"""P-152: Persian-keyboard yeh and kaf in a line's text are stored as the Arabic letters."""

from __future__ import annotations

from procurepilot_extraction_worker.worker import _normalise_line_text


def test_persian_yeh_and_keheh_become_arabic_yeh_and_kaf() -> None:
    assert _normalise_line_text("زیت کاک") == "زيت كاك"


def test_other_text_is_left_exactly_as_printed() -> None:
    text = "Olive oil 5L - زيت أرز ٥"
    assert _normalise_line_text(text) == text
