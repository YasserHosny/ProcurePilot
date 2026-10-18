"""Normalises what services/optimiser stores in ``basket_split_job.result`` to the API contract.

The worker (a separate deployable that must not import this package) persists its own result
models; the API contract (``AdvancedBasketResult``) is the canonical shape the web renders.
Rows written by the worker, old or new, are adapted on read, so a stored result can never turn
``GET /baskets/{id}`` into a 500. Already-conforming results pass through untouched. A guard
test (tests/contract/test_basket_result_worker_contract.py) runs a real worker-produced result
through this path.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

_WORKER_ONLY_KEYS = ("rule_version", "advisory_only")
_KIND_ALIASES = {"mixed_currency": "currency_consistency"}
_RISK_NOTE_KEYS = {"high": "high_supplier_risk", "medium": "elevated_supplier_risk"}


def normalise_stored_result(result: object) -> object:
    if not isinstance(result, dict):
        return result
    if not _is_worker_advanced_result(result):
        return result
    out = {k: v for k, v in result.items() if k not in _WORKER_ONLY_KEYS}
    out["allocation"] = [_allocation(a) for a in result.get("allocation", [])]
    out["confidence"] = _confidence(result.get("confidence"))
    out["risk_notes"] = _risk_notes(result.get("risk_notes", []))
    out["infeasible_items"] = result.get("infeasible_items") or _infeasible_items(
        result.get("violated_constraints", [])
    )
    out["applied_constraints"] = [
        _constraint(c, violated=False)
        for c in result.get("applied_constraints", [])
        if not _is_solver_internal(c)
    ]
    out["violated_constraints"] = [
        _constraint(c, violated=True) for c in result.get("violated_constraints", [])
    ]
    return out


def _is_worker_advanced_result(result: dict[str, Any]) -> bool:
    return (
        "advisory_only" in result
        or "rule_version" in result
        or isinstance(result.get("confidence"), dict)
        or any(isinstance(note, dict) for note in result.get("risk_notes", []) or [])
        or any(
            "supplier_id" not in line
            for allocation in result.get("allocation", []) or []
            for line in allocation.get("lines", [])
        )
    ) and "applied_constraints" in result


def _infeasible_items(violations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-item violations (no offer / mixed currency) as the infeasible card's item list."""
    reasons = {
        "no_eligible_supplier": "no_offer_from_named_suppliers",
        "mixed_currency": "mixed_currency_offers",
    }
    items: list[dict[str, Any]] = []
    for violation in violations:
        reason = reasons.get(violation.get("kind"))
        product_id = violation.get("workspace_product_id")
        if reason is None or product_id is None:
            continue
        items.append(
            {
                "workspace_product_id": product_id,
                "requested_quantity": violation.get("requested_quantity") or "0",
                "reason": reason,
                # A violation does not say which suppliers lack an offer: mixed currency means
                # offers exist, and no eligible supplier can come from exclusions or risk
                # limits. Naming every requested supplier would misdiagnose both, so leave the
                # list empty and let the card show the reason instead.
                "missing_supplier_ids": [],
            }
        )
    return items


def _is_solver_internal(constraint: dict[str, Any]) -> bool:
    """The solver reports its deterministic tie-break as a constraint; buyers never see it."""
    return "tie-break" in str(constraint.get("description", "")).lower()


def _allocation(allocation: dict[str, Any]) -> dict[str, Any]:
    supplier_id = allocation["supplier_id"]
    return {
        **allocation,
        "lines": [{"supplier_id": supplier_id, **line} for line in allocation.get("lines", [])],
    }


def _confidence(value: object) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return "low"
    if value.get("insufficient_evidence"):
        return "low"
    try:
        score = Decimal(str(value.get("score")))
    except InvalidOperation:
        return "low"
    if score >= Decimal("0.8"):
        return "high"
    return "medium" if score >= Decimal("0.5") else "low"


def _risk_notes(notes: list[Any]) -> list[str]:
    keys: list[str] = []
    for note in notes:
        if isinstance(note, str):
            key: str | None = note
        else:
            key = _RISK_NOTE_KEYS.get(note.get("severity"))
        if key is not None and key not in keys:
            keys.append(key)
    return keys


def _constraint(value: dict[str, Any], *, violated: bool) -> dict[str, Any]:
    out = {k: v for k, v in value.items() if k not in ("message", "requested_quantity")}
    out["kind"] = _KIND_ALIASES.get(value["kind"], value["kind"])
    message = value.get("message")
    if "description" not in out:
        out["description"] = message or value["kind"]
    if violated and "reason" not in out:
        out["reason"] = message or value["kind"]
    return out
