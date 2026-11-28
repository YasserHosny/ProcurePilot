"""Balance E2E files using measured durations.

Regenerate the manifest from downloaded CI list-reporter logs with:
    python3 scripts/ci/e2e_shard.py from-logs shard-*.log > scripts/ci/e2e-durations.json
Each log contributes its per-file sum; repeated files across logs use the median.
"""

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import re
import statistics
import sys
from typing import Dict, List, Sequence


# Match a successful Playwright list-reporter line after ANSI/timestamp removal.
REPORT_LINE = re.compile(
    r"^\s*✓\s+.*?›\s+tests/e2e/(?P<name>[^/\s]+\.spec\.ts):\d+:\d+"
    r"\s+›.*\((?P<duration>\d+(?:\.\d+)?)(?P<unit>ms|s|m)\)\s*$"
)
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SPECS = ROOT / "apps/web/tests/e2e"
DEFAULT_MANIFEST = Path(__file__).resolve().with_name("e2e-durations.json")


def load_weights(specs_dir: Path, manifest: Path) -> Dict[str, float]:
    """Ignore stale entries; unseen specs use the live weights' median (or 1s)."""
    names = sorted(path.name for path in specs_dir.glob("*.spec.ts") if path.is_file())
    if not names:
        raise ValueError("No E2E spec files found in {}".format(specs_dir))
    measured = json.loads(manifest.read_text(encoding="utf-8"))
    known = {name: float(measured[name]) for name in names if name in measured}
    if any(not math.isfinite(weight) or weight <= 0 for weight in known.values()):
        raise ValueError("Manifest durations must be finite, positive seconds")
    fallback = statistics.median(known.values()) if known else 1.0
    return {name: known.get(name, fallback) for name in names}


def unmeasured(specs_dir: Path, manifest: Path) -> List[str]:
    measured = json.loads(manifest.read_text(encoding="utf-8"))
    return sorted(
        path.name for path in specs_dir.glob("*.spec.ts")
        if path.is_file() and path.name not in measured
    )


def make_plan(weights: Dict[str, float], total: int) -> List[List[str]]:
    if total < 1:
        raise ValueError("--total must be positive")
    shards: List[List[str]] = [[] for _ in range(total)]
    seconds = [0.0] * total
    for name in sorted(weights, key=lambda name: (-weights[name], name)):
        index = min(range(total), key=lambda index: (seconds[index], index))
        shards[index].append(name)
        seconds[index] += weights[name]
    return [sorted(shard) for shard in shards]


def select_kind(names: Sequence[str], kind: str) -> List[str]:
    return [
        name for name in names
        if kind == "all" or ("a11y" in name) == (kind == "a11y")
    ]


def check_plan(weights: Dict[str, float], shards: List[List[str]]) -> bool:
    counts = Counter(name for shard in shards for name in shard)
    valid = counts == Counter({name: 1 for name in weights})
    for index, shard in enumerate(shards, start=1):
        a11y = select_kind(shard, "a11y")
        functional = select_kind(shard, "functional")
        valid = valid and not set(a11y).intersection(functional)
        valid = valid and Counter(a11y + functional) == Counter(shard)
        seconds = sum(weights[name] for name in shard)
        print("Shard {}: {} files, predicted {:.1f}s".format(index, len(shard), seconds))
    totals = [sum(weights[name] for name in shard) for shard in shards]
    imbalance = max(totals) / min(totals) if min(totals) else float("inf")
    print("Imbalance (max/min): {:.3f}".format(imbalance))
    if imbalance > 1.15:
        print("WARNING: predicted imbalance exceeds 1.15")
    if not valid:
        print("ERROR: broken E2E shard partition", file=sys.stderr)
    return valid


def plan_gain(current: Dict[str, float], refit: Dict[str, float], total: int) -> float:
    """Seconds the refitted plan takes off the slowest shard, both scored on refit weights."""
    def slowest(shards: List[List[str]]) -> float:
        return max(sum(refit[name] for name in shard) for shard in shards)
    before = slowest(make_plan(current, total))
    after = slowest(make_plan(refit, total))
    print("Current plan slowest shard: {:.1f}s".format(before))
    print("Refitted plan slowest shard: {:.1f}s".format(after))
    return round(before - after, 1)


def from_logs(logs: Sequence[Path]) -> Dict[str, float]:
    samples: Dict[str, List[float]] = defaultdict(list)
    for log in logs:
        totals: Dict[str, float] = defaultdict(float)
        for line in log.read_text(encoding="utf-8").splitlines():
            line = ANSI_ESCAPE.sub("", line)
            line = re.sub(r"^\s*\S+\s+(?=✓)", "", line)
            match = REPORT_LINE.match(line)
            if match:
                scale = {"ms": 0.001, "s": 1.0, "m": 60.0}[match["unit"]]
                totals[match["name"]] += float(match["duration"]) * scale
        for name, seconds in totals.items():
            samples[name].append(seconds)
    return {name: round(statistics.median(values), 1) for name, values in samples.items()}


def carry_forward(measured: Dict[str, float], committed: Path, specs_dir: Path) -> Dict[str, float]:
    """Live specs only: sampled timings win, unsampled ones keep their committed timing."""
    live = {path.name for path in specs_dir.glob("*.spec.ts") if path.is_file()}
    if not live.intersection(measured):
        raise ValueError("The logs measured no live spec file")
    previous = json.loads(committed.read_text(encoding="utf-8"))
    merged = {name: previous[name] for name in live if name in previous}
    merged.update({name: seconds for name, seconds in measured.items() if name in live})
    return merged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="Print a shard's explicit spec paths")
    plan.add_argument("--shard", type=int, required=True, help="1-based shard index")
    plan.add_argument("--total", type=int, required=True)
    plan.add_argument("--kind", choices=("all", "a11y", "functional"), default="all")
    check = commands.add_parser("check", help="Verify coverage and print predicted balance")
    check.add_argument("--total", type=int, default=3)
    gain = commands.add_parser(
        "gain", help="Print seconds a refitted manifest takes off the slowest shard"
    )
    gain.add_argument("--total", type=int, required=True)
    gain.add_argument("--new", type=Path, required=True, help="Refitted manifest")
    for command in (plan, check, gain):
        command.add_argument("--specs-dir", type=Path, default=DEFAULT_SPECS)
        command.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    logs = commands.add_parser("from-logs", help="Regenerate duration JSON from CI logs")
    logs.add_argument("logs", type=Path, nargs="+")
    logs.add_argument(
        "--carry", type=Path,
        help="Committed manifest: keep its timings for live specs the logs did not measure",
    )
    logs.add_argument("--specs-dir", type=Path, default=DEFAULT_SPECS)
    args = parser.parse_args()
    try:
        if args.command == "from-logs":
            durations = from_logs(args.logs)
            if args.carry:
                durations = carry_forward(durations, args.carry, args.specs_dir)
            print(json.dumps(durations, sort_keys=True, indent=2))
            return 0
        weights = load_weights(args.specs_dir, args.manifest)
        if args.command == "gain":
            refit = load_weights(args.specs_dir, args.new)
            print("{:.1f}".format(plan_gain(weights, refit, args.total)))
            return 0
        shards = make_plan(weights, args.total)
        if args.command == "check":
            valid = check_plan(weights, shards)
            missing = unmeasured(args.specs_dir, args.manifest)
            # Drift shows up here before it shows up as a slow shard (PPS-229).
            if len(missing) > 0.10 * len(weights):
                print("WARNING: {} of {} spec files have no measured duration "
                      "(scheduled at the median): {}".format(
                          len(missing), len(weights), ", ".join(missing)))
            return 0 if valid else 1
        if not 1 <= args.shard <= args.total:
            raise ValueError("--shard must be between 1 and --total")
        for name in select_kind(shards[args.shard - 1], args.kind):
            print("tests/e2e/" + name)
        return 0
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    sys.exit(main())
