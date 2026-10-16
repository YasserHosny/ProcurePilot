from __future__ import annotations

import argparse
import json
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from procurepilot_api import db
from procurepilot_api.config import get_settings


def requeue(*, job_ids: list[UUID], tenant_id: UUID | None, dry_run: bool) -> int:
    settings = get_settings()
    skipped = 0
    changed = 0
    with db.connect(settings.database_url.get_secret_value()) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if tenant_id is not None:
                cur.execute(
                    "select id, tenant_id, status, job_type, payload, last_error "
                    "from ingestion_jobs where tenant_id = %s "
                    "and job_type = 'email_ingest' and status = 'failed' "
                    "and payload ? 'raw_email_path' order by created_at",
                    (tenant_id,),
                )
            else:
                cur.execute(
                    "select id, tenant_id, status, job_type, payload, last_error "
                    "from ingestion_jobs where id = any(%s)",
                    (job_ids,),
                )
            found = {UUID(str(row["id"])): dict(row) for row in cur.fetchall()}

        selected = (
            list(found.values())
            if tenant_id is not None
            else [found[i] for i in job_ids if i in found]
        )
        for job_id in job_ids:
            if job_id not in found:
                print(f"skipped id={job_id}: not found")
                skipped += 1
        valid = []
        for job in selected:
            if (
                job["job_type"] != "email_ingest"
                or job["status"] != "failed"
                or not isinstance(job["payload"], dict)
                or not job["payload"].get("raw_email_path")
            ):
                print(f"skipped id={job['id']}: wrong type, status, or missing raw_email_path")
                skipped += 1
                continue
            valid.append(job)

        for job in valid:
            previous = str(job["last_error"] or "")[:160]
            action = "would requeue" if dry_run else "requeued"
            print(f"{action} id={job['id']} tenant={job['tenant_id']} last_error={previous}")
            if dry_run:
                continue
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    "update ingestion_jobs set status='pending', attempts=0, last_error=null, "
                    "locked_by=null, locked_at=null, completed_at=null, updated_at=now() "
                    "where id=%s and job_type='email_ingest' and status='failed'",
                    (job["id"],),
                )
                if cur.rowcount != 1:
                    skipped += 1
                    continue
                cur.execute("set local role authenticated")
                cur.execute(
                    "select set_config('request.jwt.claims', %s, true)",
                    (json.dumps({"tenant_id": str(job["tenant_id"]), "role": "authenticated"}),),
                )
                cur.execute(
                    "select record_audit_event(%s, 'success'::audit_outcome, %s, null, "
                    "%s, %s, null)",
                    (
                        "email_ingest_requeued",
                        job["tenant_id"],
                        "email-ingestion-requeue@procurepilot.local",
                        Jsonb({"job_id": str(job["id"]), "previous_error": previous}),
                    ),
                )
            conn.commit()
            changed += 1
    action = "would_requeue" if dry_run else "requeued"
    count = len(valid) if dry_run else changed
    print(f"summary: {action}={count} skipped={skipped}")
    return 1 if skipped else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Requeue failed raw email ingestion jobs")
    parser.add_argument("--job-id", action="append", type=UUID, default=[])
    parser.add_argument("--all-failed", action="store_true")
    parser.add_argument("--tenant-id", type=UUID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if (
        args.all_failed == bool(args.job_id)
        or (args.all_failed and args.tenant_id is None)
        or (not args.all_failed and args.tenant_id is not None)
    ):
        parser.error("choose --job-id one or more times, or --all-failed --tenant-id")
    raise SystemExit(requeue(job_ids=args.job_id, tenant_id=args.tenant_id, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
