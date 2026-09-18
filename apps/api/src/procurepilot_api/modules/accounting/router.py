"""Router for accounting integration endpoints (R3.1)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/accounting", tags=["accounting"])
