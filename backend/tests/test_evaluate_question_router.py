from __future__ import annotations

import csv

from scripts import evaluate_question_router as evaluator


def read_results(path):
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def test_batch_evaluation_reuses_router_writes_results_and_metrics(tmp_path, monkeypatch):
    source = tmp_path / "questions.csv"
    output = tmp_path / "results.csv"
    source.write_text(
        "question,expected_type\n"
        "Tell me about a time you led a team,experience\n"
        "What is RAG?,knowledge\n"
        "Why do you want this role?,motivation\n"
        "Walk me through your resume,experience\n"
        "Estimate this market size,case\n",
        encoding="utf-8",
    )
    calls = []
    production_classifier = evaluator.question_router.classify_question

    def observed(question, category=None):
        calls.append((question, category))
        return production_classifier(question, category)

    monkeypatch.setattr(evaluator.question_router, "classify_question", observed)
    summary = evaluator.evaluate_csv(source, output)
    rows = read_results(output)

    assert len(calls) == 5
    assert [row["predicted_type"] for row in rows] == ["experience", "knowledge", "motivation", "experience", "case"]
    assert all(row["correct"] == "true" for row in rows)
    assert summary["total"] == summary["correct"] == 5
    assert summary["accuracy"] == 1.0
    assert summary["per_question_type"]["case"]["accuracy"] == 1.0
    assert summary["misclassified_cases"] == []


def test_api_failure_is_recorded_without_stopping_later_rows(tmp_path, monkeypatch):
    source = tmp_path / "questions.csv"
    output = tmp_path / "results.csv"
    source.write_text(
        "question,expected_type\n"
        "An ambiguous prompt,case\n"
        "What is an index?,knowledge\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        evaluator.question_router.ai_client,
        "structured_completion",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("SECRET provider response")),
    )

    summary = evaluator.evaluate_csv(source, output)
    rows = read_results(output)

    assert rows[0]["predicted_type"] == "knowledge"
    assert rows[0]["error"] == "RuntimeError"
    assert "SECRET" not in output.read_text(encoding="utf-8-sig")
    assert rows[1]["predicted_type"] == "knowledge"
    assert rows[1]["error"] == ""
    assert summary["errors"] == 1
    assert summary["total"] == 2


def test_unlabeled_and_invalid_rows_are_isolated(tmp_path):
    source = tmp_path / "questions.csv"
    output = tmp_path / "results.csv"
    source.write_text(
        "question,expected_type\n"
        "What is RAG?,\n"
        ",knowledge\n"
        "Why this role?,unsupported\n",
        encoding="utf-8",
    )

    summary = evaluator.evaluate_csv(source, output)
    rows = read_results(output)

    assert rows[0]["predicted_type"] == "knowledge" and rows[0]["correct"] == ""
    assert rows[1]["error"].endswith("empty_question")
    assert rows[2]["error"].endswith("invalid_expected_type")
    assert summary["rows"] == 3
    assert summary["total"] == 1
    assert summary["errors"] == 2
