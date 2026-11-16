from scripts.image_measurement import validate_profile_report
import pytest


def test_tb11_no_raw_runs_cannot_enable_profile():
    report = {
        "profile": "fast",
        "cycles": [1, 2, 3],
        "raw_runs": [],
        "input_envelope": {"sizes": ["1024x1024"], "references": [1]},
        "runtime_hash": "r",
        "baseline_status": "not_run",
        "guard_events": [],
        "min_available_bytes": 40 * 1024**3,
        "release_proof": False,
        "budget": {},
    }
    errors = validate_profile_report(report)
    assert "raw_runs" in errors
    assert "release_proof" in errors
    assert "budget" in errors


def profile_fixture():
    runs = []
    for index in range(9):
        runs.append(
            {
                "run_id": "run-1",
                "request_id": f"req-{index}",
                "task_id": f"task-{index}",
                "profile": "fast" if index % 3 == 1 else "generate",
                "runtime_hash": "r",
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
        "runtime_hash": "r",
        "budget": {"reserve_bytes": 20 * 1024**3},
        "min_available_bytes": 40 * 1024**3,
        "release_proof": True,
        "guard_events": [],
    }


def test_tb11_valid_synthetic_report_passes_shape_gate():
    assert validate_profile_report(profile_fixture()) == []


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"raw_runs": []}, "raw_runs"),
        ({"release_proof": False}, "release_proof"),
        ({"guard_events": ["reserve_stop"]}, "guard_events"),
        ({"min_available_bytes": 19 * 1024**3}, "reserve"),
        ({"budget": {}}, "budget"),
    ],
)
def test_tb11_profile_counterexamples(change, expected):
    report = profile_fixture()
    report.update(change)
    assert expected in validate_profile_report(report)


def test_tb11_duplicate_task_ids_are_not_independent_runs():
    report = profile_fixture()
    report["raw_runs"][1]["task_id"] = report["raw_runs"][0]["task_id"]
    assert "duplicate_tasks" in validate_profile_report(report)


def test_tb11_runtime_mismatch_cannot_be_hidden_by_valid_run_shape():
    report = profile_fixture()
    report["raw_runs"][0]["runtime_hash"] = "old-runtime"
    assert "runtime_hash" in validate_profile_report(report)


def test_tb11_profile_runs_must_follow_generate_edit_generate_order():
    report = profile_fixture()
    report["raw_runs"][1]["profile"] = "standard"
    assert "profile_order" in validate_profile_report(report)


def test_tb11_latency_summary_reports_full_saved_output_window():
    from scripts.image_measurement import latency_summary

    runs = [
        {"submitted_ns": 0, "saved_ns": 10_000_000},
        {"submitted_ns": 0, "saved_ns": 30_000_000},
        {"submitted_ns": 0, "saved_ns": 20_000_000},
    ]
    assert latency_summary(runs) == {
        "count": 3,
        "p50_ms": 20.0,
        "p95_ms": 30.0,
        "range_ms": [10.0, 30.0],
    }


def test_tb11_model_switch_rejects_less_than_three_cycles(tmp_path):
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.benchmark_images",
            "--scenario",
            "model-switch",
            "--profiles",
            "fast",
            "--cycles",
            "2",
            "--config",
            str(tmp_path / "missing.json"),
            "--report-dir",
            str(tmp_path / "reports"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "cycles must be at least 3" in result.stdout


def test_tb11_model_switch_rejects_duplicate_profiles(tmp_path):
    import asyncio
    from scripts.benchmark_images import model_switch

    with pytest.raises(ValueError, match="profiles must be unique"):
        asyncio.run(model_switch({}, tmp_path / "reports", ["fast", "fast"], 3))
