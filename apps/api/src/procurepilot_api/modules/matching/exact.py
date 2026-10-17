"""Exact normalised-name rule (specs/004 research R5/R10 safe path).

A queued line whose text equals a catalogue product's name after normalisation
(NFKC, case-fold, whitespace collapsed) is an *exact name match*. It is NOT
auto-accepted — similarity-only matches never are — but it is surfaced as
"exact name match" so a buyer can confirm all of them in one human action.
Confirmation records a normal human `match_decision` and learns an alias, so the
same text auto-matches deterministically next time.
"""

from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalise_name(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    return _WHITESPACE.sub(" ", text).strip().casefold()


def is_exact_name_match(line_text: object, product_name: object) -> bool:
    normalised = normalise_name(line_text)
    return bool(normalised) and normalised == normalise_name(product_name)
