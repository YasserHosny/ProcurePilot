"""`dispatch.py gate` on a job whose clone has no changes.

Run with: apps/api/.venv/bin/pytest scripts/factory/tests -q
"""

from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path / "factory"))
    monkeypatch.setenv("FACTORY_ENV_FILE", str(tmp_path / "no-env-file"))
    sys.modules.pop("dispatch", None)
    return importlib.import_module("dispatch")


def _git(clone: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(clone), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _job_with_clone(dispatch, status: str) -> tuple[str, Path]:  # noqa: ANN001
    """A job whose clone sits exactly at its checkpoint, as Agy left it on 2026-11-23."""
    job_id = "20261123-0255-backoffice-agy"
    clone = dispatch.CLONES_DIR / job_id
    clone.mkdir(parents=True)
    _git(clone, "init", "-q")
    _git(clone, "config", "user.name", "T")
    _git(clone, "config", "user.email", "t@example.test")
    (clone / "a.txt").write_text("base\n")
    _git(clone, "add", "a.txt")
    _git(clone, "commit", "-qm", "checkpoint")
    job_dir = dispatch.JOBS_DIR / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "id": job_id,
                "created_at": "2026-11-23T00:55:00+00:00",
                "status": status,
                "lane": "ui",
                "implementer": "agy",
                "clone": str(clone),
                "checkpoint_sha": _git(clone, "rev-parse", "HEAD"),
                "gates": ["false"],
                "gate_timeout_seconds": 60,
                "events": [],
            }
        )
    )
    return job_id, clone


def _gate(dispatch, job_id: str, gates: list[str] | None) -> int:  # noqa: ANN001
    with pytest.raises(SystemExit) as exit_:
        dispatch.cmd_gate(argparse.Namespace(job=job_id, gate=gates))
    return exit_.value.code


def _status(dispatch, job_id: str) -> str:  # noqa: ANN001
    return dispatch.Job.load(job_id).data["status"]


def test_passing_replacement_gates_on_an_unchanged_clone_stay_no_changes(
    dispatch,  # noqa: ANN001
) -> None:
    job_id, _ = _job_with_clone(dispatch, "no_changes")
    assert _gate(dispatch, job_id, ["true"]) == 1
    assert _status(dispatch, job_id) == "no_changes"
    job = dispatch.Job.load(job_id)
    assert "identical to the checkpoint" in job.data["events"][-1]["note"]
    # The gate output is still recorded.
    assert job.data["gate_results"][0]["ok"] is True
    assert "no_changes" in (job.dir / "summary.md").read_text()


def test_failing_gates_on_an_unchanged_clone_are_still_gate_failed(dispatch) -> None:  # noqa: ANN001
    job_id, _ = _job_with_clone(dispatch, "no_changes")
    assert _gate(dispatch, job_id, None) == 1
    assert _status(dispatch, job_id) == "gate_failed"


def test_passing_gates_on_a_changed_clone_pass(dispatch) -> None:  # noqa: ANN001
    job_id, clone = _job_with_clone(dispatch, "gate_failed")
    (clone / "a.txt").write_text("changed\n")
    assert _gate(dispatch, job_id, ["true"]) == 0
    assert _status(dispatch, job_id) == "passed"
