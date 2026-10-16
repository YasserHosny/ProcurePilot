from __future__ import annotations

import re
import unicodedata
from pathlib import PurePath
from urllib.parse import quote


def _basename(filename: str) -> str:
    return filename.replace("\\", "/").split("/")[-1]


def safe_object_name(filename: str) -> str:
    """Return a deterministic, ASCII-only storage leaf name."""
    basename = _basename(filename)
    if basename in {".", ".."}:
        basename = ""
    stem, dot, suffix = basename.rpartition(".")
    if not dot or not stem:
        stem, suffix = basename, ""
    extension = suffix.lower() if re.fullmatch(r"[a-zA-Z0-9]{1,10}", suffix) else ""
    folded = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", folded)
    slug = re.sub(r"[-_]+", "-", slug).strip(".-_")[:80].strip(".-_") or "file"
    return f"{slug}.{extension}" if extension else slug


def display_filename(filename: str | None, *, fallback: str) -> str:
    value = unicodedata.normalize("NFC", _basename(filename or ""))
    value = "".join(char for char in value if unicodedata.category(char)[0] != "C").strip()
    if not value:
        value = fallback
    if len(value) <= 255:
        return value
    suffix = PurePath(value).suffix
    if len(suffix) >= 255:
        return value[:255]
    return value[: 255 - len(suffix)] + suffix


def content_disposition(filename: str, disposition: str = "attachment") -> str:
    safe = display_filename(filename, fallback="file")
    ascii_name = safe.encode("ascii", "replace").decode("ascii")
    ascii_name = re.sub(r"[^\x20-\x7e]", "_", ascii_name).strip() or "file"
    ascii_name = ascii_name.replace("\\", "\\\\").replace('"', '\\"')
    return f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(safe, safe='')}"
