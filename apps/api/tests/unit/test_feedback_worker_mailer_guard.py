"""The feedback worker must not "send" the digest through the stub mailer on a real deployment.

With RFQ_MAILER_MODE unset, get_mailer() returns the in-memory FakeMailer. On staging or production
that would drop every digest silently while still advancing digest_last_sent_at, so the day's
feedback would never reach an operator. tick() skips the digest instead (and says so in the log);
retention and the orphan sweep still run. Locally the stub is the normal choice and runs as before.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

import pytest

from procurepilot_api.config import Settings
from procurepilot_api.shared.mailer import FakeMailer
from procurepilot_api.workers import feedback_worker

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=UTC)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def fake_job(name: str) -> Callable[..., dict[str, int]]:
        def run(*_args: object, **_kwargs: object) -> dict[str, int]:
            seen.append(name)
            return {"ran": 1}

        return run

    monkeypatch.setattr(feedback_worker, "run_digest", fake_job("digest"))
    monkeypatch.setattr(feedback_worker, "purge_retention", fake_job("retention"))
    monkeypatch.setattr(feedback_worker, "sweep_orphans", fake_job("orphans"))
    monkeypatch.setattr(feedback_worker, "get_mailer", FakeMailer)
    return seen


def _settings(env: str) -> Settings:
    return cast(Settings, SimpleNamespace(api_env=env))


@pytest.mark.parametrize("env", ["staging", "production"])
def test_digest_is_skipped_with_the_stub_mailer_on_a_deployment(
    calls: list[str], env: str, caplog: pytest.LogCaptureFixture
) -> None:
    results = feedback_worker.tick(_settings(env), remover=object(), now=NOW)
    assert calls == ["retention", "orphans"]
    assert results["digest"] == {"skipped_no_mailer": 1}
    assert "RFQ_MAILER_MODE" in caplog.text


def test_digest_runs_with_the_stub_mailer_locally(calls: list[str]) -> None:
    feedback_worker.tick(_settings("local"), remover=object(), now=NOW)
    assert calls == ["digest", "retention", "orphans"]


def test_an_explicit_mailer_is_always_used(calls: list[str]) -> None:
    feedback_worker.tick(_settings("production"), mailer=FakeMailer(), remover=object(), now=NOW)
    assert calls == ["digest", "retention", "orphans"]
