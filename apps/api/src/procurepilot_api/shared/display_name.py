"""A member's name as colleagues see it (PPS-125).

membership_display_name_check (20261030000000) holds the database to the same rule: trimmed,
1-100 characters.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import StringConstraints

type DisplayName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
