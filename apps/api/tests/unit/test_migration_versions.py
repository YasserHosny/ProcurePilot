from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path


def test_migration_versions_are_valid_and_unique() -> None:
    # File ancestry: unit -> tests -> api -> apps -> repository root.
    repo_root = Path(__file__).resolve().parents[4]
    migration_files = sorted((repo_root / "supabase" / "migrations").glob("*.sql"))

    assert migration_files, "supabase/migrations must contain at least one SQL migration"

    files_by_version: dict[str, list[Path]] = defaultdict(list)
    invalid: list[str] = []
    for migration_file in migration_files:
        version = migration_file.stem.split("_", maxsplit=1)[0]
        if re.fullmatch(r"\d{14}", version) is None:
            invalid.append(str(migration_file.relative_to(repo_root)))
        files_by_version[version].append(migration_file)

    assert not invalid, "Migration filenames must start with a 14-digit timestamp: " + ", ".join(
        invalid
    )

    duplicates = {version: files for version, files in files_by_version.items() if len(files) > 1}
    assert not duplicates, "Duplicate migration versions: " + "; ".join(
        f"{version}: {', '.join(str(path.relative_to(repo_root)) for path in files)}"
        for version, files in sorted(duplicates.items())
    )
