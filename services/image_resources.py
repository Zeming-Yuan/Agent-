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
    if (not finite(budget.valid_until) or budget.valid_until <= now or not runtime_hash
            or budget.runtime_hash != runtime_hash
            or any(type(value) is not int or value < 0 for value in
                   (budget.peak_increment_bytes, budget.margin_bytes, budget.reserve_bytes))
            or budget.reserve_bytes < 20*1024**3):
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
from .image_telemetry import task_event


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
        self.settings = settings or {}
        self.runtime_hash = runtime_hash
        self.proof = []

    def budget(self, item):
        return self.budgets.get(profile_for(item))

    def configured(self, item=None):
        if (not callable(self.sampler) or not self.runtime_hash
                or any(not finite(self.settings.get(key)) or self.settings[key] <= 0
                       for key in ('max_age', 'stable_window', 'wait_timeout'))):
            return False
        if item is None:
            return bool(self.budgets)
        return self.budget(item) is not None

    def sample(self, tid):
        try:
            return self.sampler(tid)
        except Exception:
            return None

    async def prepare(self, item, store, client, url):
        from .images import settled_post
        tid = item['id']
        self.proof = []
        start = time.monotonic()
        initial = self.sample(tid)
        epoch = initial.release_epoch if initial is not None else None
        identity = (initial.host_id, initial.runtime_hash, initial.session_id) if initial else None
        task_event(store,tid,{'type':'resource_wait','reason':'release_unconfirmed'})
        # A single owned request. HTTP completion alone never authorizes loading.
        try:
            response = await settled_post(client, url+'/free', json={'unload_models': True, 'free_memory': True})
            response.raise_for_status()
        except asyncio.CancelledError:
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
                if self.proof and (not finite(sample.observed_at) or not 0 < sample.observed_at-self.proof[-1].observed_at <= min(.2,self.settings['max_age'])+1e-9):
                    self.proof = []
                self.proof.append(sample)
                while len(self.proof) > 2 and self.proof[-1].observed_at-self.proof[1].observed_at >= self.settings['stable_window']:
                    self.proof.pop(0)
            proven = correlated and released(self.proof, epoch, self.settings['stable_window'])
            decision = admit(sample, self.budget(item), now=now, runtime_hash=self.runtime_hash,
                             released=proven, max_age=self.settings['max_age'])
            if decision.allowed:
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
            and sample.release_epoch >= last.release_epoch and sample.resident_profiles == frozenset())
        decision = admit(sample, self.budget(item), now=time.monotonic(), runtime_hash=self.runtime_hash,
                         released=proven, max_age=self.settings['max_age'])
        if not decision.allowed:
            raise ResourceWaitExpired('Image admission recheck: '+decision.reason)
