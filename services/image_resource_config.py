"""Private, operator-approved safe-start configuration; no calibration by schema.

The approval digest is a trusted deployment input after human evidence review.
It is an integrity/approval pin, not a cryptographic signature or proof of hardware.
Normal production profile certification remains T11; only controlled calibration
with explicit safe-start evidence is accepted here. Current T08 release proof is
unknown, so even a pinned configuration cannot by itself start inference.
"""
from dataclasses import fields
import hashlib
import json
import os
from pathlib import Path
import stat
import time

from .image_resources import ImageAdmission, MemoryBudget, finite
from .image_telemetry import ResourceSample, host_identity


def private_bytes(path, *, limit=65536, tail=False):
    path = Path(path)
    directory = path.parent.lstat()
    if (not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.getuid()
            or directory.st_mode & 0o077):
        raise ValueError('Private resource directory required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077
                or (not tail and info.st_size > limit)):
            raise ValueError('Private bounded resource file required')
        if tail and info.st_size > limit:os.lseek(fd,-limit,os.SEEK_END)
        return os.read(fd,limit)
    finally:
        os.close(fd)


def read_resource_sample(directory, runtime_hash):
    try:
        raw = private_bytes(Path(directory)/'memory.jsonl',tail=True)
        if not raw.endswith(b'\n'):return None
        row = json.loads(raw.splitlines()[-1])
        if (row.get('host_id') != host_identity() or row.get('runtime_hash') != runtime_hash
                or not isinstance(row.get('errors'),list)):return None
        row = {field.name:row[field.name] for field in fields(ResourceSample) if field.name in row}
        for key in ('resident_profiles','running_prompts','errors'):
            if key in row and row[key] is not None:
                if not isinstance(row[key],list) or any(not isinstance(v,str) for v in row[key]):return None
                row[key] = frozenset(row[key]) if key == 'resident_profiles' else tuple(row[key])
        return ResourceSample(**row)
    except (OSError,ValueError,TypeError,IndexError,KeyError):
        return None


def load_resources(path=None, *, expected_sha256=None, runtime_hash=None):
    """Absent/invalid approval disables profiles, never falls back to guessed budgets."""
    path = path or os.getenv('IMAGE_RESOURCE_CONFIG')
    expected_sha256 = expected_sha256 or os.getenv('IMAGE_RESOURCE_CONFIG_SHA256')
    runtime_hash = runtime_hash or os.getenv('IMAGE_RUNTIME_HASH')
    if not path or not expected_sha256 or not runtime_hash:return {}
    try:
        path = Path(path)
        raw = private_bytes(path)
        if hashlib.sha256(raw).hexdigest() != expected_sha256:return {}
        cfg = json.loads(raw)
        now_utc,now = time.time(),time.monotonic()
        if (cfg['version'] != 1 or cfg['mode'] != 'controlled_calibration'
                or not isinstance(cfg['approved_by'],str) or not cfg['approved_by'].strip()
                or cfg['runtime_hash'] != runtime_hash or cfg['host_id'] != host_identity()
                or cfg['guard_active'] is not True or cfg['backend_idle'] is not True
                or not finite(cfg['expires_at_utc']) or cfg['expires_at_utc'] <= now_utc):return {}
        params = {'settings':cfg['settings'],'profiles':cfg['profiles']}
        digest = hashlib.sha256(json.dumps(params,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        if digest != cfg['parameters_sha256']:return {}
        baseline = cfg['baseline']
        # An approval cannot read arbitrary private operator files.
        name = baseline['path']
        if not isinstance(name,str) or Path(name).name != name or name in ('.','..'):return {}
        data = private_bytes(path.parent/name,limit=2*1024**2)
        if hashlib.sha256(data).hexdigest() != baseline['sha256']:return {}
        samples = [json.loads(line) for line in data.splitlines()]
        if len(samples) < 2:return {}
        settings = dict(cfg['settings'])
        budgets,envelopes = {},{}
        expires = now+(cfg['expires_at_utc']-now_utc)
        for profile,record in cfg['profiles'].items():
            if profile not in ('generate','fast','standard','high'):return {}
            budgets[profile] = MemoryBudget(**record['budget'],valid_until=expires,runtime_hash=runtime_hash)
            envelopes[profile] = record['input_envelope']
        settings['input_envelopes'] = envelopes
        directory = os.getenv('IMAGE_TELEMETRY_DIR')
        if not directory:return {}
        sampler = lambda tid:read_resource_sample(directory,runtime_hash)
        gate = ImageAdmission(sampler,budgets,settings,runtime_hash)
        if not gate.configured() or any(not gate.configured({'kind':'image_generate' if p=='generate' else 'image_edit',
                'options':{'quality':p,'size':envelopes[p]['sizes'][0],'prompt':'x','title':'',
                           'image_ids':[],'foreground_file_id':None}}) for p in budgets):return {}
        previous = None
        session = samples[0]['session_id']
        for sample in samples:
            at = sample['observed_at']
            if (not isinstance(session,str) or not session or sample['session_id'] != session or sample.get('errors') != []
                    or sample['host_id'] != cfg['host_id'] or sample['runtime_hash'] != runtime_hash
                    or not finite(at) or (previous is not None and not 0 < at-previous <= min(.2,settings['max_age'])+1e-9)):
                return {}
            previous = at
            for budget in budgets.values():
                available,headroom = sample['available_bytes'],sample['cgroup_headroom_bytes']
                need = budget.peak_increment_bytes+budget.margin_bytes
                if (type(available) is not int or type(headroom) is not int
                        or available < need+budget.reserve_bytes or headroom < need):return {}
        if samples[-1]['observed_at']-samples[0]['observed_at'] < settings['stable_window']:return {}
        return dict(resource_sampler=sampler,memory_budgets=budgets,resource_settings=settings,image_runtime_hash=runtime_hash)
    except (OSError,ValueError,TypeError,KeyError,IndexError,AttributeError):
        return {}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Validate pinned private image safe-start configuration')
    parser.add_argument('--check-config',required=True)
    args = parser.parse_args()
    valid = bool(load_resources(args.check_config))
    print('Approved controlled safe-start configuration' if valid else 'Image resource configuration unavailable or invalid')
    raise SystemExit(0 if valid else 1)
