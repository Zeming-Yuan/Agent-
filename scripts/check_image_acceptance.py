"""Validate the evidence envelope for the T14 joint image-service acceptance.

The checker is intentionally a gate: it reports missing or contradictory evidence and
never infers a platform, profile, or AC from another field.  It does not contact a
live service and it does not mutate the parent issue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


_REQUIRED_PLATFORMS = ("windows", "macos")
_REQUIRED_PLATFORM_FIELDS = ("os_version", "harness_version", "task_ids", "evidence")
_REQUIRED_DRILLS = ("backend_offline", "gateway_restart", "unknown_submission", "resource_shortage", "cancel_completion_race")
_REQUIRED_IDENTITY_CHECKS = ("cross_owner_access_denied", "same_key_replay_once", "key_rotation_preserves_owner", "legacy_takeover_verified")
_REQUIRED_RECOVERY_CHECKS = ("backend_idle_before_restore", "new_writes_preserved", "no_replay")


def _non_empty(value: Any) -> bool:
    """Return whether a report value contains usable evidence."""
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _path_digest_error(item: Any, *, root: Path | None) -> str | None:
    """Validate an optional ``{"path": ..., "sha256": ...}` evidence reference."""
    if not isinstance(item, dict) or "path" not in item:
        return None
    raw_path = item.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return "path"
    path = Path(raw_path)
    if root is not None and not path.is_absolute():
        path = root / path
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return "path"
    if root is not None:
        try:
            resolved.relative_to(root.resolve(strict=True))
        except (OSError, ValueError):
            return "path"
    path = resolved
    expected = item.get("sha256")
    if expected is not None:
        if not isinstance(expected, str) or len(expected) != 64:
            return "sha256"
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            return "path"
        if digest != expected.lower():
            return "sha256"
    return None


def _evidence_errors(value: Any, prefix: str, *, root: Path | None) -> list[str]:
    """Require hash-backed file references for delivery evidence."""
    if not isinstance(value, list) or not value:
        return [prefix]
    errors: list[str] = []
    for index, item in enumerate(value):
        item_prefix = f"{prefix}[{index}]"
        if not isinstance(item, dict) or "path" not in item or "sha256" not in item:
            errors.append(f"{item_prefix}.reference")
            continue
        error = _path_digest_error(item, root=root)
        if error:
            errors.append(f"{item_prefix}.{error}")
    return errors


def _record_errors(report: Any, name: str, required_checks: tuple[str, ...], *, root: Path | None) -> list[str]:
    prefix = name
    if not isinstance(report, dict):
        return [prefix]
    errors: list[str] = []
    for check in required_checks:
        if report.get(check) is not True:
            errors.append(f"{prefix}.{check}")
    counts = report.get("backend_execution_counts")
    if not isinstance(counts, dict) or not counts:
        errors.append(f"{prefix}.backend_execution_counts")
    elif any(type(value) is not int or value < 0 for value in counts.values()):
        errors.append(f"{prefix}.backend_execution_counts")
    elif any(value > 1 for value in counts.values()):
        errors.append(f"{prefix}.duplicate_execution")
    errors.extend(_evidence_errors(report.get("evidence"), f"{prefix}.evidence", root=root))
    return errors


def _profile_errors(name: str, report: Any, *, final_runtime: str, root: Path | None) -> list[str]:
    prefix = f"profiles.{name}"
    if not isinstance(report, dict) or not report:
        return [prefix]
    errors: list[str] = []
    runtime_hash = report.get("runtime_hash")
    if not _non_empty(runtime_hash) or runtime_hash != final_runtime:
        errors.append(f"{prefix}.runtime_hash")
    required_markers = {"profile", "input_envelope", "cycles", "raw_runs", "budget",
                        "release_proof", "min_available_bytes"}
    if not required_markers.issubset(report):
        errors.append(f"{prefix}.report")
    else:
        try:
            from scripts.image_measurement import validate_profile_report
        except ModuleNotFoundError:  # direct ``python scripts/check_image_acceptance.py``
            from image_measurement import validate_profile_report

        errors.extend(f"{prefix}.{error}" for error in validate_profile_report(report))
    errors.extend(_evidence_errors(report.get("evidence"), f"{prefix}.evidence", root=root))
    return errors


def check_acceptance(report: dict[str, Any], *, evidence_root: str | Path | None = None) -> list[str]:
    """Return stable field paths for every missing or contradictory T14 requirement."""
    if not isinstance(report, dict):
        return ["report"]

    root = Path(evidence_root).expanduser() if evidence_root is not None else None
    errors: list[str] = []
    criteria = report.get("criteria")
    if not isinstance(criteria, dict):
        criteria = {}
    for number in range(1, 21):
        key = f"AC-{number:02}"
        item = criteria.get(key)
        if not isinstance(item, dict) or item.get("passed") is not True:
            errors.append(key)
            continue
        evidence = item.get("evidence")
        if not _non_empty(evidence):
            errors.append(key)
        else:
            errors.extend(_evidence_errors(evidence, f"{key}.evidence", root=root))

    platforms = report.get("platforms")
    if not isinstance(platforms, dict):
        platforms = {}
    for platform in _REQUIRED_PLATFORMS:
        item = platforms.get(platform)
        if not isinstance(item, dict):
            item = {}
        if item.get("actual_harness") is not True:
            errors.append(f"{platform}.actual_harness")
        for field in _REQUIRED_PLATFORM_FIELDS:
            if not _non_empty(item.get(field)):
                errors.append(f"{platform}.{field}")
        errors.extend(_evidence_errors(item.get("evidence"), f"{platform}.evidence", root=root)
                      if _non_empty(item.get("evidence")) else [])

    final_build = report.get("final_build")
    final_runtime = final_build.get("runtime_hash") if isinstance(final_build, dict) else None
    if not _non_empty(final_runtime):
        errors.append("final_build.runtime_hash")

    profiles = report.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        errors.append("profiles")
    elif _non_empty(final_runtime):
        for name, profile in profiles.items():
            errors.extend(_profile_errors(str(name), profile, final_runtime=final_runtime, root=root))

    drills = report.get("drills")
    if not isinstance(drills, dict):
        errors.append("drills")
    else:
        for name in _REQUIRED_DRILLS:
            errors.extend(_record_errors(drills.get(name), f"drills.{name}", ("passed",), root=root))

    identity = report.get("identity")
    if not isinstance(identity, dict):
        errors.append("identity")
    else:
        for name in _REQUIRED_IDENTITY_CHECKS:
            if identity.get(name) is not True:
                errors.append(f"identity.{name}")
        errors.extend(_evidence_errors(identity.get("evidence"), "identity.evidence", root=root))

    recovery = report.get("recovery")
    if not isinstance(recovery, dict):
        errors.append("recovery")
    else:
        for name in _REQUIRED_RECOVERY_CHECKS:
            if recovery.get(name) is not True:
                errors.append(f"recovery.{name}")
        errors.extend(_evidence_errors(recovery.get("evidence"), "recovery.evidence", root=root))

    return list(dict.fromkeys(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate T14 image-service acceptance evidence")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--evidence-root", type=Path)
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "failed", "errors": [f"report.{type(exc).__name__}"]}, ensure_ascii=False))
        return 1
    errors = check_acceptance(report, evidence_root=args.evidence_root)
    print(json.dumps({"status": "failed" if errors else "passed", "errors": errors}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
