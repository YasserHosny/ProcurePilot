#!/usr/bin/env python3
"""Codex quota from the local session logs: the 5-hour and weekly windows, and who used them.

Every Codex turn writes a `token_count` event to its rollout file under
`$CODEX_HOME/sessions/YYYY/MM/DD/` (older files are zstd-compressed). The event carries
`rate_limits.primary` (the 5-hour window) and `rate_limits.secondary` (the weekly window),
each with `used_percent` and `resets_at`. The percentages are account-wide, so usage from
another device or chatgpt.com shows up as a rise that no local session explains.

    codex_usage.py                 # current windows + each session's share, last 24 h
    codex_usage.py --hours 6
    codex_usage.py --json
    codex_usage.py --codex-home ~/other/.codex

Attribution is approximate. Each rise between two consecutive readings (across all sessions)
goes to the session that reported the higher one. A rise that follows QUIET_MINUTES with no
local reading at all goes to "not seen locally" instead.

Environment: CODEX_HOME (default ~/.codex).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
NOT_SEEN_LOCALLY = "(not seen locally)"
QUIET_MINUTES = 15
WINDOW_MATCH_SECONDS = 120  # resets_at jitters by a few seconds within one window
# Far enough back to keep the latest reading of a weekly window that has not reset.
WINDOW_LOOKBACK = timedelta(days=8)


@dataclass(frozen=True)
class Reading:
    at: datetime
    label: str
    session: str
    cwd: str
    model: str
    effort: str
    plan: str | None
    five_hour: float
    five_hour_resets: datetime
    weekly: float
    weekly_resets: datetime
    source: str


@dataclass
class Share:
    label: str
    session: str
    window_resets: datetime
    points: float
    first_at: datetime
    last_at: datetime
    first_pct: float
    last_pct: float
    readings: int
    model: str
    effort: str


def _lines(path: Path) -> Iterator[str]:
    if path.suffix == ".zst":
        if not shutil.which("zstdcat"):
            return
        out = subprocess.run(
            ["zstdcat", str(path)],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        ).stdout
        yield from out.splitlines()
        return
    with open(path, errors="replace") as fh:
        yield from fh


def _when(epoch: float) -> datetime:
    return datetime.fromtimestamp(epoch, UTC)


def parse_rollout(path: Path) -> list[Reading]:
    """Every quota reading in one rollout file, in file order."""
    label = session = cwd = model = effort = ""
    out: list[Reading] = []
    for line in _lines(path):
        # Cheap prefilter: these files run to megabytes and most lines are tool output.
        if (
            '"session_meta"' not in line
            and '"turn_context"' not in line
            and '"token_count"' not in line
        ):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        payload = event.get("payload") or {}
        if event.get("type") == "session_meta":
            cwd = payload.get("cwd", "")
            session = payload.get("id", "")
            label = Path(cwd).name or session[:8]
        elif event.get("type") == "turn_context":
            model = payload.get("model", model)
            effort = payload.get("effort", effort) or ""
        elif payload.get("type") == "token_count":
            limits = payload.get("rate_limits") or {}
            five, weekly = limits.get("primary"), limits.get("secondary")
            if not five or not weekly or "timestamp" not in event:
                continue
            out.append(
                Reading(
                    at=datetime.fromisoformat(
                        event["timestamp"].replace("Z", "+00:00")
                    ),
                    label=label or path.stem,
                    session=session or path.stem,
                    cwd=cwd,
                    model=model,
                    effort=effort,
                    plan=limits.get("plan_type"),
                    five_hour=float(five["used_percent"]),
                    five_hour_resets=_when(five["resets_at"]),
                    weekly=float(weekly["used_percent"]),
                    weekly_resets=_when(weekly["resets_at"]),
                    source=str(path),
                )
            )
    return out


def _rollouts(codex_home: Path, since: datetime) -> list[tuple[float, Path]]:
    """Rollout files written at or after `since`, newest first, with their mtimes.

    Selecting by mtime, not by the date folder, matters: a resumed thread keeps writing to the
    file in the folder of the day it started (a 7 Sep thread was active on 23 Nov)."""
    root = codex_home / "sessions"
    if not root.exists():
        return []
    cutoff = since.timestamp()
    out: list[tuple[float, Path]] = []
    for path in root.rglob("rollout-*"):
        if path.suffix not in {".jsonl", ".zst"}:
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime >= cutoff:
            out.append((mtime, path))
    out.sort(reverse=True)
    return out


def recent_readings(codex_home: Path, since: datetime) -> list[Reading]:
    """Readings at or after `since`, oldest first."""
    out: list[Reading] = []
    for _, path in _rollouts(codex_home, since):
        out.extend(r for r in parse_rollout(path) if r.at >= since)
    out.sort(key=lambda r: r.at)
    return out


def latest_reading(codex_home: Path, since: datetime) -> Reading | None:
    """The newest reading at or after `since`, reading files newest first and stopping once a
    file was last written before the best reading so far (it cannot hold a later one)."""
    best: Reading | None = None
    for mtime, path in _rollouts(codex_home, since):
        if best is not None and mtime < best.at.timestamp():
            break
        for r in parse_rollout(path):
            if r.at >= since and (best is None or r.at > best.at):
                best = r
    return best


def latest(readings: list[Reading]) -> Reading | None:
    return max(readings, key=lambda r: r.at) if readings else None


def current_five_hour(reading: Reading | None, now: datetime) -> float:
    """The 5-hour usage now: the last reading, or 0 once its window has reset."""
    if reading is None or now >= reading.five_hour_resets:
        return 0.0
    return reading.five_hour


def current_weekly(reading: Reading | None, now: datetime) -> float:
    if reading is None or now >= reading.weekly_resets:
        return 0.0
    return reading.weekly


def attribute(readings: list[Reading]) -> list[Share]:
    """Split each 5-hour window's rises between the sessions that reported them."""
    shares: dict[tuple[str, datetime], Share] = {}
    window: datetime | None = None
    level = 0.0
    last_seen: datetime | None = None

    def share(r: Reading, local: bool) -> Share:
        # One row per rollout file, so sessions in same-named folders stay apart.
        key = (r.source if local else NOT_SEEN_LOCALLY, window)
        label = r.label if local else NOT_SEEN_LOCALLY
        if key not in shares:
            shares[key] = Share(
                label=label,
                session=r.session if local else "",
                window_resets=window,
                points=0.0,
                first_at=r.at,
                last_at=r.at,
                first_pct=r.five_hour,
                last_pct=r.five_hour,
                readings=0,
                model=r.model if label != NOT_SEEN_LOCALLY else "",
                effort=r.effort if label != NOT_SEEN_LOCALLY else "",
            )
        return shares[key]

    for r in sorted(readings, key=lambda x: x.at):
        if (
            window is None
            or abs((r.five_hour_resets - window).total_seconds()) > WINDOW_MATCH_SECONDS
        ):
            window, level = r.five_hour_resets, 0.0
        rise = r.five_hour - level
        quiet = last_seen is None or r.at - last_seen > timedelta(minutes=QUIET_MINUTES)
        if rise > 0:
            share(r, local=not quiet).points += rise
            level = r.five_hour
        s = share(r, local=True)
        s.last_at, s.last_pct, s.readings = r.at, r.five_hour, s.readings + 1
        last_seen = r.at
    return sorted(shares.values(), key=lambda s: (s.window_resets, s.first_at))


# ---------------------------------------------------------------- command line


def _clock(dt: datetime) -> str:
    return dt.astimezone().strftime("%H:%M")


def _until(later: datetime, earlier: datetime) -> str:
    mins = max(0, int((later - earlier).total_seconds() // 60))
    return f"{mins // 60}h{mins % 60:02d}m" if mins >= 60 else f"{mins}m"


def report(
    hours: float, now: datetime | None = None, codex_home: Path = CODEX_HOME
) -> dict:
    now = now or datetime.now(UTC)
    readings = recent_readings(codex_home, now - timedelta(hours=hours))
    last = latest(readings) or latest_reading(codex_home, now - WINDOW_LOOKBACK)
    return {
        "codex_home": codex_home,
        "now": now,
        "latest": last,
        "five_hour": current_five_hour(last, now),
        "weekly": current_weekly(last, now),
        "shares": attribute(readings),
    }


def print_report(rep: dict, hours: float) -> None:
    now, last = rep["now"], rep["latest"]
    if last is None:
        print(
            f"no Codex quota readings in the last {WINDOW_LOOKBACK.days} days under "
            f"{rep['codex_home'] / 'sessions'}"
        )
        print(
            "(a window with no local reading may still carry usage from another device)"
        )
        return
    print(
        f"Codex quota, plan {last.plan or '?'}; last local reading {_clock(last.at)} "
        f"({_until(now, last.at)} ago, {last.label})"
    )
    if now >= last.five_hour_resets:
        print(
            f"  5-hour window: reset at {_clock(last.five_hour_resets)}; 0% until the next reading"
        )
    else:
        print(
            f"  5-hour window: {last.five_hour:g}% used, resets {_clock(last.five_hour_resets)} "
            f"(in {_until(last.five_hour_resets, now)})"
        )
    print(
        f"  weekly window: {rep['weekly']:g}% used, resets "
        f"{last.weekly_resets.astimezone().strftime('%a %d %b %H:%M')}"
    )
    print(
        f"\nShare of each 5-hour window, last {hours:g} h (times local, approximate):"
    )
    current = None
    for s in rep["shares"]:
        if s.window_resets != current:
            current = s.window_resets
            print(f"\n  window ending {current.astimezone().strftime('%d %b %H:%M')}")
        what = f"{s.model}/{s.effort}" if s.model else ""
        # UUIDv7 session ids share a time prefix; the tail tells same-named folders apart.
        who = f"{s.label[:36]} {s.session[-6:]}" if s.session else s.label
        span = (
            f"{s.first_pct:g}% -> {s.last_pct:g}%"
            if s.label != NOT_SEEN_LOCALLY
            else ""
        )
        print(
            f"    {s.points:5.0f} pts  {_clock(s.first_at)}-{_clock(s.last_at)}  "
            f"{who:44}  {what:22} {span}"
        )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(
        prog="codex_usage.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--hours", type=float, default=24, help="how far back to look (default 24)"
    )
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--codex-home",
        type=Path,
        default=CODEX_HOME,
        help="default $CODEX_HOME or ~/.codex",
    )
    args = p.parse_args(argv)
    rep = report(args.hours, codex_home=args.codex_home.expanduser())
    if args.json:
        out = {
            **rep,
            "latest": asdict(rep["latest"]) if rep["latest"] else None,
            "shares": [asdict(s) for s in rep["shares"]],
        }
        print(json.dumps(out, default=str, indent=2))
        return
    print_report(rep, args.hours)


if __name__ == "__main__":
    sys.exit(main())
