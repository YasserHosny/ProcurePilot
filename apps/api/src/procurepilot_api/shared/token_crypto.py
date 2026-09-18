"""Application-layer encryption for OAuth tokens at rest (shared across modules).

Used by both accounting (R3.1) and POS (R3.2) modules to encrypt external OAuth
tokens at rest before persisting to PostgreSQL.

When no key is configured (encryption_key is None or empty), encrypt/decrypt are
no-ops: the value passes through unchanged. This keeps stub-mode tests and
deployments without real external credentials working without requiring a key.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr


def encrypt_token(value: str, encryption_key: SecretStr | str | None = None) -> str:
    if encryption_key is None:
        return value
    raw_key = (
        encryption_key.get_secret_value()
        if isinstance(encryption_key, SecretStr)
        else str(encryption_key)
    )
    if not raw_key:
        return value
    fernet = Fernet(raw_key.encode("utf-8"))
    return fernet.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_token(value: str, encryption_key: SecretStr | str | None = None) -> str:
    if encryption_key is None:
        return value
    raw_key = (
        encryption_key.get_secret_value()
        if isinstance(encryption_key, SecretStr)
        else str(encryption_key)
    )
    if not raw_key:
        return value
    fernet = Fernet(raw_key.encode("utf-8"))
    try:
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # A stored value that isn't valid Fernet ciphertext under the current key — most likely
        # a plaintext token written before encryption was configured, or a key rotation. Return
        # it unchanged rather than crashing the sync; the next successful token refresh
        # re-encrypts it under the current key.
        return value
