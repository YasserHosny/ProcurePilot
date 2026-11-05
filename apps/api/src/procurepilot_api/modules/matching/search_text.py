"""Folding and word-prefix matching for the match-queue search (P-152).

One definition of "the same text" for the in-process filters and the SQL filter, so an Arabic
search finds a Persian-keyboard spelling of the same word and neither path drifts.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Variant letter -> canonical letter. Keep the SQL ``translate`` in step: both read this table.
_LETTER_FOLDS: dict[str, str] = {
    "ي": "ي",  # ي stays
    "ی": "ي",  # ی (Persian yeh) -> ي
    "ى": "ي",  # ى (alef maksura) -> ي
    "ک": "ك",  # ک (Persian keheh) -> ك
    "أ": "ا",  # أ -> ا
    "إ": "ا",  # إ -> ا
    "آ": "ا",  # آ -> ا
    "ٱ": "ا",  # ٱ -> ا
    "ة": "ه",  # ة -> ه
}
_FOLD_FROM = "".join(k for k, v in _LETTER_FOLDS.items() if k != v)
_FOLD_TO = "".join(v for k, v in _LETTER_FOLDS.items() if k != v)
_TABLE = str.maketrans(_FOLD_FROM, _FOLD_TO)
_TASHKEEL_CLASS = "ً-ٰٟـ"  # harakat, dagger alef, tatweel
_TASHKEEL = re.compile(f"[{_TASHKEEL_CLASS}]")
# Whitespace, ASCII punctuation/symbols and the Arabic comma, semicolon and question mark.
_SEPARATOR_CLASS = r"\s!-/:-@\[-`{-~\u060c\u061b\u061f"
_SEPARATORS = re.compile(f"[{_SEPARATOR_CLASS}]+")


def fold_search_text(text: str) -> str:
    """Lower-case, strip tashkeel/tatweel and collapse Arabic/Persian letter variants."""
    return _TASHKEEL.sub("", text.lower()).translate(_TABLE)


def search_words(text: str) -> str:
    """Folded text with every separator run collapsed to one space (word boundaries)."""
    return _SEPARATORS.sub(" ", fold_search_text(text)).strip()


def search_matches(term: str, haystacks: Iterable[object]) -> bool:
    """True when the folded term starts a word (or a run of words) in any haystack."""
    needle = search_words(term)
    if not needle:
        return True
    for haystack in haystacks:
        if haystack is None:
            continue
        if f" {needle}" in f" {search_words(str(haystack))}":
            return True
    return False


def sql_fold_expression(column: str) -> str:
    """SQL twin of ``fold_search_text`` for a text column (identifier only, never user input)."""
    return (
        f"translate(regexp_replace(lower({column}), '[{_TASHKEEL_CLASS}]', '', 'g'), "
        f"'{_FOLD_FROM}', '{_FOLD_TO}')"
    )


def sql_word_expression(column: str) -> str:
    """SQL twin of ``search_words`` (before the caller adds the leading space)."""
    return (
        f"btrim(regexp_replace({sql_fold_expression(column)}, '[{_SEPARATOR_CLASS}]+', ' ', 'g'))"
    )
