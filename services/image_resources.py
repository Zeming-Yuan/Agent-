"""Fail-closed image admission. System and container scopes are never summed."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class MemoryBudget:
    peak_increment_bytes: int
    margin_bytes: int
    reserve_bytes: int
    valid_until: float
    runtime_hash: str


@dataclass(frozen=True)
class AdmissionDecision:
    allowed: bool
    reason: str


def admit(sample, budget, *, now, runtime_hash, released, max_age):
    if sample is None or budget is None:
        return AdmissionDecision(False, 'missing_evidence')
    if not released or sample.running_prompts != () or sample.resident_profiles is None:
        return AdmissionDecision(False, 'release_unconfirmed')
    if not all(finite(value) for value in (now, max_age, sample.observed_at)) or max_age <= 0 or not 0 <= now-sample.observed_at <= max_age:
        return AdmissionDecision(False, 'stale_sample')
    if not valid_budget(budget, now, runtime_hash):
        return AdmissionDecision(False, 'invalid_budget')
    if sample.errors or any(type(value) is not int or value < 0 for value in
                            (sample.available_bytes, sample.cgroup_headroom_bytes)):
        return AdmissionDecision(False, 'missing_evidence')
    need = budget.peak_increment_bytes + budget.margin_bytes
    if sample.available_bytes < need + budget.reserve_bytes:
        return AdmissionDecision(False, 'system_memory')
    if sample.cgroup_headroom_bytes < need:
        return AdmissionDecision(False, 'container_memory')
    return AdmissionDecision(True, 'ready')


def valid_budget(budget, now, runtime_hash):
    return (isinstance(budget, MemoryBudget) and finite(budget.valid_until) and budget.valid_until > now
        and bool(runtime_hash) and budget.runtime_hash == runtime_hash
        and all(type(value) is int and value >= 0 for value in
                (budget.peak_increment_bytes, budget.margin_bytes, budget.reserve_bytes))
        and budget.reserve_bytes >= 20*1024**3)


def valid_envelope(envelope):
    return (isinstance(envelope, dict) and isinstance(envelope.get('sizes'), list) and bool(envelope['sizes'])
        and all(isinstance(size,str) for size in envelope['sizes'])
        and type(envelope.get('foreground')) is bool
        and all(type(envelope.get(key)) is int and low <= envelope[key] <= high for key,low,high in
                (('max_references',0,3),('max_reference_pixels',1,16_000_000),
                 ('max_prompt_chars',1,4000),('max_title_chars',0,60))))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def released(samples, after_epoch, stable_window):
    """A complete, correlated window, never two sparse observations or /free ACK."""
    if not finite(stable_window) or stable_window <= 0 or len(samples) < 2:
        return False
    first = samples[0]
    identity = (first.host_id, first.runtime_hash, first.session_id, first.release_task_id)
    if not all(isinstance(value, str) and value for value in identity):
        return False
    previous = None
    for sample in samples:
        if (sample.release_proven is not True or sample.resident_profiles != frozenset()
                or sample.running_prompts != () or sample.errors
                or type(sample.release_epoch) is not int or sample.release_epoch <= after_epoch
                or (sample.host_id, sample.runtime_hash, sample.session_id, sample.release_task_id) != identity
                or not finite(sample.observed_at)):
            return False
        if previous is not None and not 0 < sample.observed_at-previous <= .2 + 1e-9:
            return False
        previous = sample.observed_at
    return samples[-1].observed_at-first.observed_at >= stable_window


import asyncio
import time
from .image_telemetry import record_current_task, task_event


class ResourceWaitExpired(RuntimeError):
    pass


class ReleaseUnconfirmed(RuntimeError):
    pass


def profile_for(item):
    return item['options']['quality'] if item['kind'] == 'image_edit' else 'generate'


class ImageAdmission:
    """Owned by the serial worker from release request through the final recheck."""
    def __init__(self, sampler=None, budgets=None, settings=None, runtime_hash=None):
        self.sampler = sampler
        self.budgets = budgets or {}
        import copy
        self.settings = copy.deepcopy(settings or {})
        self.runtime_hash = runtime_hash
        self.proof = []
        self.unavailable_reason = None

    def budget(self, item):
        return self.budgets.get(profile_for(item))

    def configured(self, item=None):
        if (not callable(self.sampler) or not self.runtime_hash
                or any(not finite(self.settings.get(key)) or self.settings[key] <= 0
                       for key in ('max_age', 'stable_window', 'wait_timeout'))):
            return False
        envelopes = self.settings.get('input_envelopes', {})
        if not isinstance(envelopes, dict):return False
        now = time.monotonic()
        if item is None:
            return any(valid_budget(budget,now,self.runtime_hash) and valid_envelope(envelopes.get(profile))
                       for profile,budget in self.budgets.items())
        envelope = envelopes.get(profile_for(item))
        if not valid_budget(self.budget(item),now,self.runtime_hash) or not valid_envelope(envelope):return False
        opts = item['options']
        return (opts['size'] in envelope['sizes'] and len(opts['image_ids']) <= envelope['max_references']
            and (not opts['foreground_file_id'] or envelope['foreground'])
            and len(opts['prompt']) <= envelope['max_prompt_chars'] and len(opts['title']) <= envelope['max_title_chars'])

    def validate_inputs(self, item, store):
        from PIL import Image
        if not self.configured(item):
            raise ResourceWaitExpired('Image profile or input envelope unavailable')
        envelope = self.settings['input_envelopes'][profile_for(item)]
        opts = item['options']
        try:
            for fid in opts['image_ids'] + ([opts['foreground_file_id']] if opts['foreground_file_id'] else []):
                with Image.open(store.path(fid,owner=store.worker_task(item['id'])['owner'])) as image:
                    if image.width*image.height > envelope['max_reference_pixels']:
                        raise ValueError('Outside input envelope')
        except (OSError,ValueError) as exc:
            raise ResourceWaitExpired('Image input outside calibrated envelope') from exc

    def sample(self, tid):
        try:
            return self.sampler(tid)
        except Exception:
            return None

    def queue_decision(self, item):
        """Read-only conservative capacity preview; never authorizes /prompt."""
        if not self.configured(item):
            return AdmissionDecision(False, 'invalid_budget')
        sample = self.sample(item['id'])
        if sample is not None and sample.runtime_hash != self.runtime_hash:
            return AdmissionDecision(False, 'missing_evidence')
        return admit(sample, self.budget(item), now=time.monotonic(), runtime_hash=self.runtime_hash,
                     released=True, max_age=self.settings['max_age'])

    async def prepare(self, item, store, client, url):
        from .images import settled_post, settle
        tid = item['id']
        self.proof = []
        start = time.monotonic()
        pause = min(.1, self.settings['stable_window']/2, self.settings['max_age']/2)
        while True:
            initial = self.sample(tid)
            if (initial is not None and type(initial.release_epoch) is int and initial.release_epoch >= 0
                    and initial.runtime_hash == self.runtime_hash and initial.host_id and initial.session_id
                    and finite(initial.observed_at) and 0 <= time.monotonic()-initial.observed_at <= self.settings['max_age']):
                break
            task_event(store,tid,{'type':'resource_wait','reason':'missing_evidence'})
            if store.worker_task(tid)['status'] == 'cancelled':return False
            if time.monotonic()-start >= self.settings['wait_timeout']:
                raise ReleaseUnconfirmed('Initial resource evidence unavailable')
            await asyncio.sleep(pause)
        epoch = initial.release_epoch
        identity = (initial.host_id, initial.runtime_hash, initial.session_id)
        task_event(store,tid,{'type':'resource_wait','reason':'release_unconfirmed'})
        # A single owned request. HTTP completion alone never authorizes loading.
        record_current_task(store,tid,operation='release',event='release_requested')
        request = asyncio.create_task(settled_post(client, url+'/free', json={'unload_models': True, 'free_memory': True}))
        async def finish_request():
            response = await request
            response.raise_for_status()
            return response
        try:
            done,_ = await asyncio.wait({request},timeout=max(0,self.settings['wait_timeout']-(time.monotonic()-start)))
            if not done:
                self.unavailable_reason = 'Model release deadline exceeded; operator recovery required'
                task_event(store,tid,{'type':'failed','error':self.unavailable_reason,'blocked_reason':'release_unconfirmed'})
                # Terminal visibility does not release serial ownership of the in-flight call.
                await settle(finish_request())
                raise ReleaseUnconfirmed(self.unavailable_reason)
            response = request.result()
            response.raise_for_status()
            record_current_task(store,tid,operation='release',event='release_acknowledged')
        except asyncio.CancelledError:
            try:
                await settle(finish_request())
            except Exception as exc:
                self.unavailable_reason = 'Model release failed during cancellation; operator recovery required'
                raise ReleaseUnconfirmed(self.unavailable_reason) from exc
            raise
        except Exception as exc:
            raise ReleaseUnconfirmed('Model release request unconfirmed') from exc
        pause = min(.1, self.settings['stable_window']/2, self.settings['max_age']/2)
        while True:
            if store.worker_task(tid)['status'] == 'cancelled':
                return False
            sample = self.sample(tid)
            now = time.monotonic()
            correlated = (sample is not None and identity is not None and epoch is not None
                and (sample.host_id, sample.runtime_hash, sample.session_id) == identity
                and sample.runtime_hash == self.runtime_hash and sample.release_task_id == tid)
            if not correlated:
                self.proof = []
            else:
                if not self.proof or sample != self.proof[-1]:
                    if self.proof and (not finite(sample.observed_at) or not 0 < sample.observed_at-self.proof[-1].observed_at <= min(.2,self.settings['max_age'])+1e-9):
                        self.proof = []
                    self.proof.append(sample)
                while len(self.proof) > 2 and self.proof[-1].observed_at-self.proof[1].observed_at >= self.settings['stable_window']:
                    self.proof.pop(0)
            proven = correlated and released(self.proof, epoch, self.settings['stable_window'])
            decision = admit(sample, self.budget(item), now=now, runtime_hash=self.runtime_hash,
                             released=proven, max_age=self.settings['max_age'])
            if decision.allowed:
                for row in self.proof:
                    historical = admit(row,self.budget(item),now=row.observed_at,runtime_hash=self.runtime_hash,
                                       released=True,max_age=self.settings['max_age'])
                    if not historical.allowed:
                        decision = historical
                        break
                if decision.allowed:
                    record_current_task(store,tid,operation='release',event='release_proof_confirmed')
                    return True
            task_event(store, tid, {'type': 'resource_wait', 'reason': decision.reason})
            if now-start >= self.settings['wait_timeout']:
                if not proven:
                    raise ReleaseUnconfirmed('Model release evidence unconfirmed')
                raise ResourceWaitExpired('Image resource wait expired: '+decision.reason)
            await asyncio.sleep(pause)

    def recheck(self, item):
        sample = self.sample(item['id'])
        last = self.proof[-1] if self.proof else None
        proven = (sample is not None and last is not None and sample.release_proven is True
            and (sample.host_id, sample.runtime_hash, sample.session_id, sample.release_task_id) ==
                (last.host_id, last.runtime_hash, last.session_id, item['id'])
            and sample.release_epoch >= last.release_epoch and sample.resident_profiles == frozenset()
            and finite(sample.observed_at) and finite(last.observed_at)
            and ((sample == last) or 0 < sample.observed_at-last.observed_at <= min(.2,self.settings['max_age'])+1e-9)
            and 0 <= time.monotonic()-sample.observed_at <= min(.2,self.settings['max_age'])+1e-9)
        decision = admit(sample, self.budget(item), now=time.monotonic(), runtime_hash=self.runtime_hash,
                         released=proven, max_age=self.settings['max_age'])
        if not decision.allowed:
            if not proven or decision.reason == 'release_unconfirmed':
                raise ReleaseUnconfirmed('Image release evidence lost at recheck')
            raise ResourceWaitExpired('Image admission recheck: '+decision.reason)
