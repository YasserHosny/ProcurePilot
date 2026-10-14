"""Fail when regenerated docs screenshots differ visually from the committed ones.

A byte comparison can never pass on CI: two runs of the same code differ by up to ~0.5% of
pixels (timestamps, seeded data). So each changed image is compared pixel-wise: it is stale only
if more than THRESHOLD_PCT of its pixels differ by more than LUMA_DELTA, if its size changed, or
if a file was added or removed. Run from the repo root after regenerating.
"""

from __future__ import annotations

import io
import subprocess
import sys

from PIL import Image, ImageChops

DIR = "docs/user/screenshots/"
THRESHOLD_PCT = 1.0
LUMA_DELTA = 24


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def main() -> int:
    changed = [
        line.split("\t") for line in git("diff", "--name-status", "--", DIR).decode().splitlines()
    ]
    untracked = git("ls-files", "--others", "--exclude-standard", "--", DIR).decode().split()
    failures: list[str] = [f"added: {path}" for path in untracked]
    for status, *paths in changed:
        path = paths[-1]
        if status != "M":
            failures.append(f"{status}: {path}")
            continue
        old = Image.open(io.BytesIO(git("show", f"HEAD:{path}"))).convert("RGB")
        new = Image.open(path).convert("RGB")
        if old.size != new.size:
            failures.append(f"resized {old.size} -> {new.size}: {path}")
            continue
        diff = ImageChops.difference(old, new).convert("L").point(lambda v: 255 if v > LUMA_DELTA else 0)
        pct = 100 * diff.histogram()[255] / (new.size[0] * new.size[1])
        print(f"{pct:6.3f}%  {path}")
        if pct > THRESHOLD_PCT:
            failures.append(f"{pct:.2f}% of pixels changed (limit {THRESHOLD_PCT}%): {path}")
    if failures:
        print("\n".join(failures))
        return 1
    print(f"Screenshots match within {THRESHOLD_PCT}% -- no drift.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
