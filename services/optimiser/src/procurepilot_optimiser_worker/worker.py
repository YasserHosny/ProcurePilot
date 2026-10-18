from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from procurepilot_optimiser_worker import db
from procurepilot_optimiser_worker.repository import (
    NoCurrentOffersError,
    load_advanced_optimisation_input,
    load_job,
    mark_completed,
    mark_failed,
    mark_running,
    read_current_offers,
)
from procurepilot_optimiser_worker.settings import get_settings
from procurepilot_optimiser_worker.solver import solve_advanced_basket, solve_two_supplier_split

logger = logging.getLogger(__name__)


def process_basket_split_job(payload: dict[str, str]) -> None:
    settings = get_settings()
    job_id = UUID(payload["job_id"])
    tenant_id = UUID(payload["tenant_id"])
    raw_attempt = payload.get("attempt")
    attempt = datetime.fromisoformat(raw_attempt) if raw_attempt else None
    with db.connect(settings.database_url) as conn:
        try:
            claimed = mark_running(conn, job_id=job_id, attempt=attempt)
            conn.commit()
            if not claimed:
                # The API expired this attempt (or requeued the job under a newer one).
                logger.warning("skipping stale basket split delivery for job %s", job_id)
                return
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
            mark_completed(
                conn, job_id=job_id, result=result.model_dump(mode="json"), attempt=attempt
            )
            conn.commit()
        except NoCurrentOffersError as exc:
            mark_failed(
                conn,
                job_id=job_id,
                error={"code": "no_offers_for_products", "product_ids": exc.product_ids},
                attempt=attempt,
            )
            conn.commit()
            raise
        except Exception as exc:
            mark_failed(
                conn,
                job_id=job_id,
                error={"code": "basket_split_failed", "message": str(exc)},
                attempt=attempt,
            )
            conn.commit()
            raise


def _is_advanced_job(payload: dict[str, str]) -> bool:
    return (
        payload.get("request_kind") == "advanced_basket_optimisation"
        or payload.get("rule_version") == "advanced-basket-v1"
    )
