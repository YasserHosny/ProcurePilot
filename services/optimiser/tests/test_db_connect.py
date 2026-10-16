"""psycopg connections go through ``procurepilot_optimiser_worker.db.connect`` only
(prepare_threshold=None for Supabase's transaction-mode pooler; see db.py)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import procurepilot_optimiser_worker
from procurepilot_optimiser_worker import db

PACKAGE_ROOT = Path(procurepilot_optimiser_worker.__file__).resolve().parent


def _direct_connect_calls(package_root: Path) -> list[str]:
    """Every psycopg connect call in the package outside db.py, as ``path:line``."""
    offenders: list[str] = []
    for path in sorted(package_root.rglob("*.py")):
        if path == package_root / "db.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        psycopg_names = {"psycopg"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                psycopg_names |= {a.asname for a in node.names if a.name == "psycopg" and a.asname}
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("psycopg"):
                # `from psycopg import connect` / `Connection` (whose .connect is the same thing)
                for alias in node.names:
                    if alias.name in {"connect", "Connection", "AsyncConnection"}:
                        offenders.append(f"{path}:{node.lineno} imports {alias.name}")
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr != "connect":
                continue
            target = node.func.value
            # psycopg.connect(...), psycopg.Connection.connect(...)
            while isinstance(target, ast.Attribute):
                target = target.value
            if isinstance(target, ast.Name) and target.id in psycopg_names:
                offenders.append(f"{path}:{node.lineno}")
    return offenders


def test_no_direct_psycopg_connect_outside_db_helper() -> None:
    offenders = _direct_connect_calls(PACKAGE_ROOT)
    assert offenders == [], "use procurepilot_optimiser_worker.db.connect:\n" + "\n".join(offenders)


def test_connect_disables_prepared_statements_and_passes_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def _record(*args: object, **kwargs: object) -> str:
        calls.append((args, kwargs))
        return "conn"

    monkeypatch.setattr(db.psycopg, "connect", _record)

    assert db.connect("postgres://x", autocommit=True, prepare_threshold=5) == "conn"
    assert calls == [(("postgres://x",), {"autocommit": True, "prepare_threshold": None})]
