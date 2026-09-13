"""Seed a minimal landed_cost row for E2E price-history fixtures.

Drives the real append-only chain (document -> quotation -> quotation_line -> match_decision ->
landed_cost) against whichever database the caller points at. Invoked from support/db.ts.
"""

from __future__ import annotations

import json
import os
import re
import sys
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row


def _abort(message: str) -> None:
    print(message, file=sys.stderr)
    sys.exit(1)


def main() -> int:
    if len(sys.argv) != 5:
        _abort(
            "usage: seed_landed_cost.py <owner_email> <workspace_product_id> "
            "<unit_price> <currency>"
        )

    owner_email = sys.argv[1]
    workspace_product_id = sys.argv[2]
    unit_price = sys.argv[3]
    currency = sys.argv[4]

    if not re.fullmatch(r"^\d+(\.\d{1,4})?$", unit_price):
        _abort(f"invalid unit_price: {unit_price}")
    if not re.fullmatch(r"^[A-Z]{3}$", currency):
        _abort(f"invalid currency: {currency}")

    try:
        UUID(workspace_product_id)
    except ValueError:
        _abort(f"invalid workspace_product_id: {workspace_product_id}")

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        _abort("DATABASE_URL is not set")

    with psycopg.connect(dsn, row_factory=dict_row, sslmode="prefer") as conn:
        with conn.cursor() as cur:
            # Resolve owner tenant and membership.
            cur.execute(
                """
                select tenant_id, id as membership_id
                from membership
                where lower(email) = lower(%s) and status = 'active'
                limit 1
                """,
                (owner_email,),
            )
            owner = cur.fetchone()
            if not owner:
                _abort(f"no active membership for {owner_email}")

            tenant_id = str(owner["tenant_id"])
            membership_id = str(owner["membership_id"])
            storage_path = f"tenants/{tenant_id}/quotations/{uuid4()}"

            # 1. Document metadata.
            cur.execute(
                """
                insert into document (
                  id, tenant_id, storage_bucket, storage_path, mime_type,
                  source_channel, status, created_by
                )
                values (gen_random_uuid(), %s, 'quotations', %s, 'text/csv', 'upload', 'uploaded', %s)
                returning id
                """,
                (tenant_id, storage_path, membership_id),
            )
            document_id = str(cur.fetchone()["id"])

            # 2. Reviewed quotation.
            cur.execute(
                """
                insert into quotation (
                  id, tenant_id, document_id, status, reviewed_by, reviewed_at, currency
                )
                values (gen_random_uuid(), %s, %s, 'reviewed', %s, now(), %s)
                returning id
                """,
                (tenant_id, document_id, membership_id, currency),
            )
            quotation_id = str(cur.fetchone()["id"])

            # 3. Quotation line.
            cur.execute(
                """
                insert into quotation_line (
                  id, tenant_id, quotation_id, line_number, original_text,
                  quantity, unit_price_amount, unit_price_currency
                )
                values (
                  gen_random_uuid(), %s, %s, 1, 'E2E fixture', 1, %s, %s
                )
                returning id
                """,
                (tenant_id, quotation_id, unit_price, currency),
            )
            line_id = str(cur.fetchone()["id"])

            # 4. Match decision: the existing product is the match.
            cur.execute(
                """
                insert into match_decision (
                  id, tenant_id, quotation_line_id, matched_workspace_product_id,
                  outcome, is_automatic, decided_by, confidence
                )
                values (
                  gen_random_uuid(), %s, %s, %s::uuid,
                  'no_match_new_product', false, %s, 1
                )
                returning id
                """,
                (tenant_id, line_id, workspace_product_id, membership_id),
            )
            decision_id = str(cur.fetchone()["id"])

            # 5. Landed cost derived from the line.
            cur.execute(
                """
                insert into landed_cost (
                  id, tenant_id, quotation_line_id, match_decision_id,
                  quantity, normalised_base_quantity, base_unit,
                  unit_price_amount, unit_price_currency,
                  vat_amount, vat_currency,
                  delivery_fee_amount, delivery_fee_currency,
                  discount_amount, discount_currency,
                  other_charges_amount, other_charges_currency,
                  total_amount, total_currency,
                  raw_inputs, rule_version, valid_from
                )
                values (
                  gen_random_uuid(), %s, %s, %s,
                  1, 1, 'each',
                  %s, %s,
                  0, %s,
                  0, %s,
                  0, %s,
                  0, %s,
                  %s, %s,
                  '{}'::jsonb, 'landed-cost-v1', now()
                )
                returning id
                """,
                (
                    tenant_id,
                    line_id,
                    decision_id,
                    unit_price,
                    currency,
                    currency,
                    currency,
                    currency,
                    currency,
                    unit_price,
                    currency,
                ),
            )
            landed_cost_id = str(cur.fetchone()["id"])

    print(json.dumps({"id": landed_cost_id}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
