from __future__ import annotations

import argparse
import json
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api import db
from procurepilot_api.config import get_settings
from procurepilot_api.modules.extraction.queue import enqueue_extraction_payload


def requeue(
    *, quotation_ids: list[UUID], tenant_id: UUID | None, all_refused: bool, dry_run: bool
) -> int:
    settings = get_settings()
    skipped = changed = 0
    with db.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("set local role service_role")
            if all_refused:
                cur.execute(
                    """select q.id, q.tenant_id, q.document_id, q.status,
                              j.id as failed_job_id, j.status as failed_job_status, j.error
                       from quotation q
                       left join lateral (
                         select id, status, error from extraction_job
                         where tenant_id=q.tenant_id and quotation_id=q.id
                         order by created_at desc, id desc limit 1
                       ) j on true
                       where q.tenant_id=%s and q.status='refused' order by q.created_at""",
                    (tenant_id,),
                )
            else:
                cur.execute(
                    """select q.id, q.tenant_id, q.document_id, q.status,
                              j.id as failed_job_id, j.status as failed_job_status, j.error
                       from quotation q
                       left join lateral (
                         select id, status, error from extraction_job
                         where tenant_id=q.tenant_id and quotation_id=q.id
                         order by created_at desc, id desc limit 1
                       ) j on true where q.id = any(%s)""",
                    (quotation_ids,),
                )
            found = {UUID(str(row["id"])): dict(row) for row in cur.fetchall()}
        selected = (
            list(found.values()) if all_refused else [found[i] for i in quotation_ids if i in found]
        )
        for quote_id in quotation_ids:
            if quote_id not in found:
                print(f"skipped id={quote_id}: not found")
                skipped += 1
        eligible = []
        for quote in selected:
            error = quote.get("error")
            valid = (
                quote.get("document_id") is not None
                and quote.get("status") == "refused"
                and quote.get("failed_job_id") is not None
                and quote.get("failed_job_status") == "failed"
                and isinstance(error, dict)
                and error.get("code") == "extraction_failed"
            )
            if not valid:
                print(f"skipped id={quote['id']}: not eligible for extraction requeue")
                skipped += 1
                continue
            eligible.append(quote)
        for quote in eligible:
            print(
                f"{'would requeue' if dry_run else 'requeued'} id={quote['id']} "
                f"tenant={quote['tenant_id']}"
            )
            if dry_run:
                continue
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "update quotation set status='extracting' where id=%s and status='refused'",
                    (quote["id"],),
                )
                if cur.rowcount != 1:
                    conn.rollback()
                    print(f"skipped id={quote['id']}: quotation is no longer refused")
                    skipped += 1
                    continue
                cur.execute(
                    "insert into extraction_job (tenant_id, quotation_id, status) "
                    "values (%s,%s,'queued') returning id",
                    (quote["tenant_id"], quote["id"]),
                )
                new_job_id = UUID(str(cur.fetchone()[0]))
            conn.commit()
            try:
                enqueue_extraction_payload(
                    settings,
                    job_id=str(new_job_id),
                    tenant_id=str(quote["tenant_id"]),
                    quotation_id=str(quote["id"]),
                    document_id=str(quote["document_id"]),
                )
            except Exception as exc:
                with conn.cursor() as cur:
                    cur.execute("set local role service_role")
                    cur.execute(
                        "update extraction_job set status='failed', error=%s, "
                        "completed_at=now() where id=%s",
                        (Jsonb({"code": "redis_enqueue_failed", "message": str(exc)}), new_job_id),
                    )
                    cur.execute("update quotation set status='refused' where id=%s", (quote["id"],))
                conn.commit()
                print(f"skipped id={quote['id']}: redis enqueue failed")
                skipped += 1
                continue
            with conn.cursor() as cur:
                cur.execute("set local role authenticated")
                cur.execute(
                    "select set_config('request.jwt.claims', %s, true)",
                    (json.dumps({"tenant_id": str(quote["tenant_id"]), "role": "authenticated"}),),
                )
                cur.execute(
                    "select record_audit_event(%s, 'success'::audit_outcome, %s, null, "
                    "%s, %s, null)",
                    (
                        "quotation_extraction_requeued",
                        quote["tenant_id"],
                        "extraction-requeue@procurepilot.local",
                        Jsonb(
                            {"quotation_id": str(quote["id"]), "extraction_job_id": str(new_job_id)}
                        ),
                    ),
                )
            conn.commit()
            changed += 1
    action = "would_requeue" if dry_run else "requeued"
    print(f"summary: {action}={len(eligible) if dry_run else changed} skipped={skipped}")
    return 1 if skipped else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Requeue refused extraction failures")
    parser.add_argument("--quotation-id", action="append", type=UUID, default=[])
    parser.add_argument("--all-refused", action="store_true")
    parser.add_argument("--tenant-id", type=UUID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if (
        args.all_refused == bool(args.quotation_id)
        or (args.all_refused and args.tenant_id is None)
        or (not args.all_refused and args.tenant_id is not None)
    ):
        parser.error("choose --quotation-id one or more times, or --all-refused --tenant-id")
    raise SystemExit(
        requeue(
            quotation_ids=args.quotation_id,
            tenant_id=args.tenant_id,
            all_refused=args.all_refused,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
