from __future__ import annotations

import sys
from pathlib import Path


def test_worker_suite_is_isolated_from_apps_api_imports() -> None:
    optimiser_root = Path(__file__).resolve().parents[1]
    forbidden = optimiser_root.parents[1] / "apps" / "api" / "src"
    assert str(forbidden) not in sys.path
