"""Seed local reference data and mint one platform invitation — task T018.

Local development only. Sign-up is invitation-gated (FR-033), so without a platform
invitation there is no way to create a workspace, even on your own machine.

Run from the repo root:

    pnpm db:seed
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sys
from datetime import UTC, datetime, timedelta

import psycopg
from psycopg.rows import dict_row

REGIONS: list[tuple[str, str, str]] = [
    ("GB", "United Kingdom", "المملكة المتحدة"),
    ("EG", "Egypt", "مصر"),
    ("AE", "United Arab Emirates", "الإمارات العربية المتحدة"),
]

CURRENCIES: list[tuple[str, str, str, int]] = [
    ("GBP", "Pound Sterling", "جنيه إسترليني", 2),
    ("EGP", "Egyptian Pound", "جنيه مصري", 2),
    ("AED", "UAE Dirham", "درهم إماراتي", 2),
]

TAX_MODELS: list[tuple[str, str, str, str]] = [
    ("uk_vat_standard", "UK VAT (standard)", "ضريبة القيمة المضافة بالمملكة المتحدة", "GB"),
    ("eg_vat_standard", "Egypt VAT (standard)", "ضريبة القيمة المضافة بمصر", "EG"),
    ("ae_vat_standard", "UAE VAT (standard)", "ضريبة القيمة المضافة بالإمارات", "AE"),
]


def hash_token(token: str) -> str:
    """Only the hash is stored, so a database read cannot yield a usable invitation (R6)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def main() -> int:
    as_json = "--json" in sys.argv
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL is not set. Copy .env.example to .env first.", file=sys.stderr)
        return 1

    invitation_token = secrets.token_urlsafe(32)
    ttl_days = int(os.environ.get("PLATFORM_INVITATION_TTL_DAYS", "7"))
    expires_at = datetime.now(UTC) + timedelta(days=ttl_days)
    email = os.environ.get("SEED_INVITATION_EMAIL", "pilot@example.test")

    with psycopg.connect(dsn, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.executemany(
            """
            insert into supported_region (code, label_en, label_ar)
            values (%s, %s, %s)
            on conflict (code) do nothing
            """,
            REGIONS,
        )
        cur.executemany(
            """
            insert into supported_currency (code, label_en, label_ar, minor_units)
            values (%s, %s, %s, %s)
            on conflict (code) do nothing
            """,
            CURRENCIES,
        )
        cur.executemany(
            """
            insert into supported_tax_model (code, label_en, label_ar, region_code)
            values (%s, %s, %s, %s)
            on conflict (code) do nothing
            """,
            TAX_MODELS,
        )
        cur.execute(
            """
            insert into platform_invitation (email, token_hash, expires_at)
            values (%s, %s, %s)
            returning id
            """,
            (email, hash_token(invitation_token), expires_at),
        )
        row = cur.fetchone()
        conn.commit()

    if as_json:
        # Machine-readable for the E2E global setup, which needs a fresh invitation to create
        # its own workspace rather than assuming one already exists.
        import json

        print(
            json.dumps(
                {
                    "invitation_token": invitation_token,
                    "invitation_id": str(row["id"]) if row else None,
                    "email": email,
                    "region": REGIONS[0][0],
                    "currency": CURRENCIES[0][0],
                    "tax_model": TAX_MODELS[0][0],
                }
            )
        )
        return 0

    print(
        f"Seeded {len(REGIONS)} regions, {len(CURRENCIES)} currencies, "
        f"{len(TAX_MODELS)} tax models."
    )
    print()
    print("Platform invitation created — single use, this token is shown ONCE:")
    print()
    print(f"    {invitation_token}")
    print()
    print(f"    id:         {row['id'] if row else 'unknown'}")
    print(f"    email:      {email}")
    print(f"    expires:    {expires_at.isoformat()}")
    print()
    print("Paste the token into the sign-up screen. Re-run this script for another.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
