from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class MatchScore:
    confidence: float
    correct: bool


def run_eval(benchmark_path: Path) -> dict[str, object]:
    records = _load_records(benchmark_path)
    placeholder_only = False
    if not records:
        records = _placeholder_records()
        placeholder_only = True

    auto_accepts: list[MatchScore] = []
    labelled_positive = 0
    recovered_positive = 0
    review_band = 0
    alias_hits = 0
    for record in records:
        expected_product_id = record.get("expected_workspace_product_id")
        if expected_product_id:
            labelled_positive += 1
        top = _top_candidate(record)
        route = str(record.get("route", "review"))
        if route == "review":
            review_band += 1
        if top and top.get("reasons", {}).get("alias_hit"):
            alias_hits += 1
        if top and expected_product_id and str(top.get("workspace_product_id")) == str(expected_product_id):
            recovered_positive += 1
        if route == "auto_accept" and top:
            auto_accepts.append(
                MatchScore(
                    confidence=float(top.get("confidence", 0)),
                    correct=str(top.get("workspace_product_id")) == str(expected_product_id),
                )
            )

    sufficient_benchmark = len(records) >= 500 and bool(benchmark_path.exists())
    return {
        "benchmark_path": str(benchmark_path),
        "placeholder_only": placeholder_only,
        "records": len(records),
        "precision_at_auto_accept": _rate(score.correct for score in auto_accepts),
        "recall": recovered_positive / labelled_positive if labelled_positive else 0.0,
        "review_band_size": review_band / len(records) if records else 0.0,
        "alias_hit_rate": alias_hits / len(records) if records else 0.0,
        "ece": _expected_calibration_error(auto_accepts),
        "minimum_required_records": 500,
        "requires_hard_negatives": True,
        "gate_status": "reported" if sufficient_benchmark else "not_validated_no_held_out_benchmark",
        "honest_gap": (
            "The 92% precision and 8% review-band gates cannot be validated until a real "
            "500+ item held-out product-matching benchmark with hard negatives exists."
        ),
    }


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _top_candidate(record: dict[str, Any]) -> dict[str, Any] | None:
    candidates = record.get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        return None
    top = max(candidates, key=lambda item: float(item.get("confidence", 0)))
    return top if isinstance(top, dict) else None


def _rate(values: object) -> float:
    realised = list(values)
    return sum(1 for value in realised if value) / len(realised) if realised else 0.0


def _expected_calibration_error(scores: list[MatchScore], *, buckets: int = 10) -> float:
    if not scores:
        return 0.0
    ece = 0.0
    for bucket in range(buckets):
        lower = bucket / buckets
        upper = (bucket + 1) / buckets
        members = [
            score
            for score in scores
            if lower <= score.confidence < upper
            or (bucket == buckets - 1 and score.confidence == 1)
        ]
        if not members:
            continue
        accuracy = sum(1 for score in members if score.correct) / len(members)
        avg_confidence = mean(score.confidence for score in members)
        ece += (len(members) / len(scores)) * abs(accuracy - avg_confidence)
    return ece


def _placeholder_records() -> list[dict[str, Any]]:
    return [
        {
            "line_id": "placeholder-line",
            "expected_workspace_product_id": "placeholder-product",
            "route": "auto_accept",
            "candidates": [
                {
                    "workspace_product_id": "placeholder-product",
                    "confidence": 1.0,
                    "reasons": {"alias_hit": True},
                }
            ],
        }
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("ml/benchmarks/product_matching/heldout.jsonl"),
    )
    args = parser.parse_args()
    print(json.dumps(run_eval(args.benchmark), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
