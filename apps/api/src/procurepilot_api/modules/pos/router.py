"""Router for POS and inventory integration endpoints (R3.2).

No `from __future__ import annotations` here, deliberately — matching ingestion/router.py
and accounting/router.py. A slowapi @mutation_limiter.limit() decorator combined with
deferred (stringified) annotations breaks FastAPI/pydantic's forward-ref resolution for
plain Path/Query parameters.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/pos", tags=["pos"])
