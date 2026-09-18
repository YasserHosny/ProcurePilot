"""Application-layer encryption for OAuth tokens at rest (R3.1 security review, T039).

access_token/refresh_token are stored in accounting_connection as plain text with no
encryption at rest — see config.py's accounting_token_encryption_key for the full reasoning
on why this is fixed here (Fernet, application-layer) rather than with Postgres's pgcrypto.

When no key is configured (accounting_token_encryption_key is None — the default, matching
every other QuickBooks setting's own None-by-default shape), encrypt/decrypt are no-ops: the
value passes through unchanged. This keeps stub-mode tests and any deployment that hasn't
configured a real QuickBooks connection working without requiring a key it doesn't need yet.
A real "quickbooks" mode deployment is expected to set this key.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from procurepilot_api.config import Settings


def encrypt_token(value: str, settings: Settings) -> str:
    key = settings.accounting_token_encryption_key
    if key is None:
        return value
    fernet = Fernet(key.get_secret_value().encode("utf-8"))
    return fernet.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_token(value: str, settings: Settings) -> str:
    key = settings.accounting_token_encryption_key
    if key is None:
        return value
    fernet = Fernet(key.get_secret_value().encode("utf-8"))
    try:
        return fernet.decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # A stored value that isn't valid Fernet ciphertext under the current key — most likely
        # a plaintext token written before encryption was configured, or a key rotation. Return
        # it unchanged rather than crashing the sync; the next successful token refresh
        # re-encrypts it under the current key.
        return value
