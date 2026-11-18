"""Byte-level helpers shared by the feedback unit and integration tests.

No database import at module level: unit tests use this too.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "feedback"

MIB = 1024 * 1024


def audio_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def jpeg_bytes(extra: int = 0) -> bytes:
    """A tiny JPEG that libmagic reports as image/jpeg, padded to be `extra` bytes longer."""
    core = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    return core + b"\x00" * extra + b"\xff\xd9"


def png_bytes(extra: int = 0) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\xff\x00\x00")
    pad = chunk(b"tEXt", b"x\x00" + b"a" * extra) if extra else b""
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + pad
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def webp_bytes(extra: int = 0) -> bytes:
    """A minimal lossless WebP container (VP8L) padded with a trailing unknown chunk."""
    vp8l = b"\x2f\x00\x00\x00\x00\x00\x00\x00"
    body = b"WEBP" + b"VP8L" + struct.pack("<I", len(vp8l)) + vp8l
    if extra:
        padding = b"\x00" * extra
        if extra % 2:
            padding += b"\x00"
        body += b"JUNK" + struct.pack("<I", extra) + padding
    return b"RIFF" + struct.pack("<I", len(body)) + body


GIF_BYTES = b"GIF89a\x01\x00\x01\x00\x00\x00\x00;"
SVG_BYTES = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'
PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
TEXT_BYTES = b"hello, this is plain text pretending to be a picture\n"
