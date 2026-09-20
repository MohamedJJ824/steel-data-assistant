#!/usr/bin/env python
"""Execute every gold SQL query and store its result.

Two jobs, both required by the plan before any evaluation is trusted:

1. Every `gold_sql` is run once and must return a non-empty result. A gold
   query that silently returns zero rows would mark a correct answer wrong.
2. A leakage check against `eval/sql_fewshot.yaml`. An evaluation question that
   paraphrases a few-shot example inflates every SQL metric, so the check
   compares both normalised text and embedding similarity.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from steel_assistant.db.engine import assistant_engine  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = REPO_ROOT / "eval" / "questions.jsonl"
FEWSHOT = REPO_ROOT / "eval" / "sql_fewshot.yaml"
GOLD_DIR = REPO_ROOT / "eval" / "gold_results"

SIMILARITY_LIMIT = 0.90


def load_questions() -> list[dict]:
    """Read the evaluation set."""
    return [
        json.loads(line)
        for line in QUESTIONS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def normalise(text_value: str) -> str:
    """Lowercase, strip accents and punctuation, for exact-overlap detection."""
    import unicodedata

    stripped = "".join(
        char
        for char in unicodedata.normalize("NFD", text_value.lower())
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(r"[^a-z0-9 ]+", " ", stripped).strip()


def check_leakage(questions: list[dict], *, use_embeddings: bool = True) -> list[str]:
    """Report evaluation questions that overlap a few-shot example."""
    examples = (yaml.safe_load(FEWSHOT.read_text(encoding="utf-8")) or {}).get("examples", [])
    example_texts = [e["question"] for e in examples]
    problems: list[str] = []

    normalised_examples = {normalise(t) for t in example_texts}
    for question in questions:
        if normalise(question["question"]) in normalised_examples:
            problems.append(f"{question['id']}: identical text to a few-shot example")

    if use_embeddings and example_texts:
        from steel_assistant.retrieval.embedder import get_embedder

        embedder = get_embedder()
        example_vectors = embedder.embed_queries(example_texts)
        question_vectors = embedder.embed_queries([q["question"] for q in questions])
        for question, vector in zip(questions, question_vectors, strict=True):
            similarities = example_vectors @ vector
            best = int(similarities.argmax())
            if float(similarities[best]) > SIMILARITY_LIMIT:
                problems.append(
                    f"{question['id']}: {float(similarities[best]):.3f} similar to "
                    f"few-shot {example_texts[best]!r}"
                )
    return problems


def main() -> int:
    """Run the gold queries and the leakage check."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-embeddings", action="store_true")
    args = parser.parse_args()

    questions = load_questions()
    print(f"{len(questions)} questions")

    print("\nLeakage check against eval/sql_fewshot.yaml")
    problems = check_leakage(questions, use_embeddings=not args.skip_embeddings)
    if problems:
        print(f"  {len(problems)} OVERLAP(S):", file=sys.stderr)
        for problem in problems:
            print(f"    - {problem}", file=sys.stderr)
        return 1
    print(f"  no overlap above {SIMILARITY_LIMIT} similarity")

    print("\nExecuting gold SQL")
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    engine = assistant_engine()
    failures = []
    executed = 0

    with engine.connect() as conn:
        for question in questions:
            gold_sql = question.get("gold_sql")
            if not gold_sql:
                continue
            try:
                result = conn.execute(text(gold_sql))
                columns = list(result.keys())
                rows = [list(row) for row in result.fetchall()]
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{question['id']}: {str(exc)[:120]}")
                conn.rollback()
                continue
            conn.rollback()

            if not rows:
                failures.append(f"{question['id']}: gold query returned no rows")
                continue

            (GOLD_DIR / f"{question['id']}.json").write_text(
                json.dumps(
                    {"id": question["id"], "sql": gold_sql, "columns": columns, "rows": rows},
                    ensure_ascii=False,
                    default=str,
                    indent=2,
                ),
                encoding="utf-8",
            )
            executed += 1
            preview = str(rows[0])[:58]
            print(f"  {question['id']}  {len(rows):>3} rows  {preview}")

    if failures:
        print(f"\n{len(failures)} GOLD QUERY FAILURE(S):", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(f"\n{executed} gold results written to {GOLD_DIR.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
