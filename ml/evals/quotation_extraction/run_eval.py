from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any


@dataclass(frozen=True)
class FieldScore:
    confidence: float
    correct: bool


def run_eval(benchmark_path: Path) -> dict[str, object]:
    records = _load_records(benchmark_path)
    if not records:
        records = _placeholder_records()
    field_scores: list[FieldScore] = []
    exact_matches = 0
    arithmetic_passes = 0
    costs: list[float] = []
    for record in records:
        expected = record["expected"]
        actual = record["actual"]
        fields = _flatten_fields(actual)
        expected_fields = _flatten_fields(expected)
        document_exact = fields == expected_fields
        if document_exact:
            exact_matches += 1
        for key, actual_value in fields.items():
            expected_value = expected_fields.get(key)
            confidence = float(_confidence(actual, key))
            field_scores.append(
                FieldScore(confidence=confidence, correct=actual_value == expected_value)
            )
        if actual.get("arithmetic_status") == expected.get("arithmetic_status"):
            arithmetic_passes += 1
        costs.append(float(record.get("cost_usd", 0)))
    return {
        "benchmark_path": str(benchmark_path),
        "placeholder_only": not benchmark_path.exists(),
        "documents": len(records),
        "field_level_accuracy": _rate(score.correct for score in field_scores),
        "document_exact_match": exact_matches / len(records),
        "arithmetic_validation_pass_rate": arithmetic_passes / len(records),
        "cost_per_document_usd": mean(costs) if costs else 0.0,
        "ece": _expected_calibration_error(field_scores),
        "gate_status": (
            "not_validated_stub_provider_no_held_out_benchmark"
            if not benchmark_path.exists()
            else "reported"
        ),
    }


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _flatten_fields(document: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, value in document.get("header", {}).items():
        fields[f"header.{key}"] = value.get("value") if isinstance(value, dict) else value
    for index, line in enumerate(document.get("lines", []), start=1):
        for key, value in line.get("fields", {}).items():
            fields[f"line.{index}.{key}"] = value.get("value") if isinstance(value, dict) else value
    return fields


def _confidence(document: dict[str, Any], field_key: str) -> float:
    parts = field_key.split(".")
    if parts[0] == "header":
        return float(document["header"][parts[1]].get("confidence", 0))
    line = document["lines"][int(parts[1]) - 1]
    return float(line["fields"][parts[2]].get("confidence", 0))


def _rate(values: list[bool] | object) -> float:
    realised = list(values)
    return sum(1 for value in realised if value) / len(realised) if realised else 0.0


def _expected_calibration_error(scores: list[FieldScore], *, buckets: int = 10) -> float:
    if not scores:
        return 0.0
    ece = 0.0
    for bucket in range(buckets):
        lower = bucket / buckets
        upper = (bucket + 1) / buckets
        members = [
            score
            for score in scores
            if lower <= score.confidence < upper or (
                bucket == buckets - 1 and score.confidence == 1
            )
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
            "expected": {
                "header": {"currency": {"value": "GBP"}},
                "lines": [{"fields": {"quantity": {"value": "2"}}}],
                "arithmetic_status": "reconciled",
            },
            "actual": {
                "header": {"currency": {"value": "GBP", "confidence": 1.0}},
                "lines": [{"fields": {"quantity": {"value": "2", "confidence": 1.0}}}],
                "arithmetic_status": "reconciled",
            },
            "cost_usd": 0.0,
        }
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=Path("ml/benchmarks/quotation_extraction/heldout.jsonl"),
    )
    args = parser.parse_args()
    print(json.dumps(run_eval(args.benchmark), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
