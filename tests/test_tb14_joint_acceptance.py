import hashlib
import json
import subprocess
import sys

import pytest

from scripts.check_image_acceptance import check_acceptance


def test_tb14_macos_only_cannot_pass_joint_acceptance():
    report = {
        "criteria": {},
        "platforms": {
            "macos": {
                "actual_harness": True,
                "os_version": "fixture",
                "harness_version": "fixture",
                "task_ids": ["task-a"],
                "evidence": [{"path": "mac-proof", "sha256": "0" * 64}],
            }
        },
        "profiles": {},
    }
    errors = check_acceptance(report)
    assert "windows.actual_harness" in errors
    assert "AC-01" in errors


@pytest.mark.parametrize("missing", ["windows", "macos"])
def test_tb14_each_platform_required(missing):
    report = {"criteria": {}, "platforms": {}, "profiles": {}}
    report["platforms"][missing] = {"actual_harness": False}
    assert f"{missing}.actual_harness" in check_acceptance(report)


@pytest.mark.parametrize("number", [1, 7, 11, 16, 20])
def test_tb14_each_ac_requires_actual_evidence(number):
    key = f"AC-{number:02}"
    report = {
        "criteria": {key: {"passed": True, "evidence": []}},
        "platforms": {},
        "profiles": {},
    }
    assert key in check_acceptance(report)


def test_tb14_minimal_shape_is_not_delivery():
    platforms = {
        platform: {
            "actual_harness": True,
            "os_version": "test",
            "harness_version": "test",
            "task_ids": ["synthetic"],
            "evidence": ["synthetic-proof"],
        }
        for platform in ("windows", "macos")
    }
    report = {
        "criteria": {
            f"AC-{number:02}": {"passed": True, "evidence": ["synthetic"]}
            for number in range(1, 21)
        },
        "platforms": platforms,
        "profiles": {"fast": {"runtime_hash": "test"}},
    }
    errors = check_acceptance(report)
    assert "AC-01.evidence[0].reference" in errors
    assert "final_build.runtime_hash" in errors
    assert "drills" in errors
    assert "identity" in errors
    assert "recovery" in errors


def test_tb14_empty_profiles_is_not_delivery():
    report = {"criteria": {}, "platforms": {}, "profiles": {}}
    assert "profiles" in check_acceptance(report)


def _proof_ref(tmp_path):
    evidence = tmp_path / "proof.json"
    evidence.write_text("current", encoding="utf-8")
    return {
        "path": evidence.name,
        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
    }


def _profile_report(ref):
    runs = []
    for index in range(9):
        runs.append(
            {
                "run_id": f"run-{index}",
                "request_id": f"req-{index}",
                "task_id": f"task-{index}",
                "profile": "fast" if index % 3 == 1 else "generate",
                "runtime_hash": "runtime",
                "host_match": True,
                "backend_executions": 1,
                "status": "completed",
                "output_verified": True,
                "submitted_ns": index * 100,
                "completed_ns": index * 100 + 10,
                "downloaded_ns": index * 100 + 20,
                "saved_ns": index * 100 + 30,
                "memory_samples": [{"available_bytes": 40 * 1024**3}],
                "guard_events": [],
            }
        )
    return {
        "profile": "fast",
        "cycles": [1, 2, 3],
        "raw_runs": runs,
        "input_envelope": {"sizes": ["1024x1024"], "references": [1]},
        "runtime_hash": "runtime",
        "budget": {"reserve_bytes": 20 * 1024**3},
        "min_available_bytes": 40 * 1024**3,
        "release_proof": True,
        "guard_events": [],
        "evidence": [ref],
    }


def _complete_report(tmp_path):
    ref = _proof_ref(tmp_path)
    platforms = {
        platform: {
            "actual_harness": True,
            "os_version": "test",
            "harness_version": "test",
            "task_ids": [f"{platform}-task"],
            "evidence": [ref],
        }
        for platform in ("windows", "macos")
    }
    drills = {
        name: {"passed": True, "backend_execution_counts": {"task": 1}, "evidence": [ref]}
        for name in (
            "backend_offline",
            "gateway_restart",
            "unknown_submission",
            "resource_shortage",
            "cancel_completion_race",
        )
    }
    return {
        "criteria": {
            f"AC-{number:02}": {"passed": True, "evidence": [ref]}
            for number in range(1, 21)
        },
        "platforms": platforms,
        "profiles": {"fast": _profile_report(ref)},
        "final_build": {"runtime_hash": "runtime"},
        "drills": drills,
        "identity": {
            "cross_owner_access_denied": True,
            "same_key_replay_once": True,
            "key_rotation_preserves_owner": True,
            "legacy_takeover_verified": True,
            "evidence": [ref],
        },
        "recovery": {
            "backend_idle_before_restore": True,
            "new_writes_preserved": True,
            "no_replay": True,
            "evidence": [ref],
        },
    }


def test_tb14_complete_hash_backed_report_passes(tmp_path):
    assert check_acceptance(_complete_report(tmp_path), evidence_root=tmp_path) == []


def test_tb14_rejects_profile_runtime_mismatch(tmp_path):
    report = _complete_report(tmp_path)
    report["profiles"]["fast"]["runtime_hash"] = "old-runtime"
    assert "profiles.fast.runtime_hash" in check_acceptance(report, evidence_root=tmp_path)


def test_tb14_missing_final_build_is_rejected(tmp_path):
    report = _complete_report(tmp_path)
    report.pop("final_build")
    assert "final_build.runtime_hash" in check_acceptance(report, evidence_root=tmp_path)


def test_tb14_verifies_hashed_evidence_reference(tmp_path):
    report = _complete_report(tmp_path)
    report["criteria"]["AC-01"]["evidence"][0]["sha256"] = "0" * 64
    errors = check_acceptance(report, evidence_root=tmp_path)
    assert "AC-01.evidence[0].sha256" in errors


def test_tb14_cli_fails_closed_for_missing_evidence(tmp_path):
    report = _complete_report(tmp_path)
    report["platforms"]["windows"]["actual_harness"] = False
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_image_acceptance.py",
            "--report",
            str(path),
            "--evidence-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert result.stdout, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "failed"
    assert "windows.actual_harness" in payload["errors"]


def test_tb14_rejects_duplicate_backend_execution(tmp_path):
    report = _complete_report(tmp_path)
    report["drills"]["unknown_submission"]["backend_execution_counts"] = {"task": 2}
    assert "drills.unknown_submission.duplicate_execution" in check_acceptance(
        report, evidence_root=tmp_path
    )
