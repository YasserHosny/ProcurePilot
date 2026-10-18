"""Stdlib-only regression tests for duration-balanced E2E sharding."""

from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import e2e_shard as shard


class E2EShardTests(unittest.TestCase):
    def cli(self, *args: str, cwd: Path = shard.ROOT) -> str:
        return subprocess.check_output(
            [sys.executable, str(Path(shard.__file__).resolve()), *args],
            cwd=cwd, text=True,
        )

    def test_deterministic_from_any_cwd(self) -> None:
        first = self.cli("plan", "--shard", "1", "--total", "3")
        with tempfile.TemporaryDirectory() as directory:
            second = self.cli("plan", "--shard", "1", "--total", "3", cwd=Path(directory))
        self.assertEqual(first, second)
        self.assertEqual(first.splitlines(), sorted(first.splitlines()))

    def test_real_partition(self) -> None:
        expected = Counter(
            "tests/e2e/" + path.name for path in shard.DEFAULT_SPECS.glob("*.spec.ts")
        )
        for total in (2, 3, 4):
            with self.subTest(total=total):
                actual = Counter()
                for index in range(1, total + 1):
                    actual.update(self.cli(
                        "plan", "--shard", str(index), "--total", str(total)
                    ).splitlines())
                self.assertEqual(actual, expected)

    def test_unknown_spec_uses_median_and_stale_entries_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "durations.json"
            manifest.write_text(json.dumps({
                "a.spec.ts": 10, "b.spec.ts": 30, "stale.spec.ts": 9999,
            }), encoding="utf-8")
            for name in ("a.spec.ts", "b.spec.ts", "unknown.spec.ts"):
                (root / name).touch()
            weights = shard.load_weights(root, manifest)
            self.assertEqual(weights, {"a.spec.ts": 10, "b.spec.ts": 30, "unknown.spec.ts": 20})
            scheduled = []
            for index in (1, 2):
                scheduled.extend(self.cli(
                    "plan", "--shard", str(index), "--total", "2",
                    "--specs-dir", str(root), "--manifest", str(manifest),
                ).splitlines())
            self.assertEqual(Counter(scheduled), Counter("tests/e2e/" + name for name in weights))

    def test_kind_filters_partition_each_shard(self) -> None:
        for index in range(1, 4):
            base = ("plan", "--shard", str(index), "--total", "3")
            all_files = set(self.cli(*base, "--kind", "all").splitlines())
            a11y = set(self.cli(*base, "--kind", "a11y").splitlines())
            functional = set(self.cli(*base, "--kind", "functional").splitlines())
            self.assertEqual(a11y | functional, all_files)
            self.assertFalse(a11y & functional)
            self.assertTrue(all("a11y" in name for name in a11y))
            self.assertTrue(all("a11y" not in name for name in functional))

    def test_real_predicted_imbalance_under_ten_percent(self) -> None:
        weights = shard.load_weights(shard.DEFAULT_SPECS, shard.DEFAULT_MANIFEST)
        totals = [sum(weights[name] for name in names) for names in shard.make_plan(weights, 3)]
        self.assertLess(max(totals) / min(totals), 1.10)

    def test_lpt_ties_use_name_then_lowest_shard_index(self) -> None:
        self.assertEqual(shard.make_plan({"c": 2, "b": 2, "a": 2}, 2), [["a", "c"], ["b"]])

    def test_check_rejects_duplicate_and_missing_files(self) -> None:
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertFalse(shard.check_plan({"a": 2, "b": 1}, [["a"], ["a"]]))

    def test_from_logs_sums_units_then_takes_median(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.log"
            second = Path(directory) / "second.log"
            first.write_text(
                "2026-10-18T12:00:00Z \x1b[32m✓ 1 [chrome] › tests/e2e/a.spec.ts:1:2 › one (500ms)\x1b[0m\n"
                "✓ 2 [chrome] › tests/e2e/a.spec.ts:3:4 › two (12.3s)\n"
                "✓ 3 [chrome] › tests/e2e/b.spec.ts:5:6 › three (1.5m)\n"
                "✘ 4 [chrome] › tests/e2e/failed.spec.ts:1:2 › failed (10s)\n"
                "unrelated output (20s)\n", encoding="utf-8",
            )
            second.write_text(
                "✓ 1 [chrome] › tests/e2e/a.spec.ts:1:2 › one (20s)\n",
                encoding="utf-8",
            )
            output = self.cli("from-logs", str(first), str(second))
            self.assertEqual(json.loads(output), {"a.spec.ts": 16.4, "b.spec.ts": 90.0})
            self.assertLess(output.index("a.spec.ts"), output.index("b.spec.ts"))
            self.assertIn("90.0", output)


if __name__ == "__main__":
    unittest.main()
