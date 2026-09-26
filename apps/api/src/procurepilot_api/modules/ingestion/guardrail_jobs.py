from __future__ import annotations

import json
import logging
from uuid import UUID

import psycopg

from procurepilot_api.config import Settings

logger = logging.getLogger(__name__)


def enqueue_guardrail_evaluation(
    settings: Settings, *, tenant_id: UUID, quotation_id: UUID
) -> None:
    """Best-effort enqueue after a match decision is durably created."""
    try:
        with psycopg.connect(settings.database_url.get_secret_value()) as conn:
            with conn.cursor() as cur:
                cur.execute("set local role service_role")
                cur.execute(
                    """
                    insert into ingestion_jobs (tenant_id, job_type, payload)
                    select %s, 'guardrail_eval', %s::jsonb
                    where exists (
                      select 1 from rfq_response
                      where tenant_id = %s and quotation_id = %s
                    )
                    """,
                    (
                        tenant_id,
                        json.dumps({"quotation_id": str(quotation_id)}),
                        tenant_id,
                        quotation_id,
                    ),
                )
            conn.commit()
    except Exception:
        logger.exception(
            "Failed to enqueue guardrail evaluation for quotation %s", quotation_id
        )
