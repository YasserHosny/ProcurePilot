"""codex_usage: read Codex quota readings from rollout files and attribute them to sessions.

Run with: apps/api/.venv/bin/pytest scripts/factory/tests -q
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import codex_usage as cu  # noqa: E402

# The 5-hour window that ran out on 2026-11-23 (UTC).
RESET_5H = int(datetime(2026, 11, 23, 3, 32, 11, tzinfo=UTC).timestamp())
RESET_WK = int(datetime(2026, 11, 29, 9, 0, tzinfo=UTC).timestamp())


def ts(hhmm: str, day: int = 23) -> str:
    h, m = hhmm.split(":")
    return (
        datetime(2026, 11, day, int(h), int(m), tzinfo=UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )


def meta(cwd: str, sid: str) -> dict:
    return {"type": "session_meta", "payload": {"id": sid, "cwd": cwd}}


def ctx(model: str, effort: str) -> dict:
    return {"type": "turn_context", "payload": {"model": model, "effort": effort}}


def tc(at: str, five: float, weekly: float, reset5: int = RESET_5H) -> dict:
    return {
        "timestamp": at,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "last_token_usage": {"input_tokens": 1000, "cached_input_tokens": 900}
            },
            "rate_limits": {
                "primary": {
                    "used_percent": five,
                    "window_minutes": 300,
                    "resets_at": reset5,
                },
                "secondary": {
                    "used_percent": weekly,
                    "window_minutes": 10080,
                    "resets_at": RESET_WK,
                },
                "plan_type": "plus",
            },
        },
    }


def write_rollout(home: Path, name: str, events: list[dict]) -> Path:
    d = home / "sessions" / "2026" / "11" / "23"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"rollout-{name}.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return f


def test_parse_rollout_reads_quota_and_session_context(tmp_path: Path) -> None:
    f = write_rollout(
        tmp_path,
        "a",
        [
            meta("/home/u/factory/clones/20261123-0225-purchasing", "s1"),
            ctx("gpt-6.2-sol", "high"),
            {
                "type": "event_msg",
                "payload": {"type": "token_count", "rate_limits": {}},
            },
            tc(ts("00:25"), 54.0, 14.0),
            tc(ts("00:43"), 84.0, 19.0),
        ],
    )
    readings = cu.parse_rollout(f)
    assert [r.five_hour for r in readings] == [54.0, 84.0]
    r = readings[-1]
    assert r.label == "20261123-0225-purchasing"
    assert (r.model, r.effort, r.plan) == ("gpt-6.2-sol", "high", "plus")
    assert r.weekly == 19.0
    assert r.five_hour_resets == datetime.fromtimestamp(RESET_5H, UTC)


def test_recent_readings_skip_files_not_written_since(tmp_path: Path) -> None:
    old = write_rollout(
        tmp_path, "old", [meta("/x/old", "o"), tc(ts("00:10"), 10.0, 5.0)]
    )
    new = write_rollout(
        tmp_path, "new", [meta("/x/new", "n"), tc(ts("00:20"), 20.0, 6.0)]
    )
    since = datetime(2026, 11, 23, 0, 15, tzinfo=UTC)
    os.utime(old, (since.timestamp() - 60, since.timestamp() - 60))
    os.utime(new, (since.timestamp() + 60, since.timestamp() + 60))
    labels = {r.label for r in cu.recent_readings(tmp_path, since)}
    assert labels == {"new"}


def test_current_five_hour_is_zero_once_the_window_has_reset() -> None:
    r = cu.Reading(
        at=datetime(2026, 11, 23, 0, 50, tzinfo=UTC),
        label="x",
        session="s",
        cwd="/x",
        model="m",
        effort="e",
        plan="plus",
        five_hour=100.0,
        five_hour_resets=datetime.fromtimestamp(RESET_5H, UTC),
        weekly=21.0,
        weekly_resets=datetime.fromtimestamp(RESET_WK, UTC),
        source="f",
    )
    before = datetime(2026, 11, 23, 3, 0, tzinfo=UTC)
    after = datetime(2026, 11, 23, 3, 40, tzinfo=UTC)
    assert cu.current_five_hour(r, before) == 100.0
    assert cu.current_five_hour(r, after) == 0.0
    assert cu.current_weekly(r, after) == 21.0


def test_attribute_credits_turn_deltas_and_flags_jumps_before_a_first_reading(
    tmp_path: Path,
) -> None:
    # 23 Nov in miniature: a review, an unexplained jump, then two overlapping jobs.
    write_rollout(
        tmp_path,
        "review",
        [
            meta("/t/debate-review-local-m7", "r"),
            tc(ts("22:32", 22), 0.0, 5.0),
            tc(ts("22:36", 22), 6.0, 6.0),
        ],
    )
    write_rollout(
        tmp_path,
        "purchasing",
        [
            meta("/c/purchasing", "p"),
            tc(ts("23:51", 22), 29.0, 10.0),
            tc(ts("23:55", 22), 40.0, 12.0),
            tc(ts("00:05"), 60.0, 14.0),
        ],
    )
    write_rollout(
        tmp_path,
        "backoffice",
        [
            meta("/c/backoffice", "b"),
            tc(ts("23:58", 22), 45.0, 13.0),
            tc(ts("00:08"), 100.0, 21.0),
        ],
    )
    readings = cu.recent_readings(tmp_path, datetime(2026, 1, 1, tzinfo=UTC))
    shares = {s.label: s for s in cu.attribute(readings)}

    assert shares["debate-review-local-m7"].points == 6.0
    # 6 -> 29 rose during 75 quiet minutes with no local reading: not seen on this machine.
    assert shares[cu.NOT_SEEN_LOCALLY].points == 23.0
    # purchasing: 29->40 (11) and 45->60 (15). backoffice: 40->45 at its first reading (purchasing
    # was active minutes before, so it is local), then 60->100.
    assert shares["purchasing"].points == 26.0
    assert shares["backoffice"].points == 45.0
    assert sum(s.points for s in shares.values()) == 100.0
    assert shares["purchasing"].first_pct == 29.0
    assert shares["purchasing"].last_pct == 60.0


def test_attribute_restarts_from_zero_in_a_new_window(tmp_path: Path) -> None:
    later = int(datetime(2026, 11, 23, 19, 37, tzinfo=UTC).timestamp())
    write_rollout(
        tmp_path,
        "s",
        [
            meta("/x/main", "m"),
            tc(ts("00:43"), 84.0, 19.0),
            tc(ts("14:40"), 3.0, 21.0, reset5=later),
            tc(ts("14:44"), 7.0, 22.0, reset5=later),
        ],
    )
    shares = cu.attribute(
        cu.recent_readings(tmp_path, datetime(2026, 1, 1, tzinfo=UTC))
    )
    by_window = {(s.label, s.window_resets.hour): s.points for s in shares}
    assert by_window[(cu.NOT_SEEN_LOCALLY, 3)] == 84.0
    assert by_window[(cu.NOT_SEEN_LOCALLY, 19)] == 3.0
    assert by_window[("main", 19)] == 4.0


def test_attribute_keeps_sessions_apart_when_their_folders_share_a_name(
    tmp_path: Path,
) -> None:
    write_rollout(
        tmp_path,
        "one",
        [
            meta("/a/ProcurePilot", "s-one"),
            tc(ts("10:00"), 1.0, 1.0),
            tc(ts("10:05"), 4.0, 1.0),
        ],
    )
    write_rollout(
        tmp_path,
        "two",
        [
            meta("/b/ProcurePilot", "s-two"),
            tc(ts("10:06"), 5.0, 1.0),
            tc(ts("10:08"), 9.0, 1.0),
        ],
    )
    shares = [
        s
        for s in cu.attribute(
            cu.recent_readings(tmp_path, datetime(2026, 1, 1, tzinfo=UTC))
        )
        if s.label == "ProcurePilot"
    ]
    assert sorted(s.points for s in shares) == [3.0, 5.0]
    assert {s.session for s in shares} == {"s-one", "s-two"}


def test_latest_reading_finds_an_old_reading_without_reading_every_file(
    tmp_path: Path,
) -> None:
    newest = write_rollout(
        tmp_path, "newest", [meta("/x/n", "n"), tc(ts("09:00", 21), 3.0, 50.0)]
    )
    older = write_rollout(
        tmp_path, "older", [meta("/x/o", "o"), tc(ts("08:00", 21), 2.0, 49.0)]
    )
    os.utime(newest, (datetime(2026, 11, 21, 9, 1, tzinfo=UTC).timestamp(),) * 2)
    os.utime(older, (datetime(2026, 11, 21, 8, 1, tzinfo=UTC).timestamp(),) * 2)
    r = cu.latest_reading(tmp_path, datetime(2026, 11, 16, tzinfo=UTC))
    assert r is not None and r.label == "n" and r.weekly == 50.0


def test_latest_reading_keeps_looking_when_the_newest_file_holds_an_older_reading(
    tmp_path: Path,
) -> None:
    # A: last reading 08:30, but tool output kept it written until 09:01.
    # B: a reading at 08:55, last written 08:56. B's reading is the latest.
    a = write_rollout(tmp_path, "a", [meta("/x/a", "a"), tc(ts("08:30", 21), 3.0, 50.0)])
    b = write_rollout(tmp_path, "b", [meta("/x/b", "b"), tc(ts("08:55", 21), 9.0, 51.0)])
    os.utime(a, (datetime(2026, 11, 21, 9, 1, tzinfo=UTC).timestamp(),) * 2)
    os.utime(b, (datetime(2026, 11, 21, 8, 56, tzinfo=UTC).timestamp(),) * 2)
    r = cu.latest_reading(tmp_path, datetime(2026, 11, 16, tzinfo=UTC))
    assert r is not None and r.label == "b"
