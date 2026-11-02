"""Read every row of a PostgREST query, past the server's per-response cap."""

from __future__ import annotations

from collections.abc import Callable

# PostgREST returns at most `max_rows` rows per response (supabase/config.toml, and the hosted
# project's API setting), without an error. Keep this equal to it: a short page ends the read.
PAGE_ROWS = 1000


def all_rows(
    build: Callable[[], object], parse: Callable[[object], list[dict[str, object]]]
) -> list[dict[str, object]]:
    """Page `build()` (a fresh query with a stable order) with `.range()` until a short page."""
    rows: list[dict[str, object]] = []
    start = 0
    while True:
        page = parse(build().range(start, start + PAGE_ROWS - 1).execute().data)
        rows.extend(page)
        if len(page) < PAGE_ROWS:
            return rows
        start += PAGE_ROWS
