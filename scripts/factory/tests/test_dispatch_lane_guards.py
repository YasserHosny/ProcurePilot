"""Haiku lane limits and resource admission for concurrent dispatches."""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from dispatch import Job

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HAIKU = {"implementer": "claude", "model": "claude-HaIkU-4-5", "relay": "/relay.mjs"}
HAIKU_ARGS = ["--max-turns", "40", "--max-budget-usd", "3"]


@pytest.fixture
def dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path / "factory"))
    monkeypatch.setenv("FACTORY_MIN_DISK_GB", "8")
    monkeypatch.setenv("FACTORY_MIN_MEM_GB", "0")
    for var in (
        "FACTORY_HAIKU_MAX_TURNS",
        "FACTORY_HAIKU_MAX_BUDGET_USD",
        "FACTORY_CLONE_GB",
        "FACTORY_MAX_PARALLEL",
    ):
        monkeypatch.delenv(var, raising=False)
    sys.modules.pop("dispatch", None)
    return importlib.import_module("dispatch")


@pytest.fixture
def new_args(tmp_path: Path) -> argparse.Namespace:
    brief = tmp_path / "task.md"
    brief.write_text("Implement the task.\n")
    return argparse.Namespace(
        brief=str(brief),
        lane="feature",
        gate=["true"],
        name=None,
        base="main",
        local_base=False,
        ignore_quota=False,
        no_reroute=False,
        gate_timeout=60,
        timeout="90m",
        web=False,
        relay_arg=None,
        no_start=True,
    )


@pytest.mark.parametrize(
    ("lane", "expected"),
    [
        (HAIKU, HAIKU_ARGS),
        ({"implementer": "claude", "model": "sonnet"}, []),
        ({"implementer": "agy"}, ["--dangerously-skip-permissions"]),
    ],
)
def test_relay_extra_args(
    dispatch: ModuleType, lane: dict, expected: list[str]
) -> None:
    assert dispatch.relay_extra_args(lane) == expected


def test_haiku_caps_come_from_the_environment(
    dispatch: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FACTORY_HAIKU_MAX_TURNS", "22")
    monkeypatch.setenv("FACTORY_HAIKU_MAX_BUDGET_USD", "1.75")
    dispatch = importlib.reload(dispatch)

    assert dispatch.relay_extra_args(HAIKU) == [
        "--max-turns",
        "22",
        "--max-budget-usd",
        "1.75",
    ]


def test_per_job_relay_args_follow_haiku_caps(
    dispatch: ModuleType, new_args: argparse.Namespace
) -> None:
    job = dispatch.Job("haiku-job")
    new_args.relay_arg = ["--max-turns", "15", "--max-budget-usd", "1"]

    dispatch.record_new_job(
        job, new_args, Path(new_args.brief), "feature", HAIKU, None, None
    )

    assert dispatch.Job.load(job.id).data["relay_extra_args"] == (
        HAIKU_ARGS + new_args.relay_arg
    )


def test_brief_appends_the_haiku_footer_only_for_haiku(dispatch: ModuleType) -> None:
    clone = Path("/tmp/task-clone")
    haiku = dispatch.build_brief("Task\n", HAIKU, clone, "factory/task", ["true"])
    codex = dispatch.build_brief(
        "Task\n", {"implementer": "codex"}, clone, "factory/task", ["true"]
    )

    assert "Factory gate" in codex and "1. `true`" in codex
    assert haiku == codex + dispatch.HAIKU_FOOTER
    assert dispatch.HAIKU_FOOTER not in codex


def write_job(
    dispatch: ModuleType,
    job_id: str,
    status: str,
    minutes_old: int = 0,
    supervisor_pid: int | None = None,
) -> None:
    job = dispatch.Job(job_id)
    job.data = {
        "created_at": (datetime.now(UTC) - timedelta(minutes=minutes_old)).isoformat(),
        "status": status,
        "supervisor_pid": supervisor_pid,
    }
    job.save()


def patch_disk_usage(
    dispatch: ModuleType, monkeypatch: pytest.MonkeyPatch, free_gb: float
) -> None:
    monkeypatch.setattr(
        dispatch.shutil, "disk_usage", lambda path: SimpleNamespace(free=free_gb * 1e9)
    )


def test_only_fresh_created_jobs_reserve_disk(
    dispatch: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch_disk_usage(dispatch, monkeypatch, 9)
    write_job(dispatch, "stale", "created", minutes_old=31)
    write_job(dispatch, "done", "passed")
    assert dispatch.check_resources() == []

    write_job(dispatch, "cloning", "created")
    (problem,) = dispatch.check_resources()
    assert "1 in-flight" in problem and "9.5 GB" in problem
    assert dispatch.check_resources(exclude="cloning") == []


def test_clone_reservation_comes_from_the_environment(
    dispatch: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FACTORY_CLONE_GB", "0.5")
    dispatch = importlib.reload(dispatch)
    write_job(dispatch, "cloning", "created")

    patch_disk_usage(dispatch, monkeypatch, 8.4)
    assert dispatch.check_resources()
    patch_disk_usage(dispatch, monkeypatch, 8.5)
    assert dispatch.check_resources() == []


def probe_lock(path: Path) -> int:
    probe = (
        "import fcntl,sys; f=open(sys.argv[1],'a'); "
        "fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)"
    )
    return subprocess.run(
        [sys.executable, "-c", probe, str(path)], check=False, capture_output=True
    ).returncode


def test_resource_admission_lock_is_exclusive_across_processes(
    dispatch: ModuleType,
) -> None:
    path = dispatch.FACTORY_HOME / "resource-admission.lock"
    with dispatch.resource_admission_lock():
        assert probe_lock(path) != 0
    assert probe_lock(path) == 0


def test_new_reserves_resources_until_clone_and_uses_the_rerouted_lane(
    dispatch: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    new_args: argparse.Namespace,
    capsys: pytest.CaptureFixture[str],
) -> None:
    patch_disk_usage(dispatch, monkeypatch, 9)
    new_args.lane = "complex"
    monkeypatch.setattr(dispatch, "CODEX_FALLBACK_LANE", "feature")
    monkeypatch.setattr(dispatch, "check_codex_quota", lambda brief: ("over quota", {}))
    lane_specs = {"complex": {"implementer": "codex"}, "feature": HAIKU}
    monkeypatch.setattr(dispatch, "resolve_lane", lane_specs.__getitem__)
    resource_lock = dispatch.FACTORY_HOME / "resource-admission.lock"
    check_resources = dispatch.check_resources
    record_new_job = dispatch.record_new_job

    def check_under_locks(exclude: str | None = None) -> list[str]:
        assert probe_lock(dispatch.ADMISSION_LOCK) != 0
        assert probe_lock(resource_lock) != 0
        return check_resources(exclude=exclude)

    def record_under_locks(
        job: Job,
        args: argparse.Namespace,
        brief_path: Path,
        lane_name: str,
        lane: dict,
        quota: dict | None,
        quota_note: str | None,
    ) -> None:
        assert probe_lock(dispatch.ADMISSION_LOCK) != 0
        assert probe_lock(resource_lock) != 0
        record_new_job(job, args, brief_path, lane_name, lane, quota, quota_note)

    def fake_clone(job: Job, base: str, local_base: bool, log: list[str]) -> None:
        assert probe_lock(dispatch.ADMISSION_LOCK) == 0
        assert probe_lock(resource_lock) == 0
        (saved_job,) = dispatch.list_jobs()
        assert saved_job.data["status"] == "created"
        assert check_resources()
        assert check_resources(exclude=saved_job.id) == []
        job.data["branch"] = "factory/task"

    monkeypatch.setattr(dispatch, "check_resources", check_under_locks)
    monkeypatch.setattr(dispatch, "record_new_job", record_under_locks)
    monkeypatch.setattr(dispatch, "make_clone", fake_clone)

    dispatch.cmd_new(new_args)

    (job,) = dispatch.list_jobs()
    assert job.data["status"] == "cloned"
    assert job.data["relay_extra_args"] == HAIKU_ARGS
    assert dispatch.HAIKU_FOOTER in (job.dir / "brief.md").read_text()
    assert " ".join(HAIKU_ARGS) in capsys.readouterr().err


@pytest.mark.parametrize("cap", ["2", "0", None])
def test_parallel_cap_counts_clones_and_live_supervisors(
    dispatch: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    new_args: argparse.Namespace,
    cap: str | None,
) -> None:
    if cap is not None:
        monkeypatch.setenv("FACTORY_MAX_PARALLEL", cap)
        dispatch = importlib.reload(dispatch)
    patch_disk_usage(dispatch, monkeypatch, 20)
    write_job(dispatch, "cloning", "created")
    write_job(dispatch, "running", "running", supervisor_pid=os.getpid())
    write_job(dispatch, "dead", "running")
    monkeypatch.setattr(dispatch, "resolve_lane", lambda lane: HAIKU)

    def fake_clone(job: Job, base: str, local_base: bool, log: list[str]) -> None:
        job.data["branch"] = "factory/task"

    monkeypatch.setattr(dispatch, "make_clone", fake_clone)

    if cap == "2":
        with pytest.raises(SystemExit) as exc:
            dispatch.cmd_new(new_args)
        assert exc.value.code == 1
        (failed,) = [job for job in dispatch.list_jobs() if job.id.endswith("-task")]
        assert failed.data["status"] == "preflight_failed"
        assert "2 jobs" in (failed.dir / "preflight.log").read_text()
    else:
        dispatch.cmd_new(new_args)
        assert any(job.data["status"] == "cloned" for job in dispatch.list_jobs())
