"""Evaluate the production Question Router against a CSV dataset."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services import question_router


QUESTION_TYPES = ("experience", "knowledge", "motivation", "case")
OUTPUT_FIELDS = ("question", "predicted_type", "expected_type", "correct", "error")


def classify_with_error(question: str, category: str | None = None) -> tuple[str, str]:
    """Call production classification while observing its intentionally safe fallback."""
    error = ""
    original = question_router.ai_client.structured_completion

    def tracked_completion(**kwargs: Any) -> Any:
        nonlocal error
        try:
            return original(**kwargs)
        except Exception as exc:
            # Keep the batch diagnostic safe: exception text can contain provider payloads.
            error = type(exc).__name__
            raise

    question_router.ai_client.structured_completion = tracked_completion
    try:
        predicted = question_router.classify_question(question, category)
    finally:
        question_router.ai_client.structured_completion = original
    return predicted, error


def evaluate_csv(input_path: Path, output_path: Path) -> dict[str, Any]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or "question" not in reader.fieldnames:
            raise ValueError("Input CSV must contain a 'question' column")
        rows = list(reader)

    results: list[dict[str, str]] = []
    for row_number, row in enumerate(rows, start=2):
        question = (row.get("question") or "").strip()
        expected = (row.get("expected_type") or "").strip().casefold()
        category = (row.get("category") or "").strip() or None
        predicted = ""
        error = ""
        if not question:
            error = f"row_{row_number}:empty_question"
        elif expected and expected not in QUESTION_TYPES:
            error = f"row_{row_number}:invalid_expected_type"
        else:
            try:
                predicted, error = classify_with_error(question, category)
            except Exception as exc:
                # Defensive isolation if production classification ever stops catching a provider failure.
                error = type(exc).__name__
        correct = ""
        if expected:
            correct = str(bool(predicted == expected and not error)).lower()
        results.append({
            "question": question,
            "predicted_type": predicted,
            "expected_type": expected,
            "correct": correct,
            "error": error,
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(results)

    summary = build_summary(results)
    summary["output_file"] = str(output_path.resolve())
    return summary


def build_summary(results: list[dict[str, str]]) -> dict[str, Any]:
    labeled = [row for row in results if row["expected_type"] in QUESTION_TYPES]
    correct = sum(row["correct"] == "true" for row in labeled)
    per_type: dict[str, dict[str, int | float]] = {}
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for question_type in QUESTION_TYPES:
        typed = [row for row in labeled if row["expected_type"] == question_type]
        typed_correct = sum(row["correct"] == "true" for row in typed)
        per_type[question_type] = {
            "total": len(typed),
            "correct": typed_correct,
            "accuracy": typed_correct / len(typed) if typed else 0.0,
        }
    for row in labeled:
        confusion[row["expected_type"]][row["predicted_type"] or "error"] += 1
    return {
        "rows": len(results),
        "total": len(labeled),
        "correct": correct,
        "accuracy": correct / len(labeled) if labeled else None,
        "per_question_type": per_type,
        "confusion": {expected: dict(counts) for expected, counts in confusion.items()},
        "misclassified_cases": [row for row in labeled if row["correct"] != "true"],
        "errors": sum(bool(row["error"]) for row in results),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch evaluate the production Question Router")
    parser.add_argument("input_csv", type=Path, help="UTF-8 CSV containing question and optional expected_type")
    parser.add_argument("--output", type=Path, default=Path("question_router_eval_results.csv"), help="Result CSV path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = evaluate_csv(args.input_csv, args.output)
    except (OSError, ValueError) as exc:
        print(f"Evaluation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
