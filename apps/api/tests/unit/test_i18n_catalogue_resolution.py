from pathlib import Path

import pytest

from procurepilot_api.shared import i18n


def test_catalogues_resolve_and_translate_rfq_and_digest_keys() -> None:
    i18n.find_i18n_dir.cache_clear()
    i18n.load_translations.cache_clear()

    catalogue_dir = i18n.find_i18n_dir()
    assert (catalogue_dir / "en.json").is_file()
    assert (catalogue_dir / "ar.json").is_file()
    i18n.assert_catalogues_present()

    for key, variables in (
        ("rfq.email.subject", {"tenant": "X", "date": "D"}),
        ("digests.subject", {"periodStart": "X", "periodEnd": "D"}),
    ):
        result = i18n.t(key, "ar", **variables)
        assert result != key
        assert "X" in result


def test_assert_catalogues_present_rejects_empty_configured_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("I18N_DIR", str(tmp_path))
    monkeypatch.setattr(i18n, "_LOCALE_DIR_CANDIDATES", [])
    i18n.find_i18n_dir.cache_clear()
    i18n.load_translations.cache_clear()

    with pytest.raises(RuntimeError, match="en.json, ar.json"):
        i18n.assert_catalogues_present()

    i18n.find_i18n_dir.cache_clear()
    i18n.load_translations.cache_clear()
