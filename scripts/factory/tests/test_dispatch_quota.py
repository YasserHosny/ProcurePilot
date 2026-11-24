"""dispatch.py's Codex quota gate, replayed against the 2026-11-23 lockout.

Run with: apps/api/.venv/bin/pytest scripts/factory/tests -q
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))


@pytest.fixture
def dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path / "factory"))
    for var in (
        "FACTORY_CODEX_CEILING",
        "FACTORY_CODEX_RETRY_CEILING",
        "FACTORY_CODEX_WEEKLY_CEILING",
        "FACTORY_CODEX_JOB_COST",
        "FACTORY_CODEX_MAX_PARALLEL",
    ):
        monkeypatch.delenv(var, raising=False)
    sys.modules.pop("dispatch", None)
    return importlib.import_module("dispatch")


def test_first_job_on_a_half_used_window_is_allowed(dispatch) -> None:  # noqa: ANN001
    # 00:25: purchasing started at 54%, nothing else running.
    assert dispatch.codex_quota_problem(54, 14, running=0, retry=False) is None


def test_second_job_that_would_overrun_the_window_is_refused(dispatch) -> None:  # noqa: ANN001
    # 00:36: backoffice at 68% with purchasing still running: 68 + 2 x 25 > 85.
    problem = dispatch.codex_quota_problem(68, 16, running=1, retry=False)
    assert problem and "5-hour" in problem and "118" in problem


def test_a_third_parallel_codex_job_is_refused_even_on_a_fresh_window(dispatch) -> None:  # noqa: ANN001
    problem = dispatch.codex_quota_problem(0, 5, running=2, retry=False)
    assert problem and "parallel" in problem


def test_a_retry_needs_the_window_below_the_retry_ceiling(dispatch) -> None:  # noqa: ANN001
    # 00:46: the failed Haiku briefs went to Codex at 88%.
    assert "retry" in dispatch.codex_quota_problem(88, 19, running=0, retry=True)
    assert "retry" in dispatch.codex_quota_problem(61, 19, running=0, retry=True)
    assert dispatch.codex_quota_problem(59, 19, running=0, retry=True) is None


def test_a_nearly_spent_weekly_window_is_refused(dispatch) -> None:  # noqa: ANN001
    assert "weekly" in dispatch.codex_quota_problem(0, 91, running=0, retry=False)


def test_thresholds_come_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path / "factory"))
    monkeypatch.setenv("FACTORY_CODEX_JOB_COST", "10")
    monkeypatch.setenv("FACTORY_CODEX_MAX_PARALLEL", "3")
    sys.modules.pop("dispatch", None)
    d = importlib.import_module("dispatch")
    # Default cost 25 would refuse 68 + 25 = 93; at 10 it is 78, under the 85 ceiling.
    assert d.codex_quota_problem(68, 16, running=0, retry=False) is None
    # Default cap 2 would refuse a third parallel job; the cap is now 3.
    assert d.codex_quota_problem(0, 5, running=2, retry=False) is None


def _job(dispatch, job_id: str, brief: str, status: str, lane: str, impl: str, **extra):  # noqa: ANN001, ANN003, ANN202
    d = dispatch.JOBS_DIR / job_id
    d.mkdir(parents=True)
    data = {
        "id": job_id,
        "created_at": job_id,
        "brief_source": brief,
        "status": status,
        "lane": lane,
        "implementer": impl,
        "clone": str(d),
        **extra,
    }
    (d / "job.json").write_text(json.dumps(data))


def test_a_brief_that_already_failed_is_a_retry(dispatch) -> None:  # noqa: ANN001
    _job(
        dispatch,
        "0235-sourcing",
        "/b/sourcing.md",
        "implementer_failed",
        "feature",
        "claude",
    )
    _job(
        dispatch,
        "0225-sourcing",
        "/b/sourcing.md",
        "preflight_failed",
        "feature",
        "claude",
    )
    _job(dispatch, "0225-purchasing", "/b/purchasing.md", "passed", "complex", "codex")
    assert dispatch.previous_failure("/b/sourcing.md").id == "0235-sourcing"
    # A preflight failure never reached an implementer, and a passed job is not a failure.
    assert dispatch.previous_failure("/b/purchasing.md") is None
    assert dispatch.previous_failure("/b/new.md") is None


DEAD_PID = 2**22 + 12345  # above the default pid_max, so never alive


def test_codex_slots_count_live_jobs_and_fresh_reservations(dispatch) -> None:  # noqa: ANN001
    import os
    from datetime import UTC, datetime, timedelta

    fresh = datetime.now(UTC).isoformat()
    stale = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    me = os.getpid()
    _job(dispatch, "live", "/b/1.md", "running", "complex", "codex", supervisor_pid=me)
    # Supervisor died, Codex itself still running: the slot is still taken.
    _job(
        dispatch,
        "orphan",
        "/b/2.md",
        "running",
        "complex",
        "codex",
        supervisor_pid=DEAD_PID,
        relay_pid=me,
    )
    _job(
        dispatch,
        "gone",
        "/b/3.md",
        "running",
        "complex",
        "codex",
        supervisor_pid=DEAD_PID,
        relay_pid=DEAD_PID,
    )
    # Admitted moments ago and still cloning: reserved.
    _job(
        dispatch, "cloning", "/b/4.md", "created", "complex", "codex", created_at=fresh
    )
    _job(
        dispatch, "abandoned", "/b/5.md", "cloned", "complex", "codex", created_at=stale
    )
    _job(dispatch, "agy", "/b/6.md", "running", "ui", "agy", supervisor_pid=me)
    _job(dispatch, "done", "/b/7.md", "passed", "complex", "codex", created_at=fresh)
    assert dispatch.running_codex_jobs() == 3
    assert dispatch.running_codex_jobs(exclude="cloning") == 2


def test_admission_lock_is_exclusive_across_processes(dispatch) -> None:  # noqa: ANN001
    import subprocess

    probe = (
        "import fcntl,sys; f=open(sys.argv[1],'a'); "
        "fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)"
    )
    with dispatch.admission_lock():
        held = subprocess.run(
            [sys.executable, "-c", probe, str(dispatch.ADMISSION_LOCK)]
        )
    free = subprocess.run([sys.executable, "-c", probe, str(dispatch.ADMISSION_LOCK)])
    assert held.returncode != 0
    assert free.returncode == 0


def _reading_line(at, five: float, weekly: float, five_resets, weekly_resets) -> str:  # noqa: ANN001
    return json.dumps(
        {
            "timestamp": at.isoformat().replace("+00:00", "Z"),
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "rate_limits": {
                    "primary": {
                        "used_percent": five,
                        "resets_at": int(five_resets.timestamp()),
                    },
                    "secondary": {
                        "used_percent": weekly,
                        "resets_at": int(weekly_resets.timestamp()),
                    },
                },
            },
        }
    )


def test_quota_check_reads_the_env_files_codex_home_and_an_old_weekly_reading(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    relay_home = tmp_path / "relay-codex"
    f = relay_home / "sessions" / "2026" / "11" / "22" / "rollout-old.jsonl"
    f.parent.mkdir(parents=True)
    two_days_ago = now - timedelta(days=2)
    f.write_text(
        _reading_line(
            two_days_ago,
            40,
            96,
            two_days_ago + timedelta(hours=3),
            now + timedelta(days=3),
        )
        + "\n"
    )
    os.utime(f, (two_days_ago.timestamp(), two_days_ago.timestamp()))
    env_file = tmp_path / "pp-env.sh"
    env_file.write_text(f"export CODEX_HOME={relay_home}\n")
    monkeypatch.setenv("FACTORY_HOME", str(tmp_path / "factory"))
    monkeypatch.setenv("FACTORY_ENV_FILE", str(env_file))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "caller-codex-empty"))
    sys.modules.pop("dispatch", None)
    d = importlib.import_module("dispatch")

    problem, snapshot = d.check_codex_quota("/b/x.md")
    assert snapshot["codex_home"] == str(relay_home)
    assert snapshot["weekly"] == 96  # still inside its weekly window
    assert snapshot["five_hour"] == 0  # that 5-hour window reset long ago
    assert problem and "weekly" in problem


def test_start_rechecks_quota_for_a_staged_codex_job(
    dispatch,
    monkeypatch: pytest.MonkeyPatch,  # noqa: ANN001
) -> None:
    import argparse

    _job(dispatch, "staged", "/b/s.md", "cloned", "complex", "codex")
    started: list[str] = []
    monkeypatch.setattr(
        dispatch, "start_supervisor", lambda job: started.append(job.id)
    )
    seen: list[str | None] = []

    def fake_check(brief: str, exclude: str | None = None) -> tuple[str | None, dict]:
        seen.append(exclude)
        return "5-hour window would reach 110%", {}

    monkeypatch.setattr(dispatch, "check_codex_quota", fake_check)
    with pytest.raises(SystemExit):
        dispatch.cmd_start(argparse.Namespace(job="staged", ignore_quota=False))
    assert started == [] and seen == ["staged"]
    dispatch.cmd_start(argparse.Namespace(job="staged", ignore_quota=True))
    assert started == ["staged"]


def test_choose_lane_reroutes_a_refused_codex_job_to_the_fallback_lane(
    dispatch,
) -> None:  # noqa: ANN001
    lane, note = dispatch.choose_lane(
        "complex", "codex", "5-hour window would reach 118%", "ui"
    )
    assert lane == "ui"
    assert "complex" in note and "ui" in note and "118%" in note


def test_choose_lane_keeps_the_lane_when_quota_is_fine_or_the_lane_is_not_codex(
    dispatch,
) -> None:  # noqa: ANN001
    assert dispatch.choose_lane("complex", "codex", None, "ui") == ("complex", None)
    assert dispatch.choose_lane("ui", "agy", None, "ui") == ("ui", None)


def test_choose_lane_without_a_fallback_refuses(dispatch) -> None:  # noqa: ANN001
    with pytest.raises(SystemExit):
        dispatch.choose_lane("complex", "codex", "5-hour window would reach 118%", None)


def test_choose_lane_refuses_to_carry_relay_args_onto_the_fallback(dispatch) -> None:  # noqa: ANN001
    # Codex accepts --ignore-user-config; the Agy relay exits 2 on it.
    with pytest.raises(SystemExit):
        dispatch.choose_lane(
            "complex",
            "codex",
            "5-hour window would reach 118%",
            "ui",
            relay_args=["--ignore-user-config"],
        )


@pytest.mark.parametrize("status", ["cloned", "implementer_failed"])
def test_start_holds_the_slot_before_the_lock_is_released(
    dispatch,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
    status: str,
) -> None:
    import argparse

    # Created long ago: a staged job past its reservation, or a failed job being restarted.
    _job(
        dispatch,
        "old",
        "/b/o.md",
        status,
        "complex",
        "codex",
        created_at="2026-01-01T00:00:00+00:00",
    )
    monkeypatch.setattr(
        dispatch, "check_codex_quota", lambda brief, exclude=None: (None, {})
    )
    counted: list[int] = []
    monkeypatch.setattr(
        dispatch,
        "start_supervisor",
        lambda job: counted.append(dispatch.running_codex_jobs()),
    )
    dispatch.cmd_start(argparse.Namespace(job="old", ignore_quota=False))
    assert counted == [1]
