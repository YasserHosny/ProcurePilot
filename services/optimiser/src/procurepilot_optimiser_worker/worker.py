from __future__ import annotations

from uuid import UUID

import psycopg

from procurepilot_optimiser_worker.repository import (
    load_advanced_optimisation_input,
    load_job,
    mark_completed,
    mark_failed,
    mark_running,
    read_current_offers,
)
from procurepilot_optimiser_worker.settings import get_settings
from procurepilot_optimiser_worker.solver import solve_advanced_basket, solve_two_supplier_split


def process_basket_split_job(payload: dict[str, str]) -> None:
    settings = get_settings()
    job_id = UUID(payload["job_id"])
    tenant_id = UUID(payload["tenant_id"])
    with psycopg.connect(settings.database_url) as conn:
        try:
            mark_running(conn, job_id=job_id)
            conn.commit()
            if _is_advanced_job(payload):
                input_payload = load_advanced_optimisation_input(
                    conn,
                    job_id=job_id,
                    tenant_id=tenant_id,
                )
                result = solve_advanced_basket(input_payload=input_payload)
            else:
                job = load_job(conn, job_id=job_id, tenant_id=tenant_id)
                offers = read_current_offers(conn, job=job)
                result = solve_two_supplier_split(
                    supplier_ids=job.supplier_ids,
                    items=job.items,
                    offers=offers,
                )
            mark_completed(conn, job_id=job_id, result=result.model_dump(mode="json"))
            conn.commit()
        except Exception as exc:
            mark_failed(
                conn,
                job_id=job_id,
                error={"code": "basket_split_failed", "message": str(exc)},
            )
            conn.commit()
            raise


def _is_advanced_job(payload: dict[str, str]) -> bool:
    return (
        payload.get("request_kind") == "advanced_basket_optimisation"
        or payload.get("rule_version") == "advanced-basket-v1"
    )
