"""psycopg connections go through ``procurepilot_api.db.connect`` only.

Hosted DATABASE_URL is Supabase's transaction-mode pooler; psycopg's default auto-prepare
(prepare_threshold=5) makes connections that share a pooled backend fail with
``DuplicatePreparedStatement: prepared statement "_pg3_0" already exists`` — which broke
the products CSV import confirm on hosted. The helper forces prepare_threshold=None; this
guard keeps a new direct ``psycopg.connect`` from slipping back in.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import procurepilot_api
from procurepilot_api import db

PACKAGE_ROOT = Path(procurepilot_api.__file__).resolve().parent
TESTS_ROOT = Path(__file__).resolve().parents[1]


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
    package_offenders = _direct_connect_calls(PACKAGE_ROOT)
    assert TESTS_ROOT.is_dir()
    assert any(TESTS_ROOT.rglob("*.py")), f"no Python tests found under {TESTS_ROOT}"
    test_offenders = _direct_connect_calls(TESTS_ROOT)
    offenders = package_offenders + test_offenders
    assert offenders == [], (
        "open connections with procurepilot_api.db.connect (prepare_threshold=None for the "
        "Supabase transaction pooler), not psycopg directly:\n" + "\n".join(offenders)
    )


def test_guard_detects_direct_connect(tmp_path: Path) -> None:
    (tmp_path / "db.py").write_text("import psycopg\npsycopg.connect('x')\n")
    (tmp_path / "bad.py").write_text(
        "import psycopg\nimport psycopg as pg\nfrom psycopg import connect\n"
        "def f():\n    with psycopg.connect('x', prepare_threshold=None):\n        pass\n"
        "    pg.connect('x')\n    psycopg.Connection.connect('x')\n"
    )
    offenders = _direct_connect_calls(tmp_path)
    assert sorted(o.rsplit(":", 1)[-1] for o in offenders) == ["3 imports connect", "5", "7", "8"]


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __call__(self, *args: object, **kwargs: object) -> str:
        self.calls.append((args, kwargs))
        return "conn"


def test_connect_disables_prepared_statements_and_passes_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(db.psycopg, "connect", recorder)

    assert db.connect("postgres://x", autocommit=True, prepare_threshold=5) == "conn"

    assert recorder.calls == [(("postgres://x",), {"autocommit": True, "prepare_threshold": None})]


def test_connect_defaults_to_configured_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder()
    monkeypatch.setattr(db.psycopg, "connect", recorder)
    monkeypatch.setenv("DATABASE_URL", "postgres://configured")
    from procurepilot_api.config import get_settings

    get_settings.cache_clear()
    try:
        db.connect()
    finally:
        get_settings.cache_clear()

    assert recorder.calls == [(("postgres://configured",), {"prepare_threshold": None})]
