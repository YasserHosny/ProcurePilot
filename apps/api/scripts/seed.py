"""Seed local reference data, mint one platform invitation, and seed the reporting demo rows.

Local development only. Sign-up is invitation-gated (FR-033), so without a platform
invitation there is no way to create a workspace, even on your own machine.

The R2.5 reporting demo (task T006) seeds, into the first workspace that exists (the one
you created by signing up with the invitation): one savings_ledger report schedule and one
weekly-digest subscription, both deliberately past due so the Wave 17 scheduler ticks them
on its first run, plus the verified saving they report on. Re-running is a no-op for every
row — each is guarded by a natural key or a marker. If no workspace exists yet, the
reporting section is skipped with a note; the invitation and reference data are still
seeded.

Run from the repo root:

    pnpm db:seed
"""

from __future__ import annotations

import hashlib
import json
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


DEMO_SUPPLIER_NAME = "Demo Wholesale Foods"
DEMO_GTIN = "000000000001"  # GTIN-12 shape; a demo marker, not a real catalogue code
DEMO_MARKER = "r2.5-reporting-demo-seed"


def canonical_filters_digest(filters: dict[str, object]) -> str:
    """sha256 of the canonical filters JSON (data-model.md: computed by the API).

    The canonicalisation is part of the contract, not an implementation detail: report
    uniqueness rides on it. The API-side computation (reports module, task T011) must be
    byte-identical — ``json.dumps(filters, sort_keys=True, separators=(",", ":"),
    ensure_ascii=False)`` — or a seeded schedule and an API-created schedule with the same
    filters would collide as two rows instead of one.
    """
    payload = json.dumps(filters, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def seed_reporting_demo(cur: psycopg.Cursor) -> dict[str, object] | None:
    """Seed the R2.5 reporting demo rows into the first workspace that exists (T006).

    Returns a summary dict, or None when no workspace exists yet (the seed's invitation
    section is the prerequisite: sign up first, then re-run to land the demo rows).
    """
    cur.execute(
        """
        select t.id as tenant_id, t.currency, t.default_locale, m.id as membership_id
        from tenant t
        join membership m
          on m.tenant_id = t.id
         and m.role = 'owner'
         and m.status = 'active'
        order by t.created_at
        limit 1
        """
    )
    workspace = cur.fetchone()
    if workspace is None:
        return None

    tenant_id = workspace["tenant_id"]
    currency = workspace["currency"]
    membership_id = workspace["membership_id"]
    now = datetime.now(UTC)
    yesterday = now - timedelta(days=1)

    # --- supplier (guarded by name) ----------------------------------------------
    cur.execute(
        "select id from supplier where tenant_id = %(t)s and name = %(n)s",
        {"t": tenant_id, "n": DEMO_SUPPLIER_NAME},
    )
    row = cur.fetchone()
    if row is None:
        cur.execute(
            """
            insert into supplier (tenant_id, name, payment_terms, lead_time_days, status)
            values (%(t)s, %(n)s, 'Net 30', 5, 'active')
            returning id
            """,
            {"t": tenant_id, "n": DEMO_SUPPLIER_NAME},
        )
        row = cur.fetchone()
    supplier_id = row["id"]

    # --- canonical + workspace product (guarded by GTIN / unique view) -----------
    cur.execute(
        """
        insert into canonical_product (brand, name, variant, gtin, base_unit)
        values ('Demo Mills', 'Basmati Rice 5kg', null, %(g)s, 'kilogram')
        on conflict do nothing
        """,
        {"g": DEMO_GTIN},
    )
    cur.execute("select id from canonical_product where gtin = %(g)s", {"g": DEMO_GTIN})
    canonical_id = cur.fetchone()["id"]

    cur.execute(
        """
        insert into workspace_product
          (tenant_id, canonical_product_id, tenant_name, preferred_supplier_id, status)
        values (%(t)s, %(c)s, 'Basmati Rice (demo)', %(s)s, 'active')
        on conflict (tenant_id, canonical_product_id) do nothing
        """,
        {"t": tenant_id, "c": canonical_id, "s": supplier_id},
    )
    cur.execute(
        """
        select id from workspace_product
        where tenant_id = %(t)s and canonical_product_id = %(c)s
        """,
        {"t": tenant_id, "c": canonical_id},
    )
    product_id = cur.fetchone()["id"]

    # --- one verified saving inside the last week (guarded by the notes marker) --
    cur.execute(
        "select 1 from purchase_record where tenant_id = %(t)s and notes = %(n)s",
        {"t": tenant_id, "n": DEMO_MARKER},
    )
    if cur.fetchone() is None:
        cur.execute(
            """
            insert into purchase_record (
              tenant_id, workspace_product_id, supplier_id, recorded_by,
              quantity, base_unit, unit_price_amount, unit_price_currency,
              total_paid_amount, total_paid_currency, delivery_result,
              ordered_at, delivered_at, recorded_at, notes
            )
            values (
              %(t)s, %(p)s, %(s)s, %(m)s,
              10, 'kilogram', 4.25, %(c)s,
              42.50, %(c)s, 'delivered',
              %(o)s, %(y)s, %(y)s, %(n)s
            )
            returning id
            """,
            {
                "t": tenant_id,
                "p": product_id,
                "s": supplier_id,
                "m": membership_id,
                "c": currency,
                "o": yesterday - timedelta(days=1),
                "y": yesterday,
                "n": DEMO_MARKER,
            },
        )
        purchase_id = cur.fetchone()["id"]
        cur.execute(
            """
            insert into saving_record (
              tenant_id, purchase_record_id, workspace_product_id, supplier_id,
              status, baseline_policy, baseline_source_landed_cost_ids,
              baseline_unit_price_amount, baseline_unit_price_currency,
              baseline_value_amount, baseline_value_currency,
              actual_value_amount, actual_value_currency,
              delta_amount, delta_currency,
              calculation_version, calculation_inputs,
              recorded_by, recorded_at, verified_by, verified_at
            )
            values (
              %(t)s, %(pc)s, %(p)s, %(s)s,
              'verified', 'last_paid', '{}',
              5.00, %(c)s,
              50.00, %(c)s,
              42.50, %(c)s,
              7.50, %(c)s,
              'seed-demo-v1', %(inputs)s,
              %(m)s, %(y)s, %(m)s, %(y)s
            )
            """,
            {
                "t": tenant_id,
                "pc": purchase_id,
                "p": product_id,
                "s": supplier_id,
                "c": currency,
                "m": membership_id,
                "y": yesterday,
                # Honest marker: this baseline did NOT come from the price-history read
                # model — it is seed data, and the inputs say so.
                "inputs": json.dumps({"source": "seed", "marker": DEMO_MARKER}),
            },
        )

    # --- one savings_ledger schedule, deliberately past due (T016 claim) --------
    schedule_filters: dict[str, object] = {"supplier_id": None, "branch_id": None}
    cur.execute(
        """
        insert into report_schedule (
          tenant_id, created_by_membership_id, kind, format,
          filters, filters_digest, weekday, status, next_run_at
        )
        values (
          %(t)s, %(m)s, 'savings_ledger', 'xlsx',
          %(f)s, %(d)s, %(w)s, 'active', %(nr)s
        )
        on conflict (tenant_id, created_by_membership_id, kind, format, filters_digest)
        do nothing
        """,
        {
            "t": tenant_id,
            "m": membership_id,
            "f": json.dumps(schedule_filters),
            "d": canonical_filters_digest(schedule_filters),
            "w": now.weekday(),  # Monday-based, matching the 0-6 CHECK
            "nr": now - timedelta(hours=1),  # past due: the scheduler ticks it first run
        },
    )

    # --- one weekly-digest subscription, also past due ---------------------------
    digest_filters: dict[str, object] = {}
    cur.execute(
        """
        insert into digest_subscription (
          tenant_id, membership_id, kind, locale, filters, filters_digest,
          channel, status, next_run_at
        )
        values (
          %(t)s, %(m)s, 'weekly_digest', %(l)s, %(f)s, %(d)s,
          'in_app', 'active', %(nr)s
        )
        on conflict (tenant_id, membership_id, kind, filters_digest) do nothing
        """,
        {
            "t": tenant_id,
            "m": membership_id,
            "l": workspace["default_locale"],
            "f": json.dumps(digest_filters),
            "d": canonical_filters_digest(digest_filters),
            "nr": now - timedelta(hours=1),
        },
    )

    return {
        "tenant_id": str(tenant_id),
        "supplier_id": str(supplier_id),
        "product_id": str(product_id),
        "currency": currency,
    }


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

    # Supabase's transaction-mode pooler can hand back sessions with prepared statement names
    # already present, so keep this one-shot seed script on simple protocol statements.
    with (
        psycopg.connect(
            dsn,
            row_factory=dict_row,
            prepare_threshold=None,
        ) as conn,
        conn.cursor() as cur,
    ):
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
        reporting = seed_reporting_demo(cur)
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
    if reporting is None:
        print("Reporting demo skipped: no workspace exists yet. Sign up with the invitation")
        print("above, then re-run pnpm db:seed to land the R2.5 demo rows.")
        print()
    else:
        print("R2.5 reporting demo (re-runnable, every row idempotent):")
        print(f"    workspace:        {reporting['tenant_id']}")
        print("    savings_ledger:   one xlsx schedule, active, past due (scheduler ticks it)")
        print("    weekly digest:    one in-app subscription, active, past due")
        print(
            f"    verified saving:  10 kg @ 4.25 {reporting['currency']} "
            f"(baseline 5.00, delta 7.50 {reporting['currency']})"
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
