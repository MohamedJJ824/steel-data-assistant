#!/usr/bin/env python
"""Run one evaluation configuration, or all of them.

Usage:
    python scripts/run_eval.py --config c3
    python scripts/run_eval.py --all
    python scripts/run_eval.py --config c0 --limit 6 --no-judge   # smoke run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from steel_assistant.config import load_config  # noqa: E402
from steel_assistant.eval.runner import load_questions, run_evaluation  # noqa: E402
from steel_assistant.llm.factory import build_llm_client  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config" / "eval_configs"

CONFIGS = {
    "c0": "c0_baseline.yaml",
    "c1": "c1_fewshot.yaml",
    "c2": "c2_hybrid.yaml",
    "c3": "c3_rerank.yaml",
    "c4": "c4_tool_calling.yaml",
}


def main() -> int:
    """Run the requested configurations."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", choices=sorted(CONFIGS))
    parser.add_argument("--all", action="store_true", help="run every configuration")
    parser.add_argument("--limit", type=int, help="only the first N questions")
    parser.add_argument("--category", help="only questions in this category")
    parser.add_argument("--no-judge", action="store_true", help="skip LLM judge scoring")
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args()

    if not args.config and not args.all:
        parser.error("pass --config <name> or --all")

    names = sorted(CONFIGS) if args.all else [args.config]

    questions = load_questions()
    if args.category:
        questions = [q for q in questions if q["category"] == args.category]
    if args.limit:
        # Take from each category rather than the first N, so a smoke run still
        # exercises every code path.
        by_category: dict[str, list] = {}
        for question in questions:
            by_category.setdefault(question["category"], []).append(question)
        per_category = max(1, args.limit // max(len(by_category), 1))
        questions = [q for group in by_category.values() for q in group[:per_category]]

    client = build_llm_client()
    if not client.is_available():
        print("LLM backend is not reachable", file=sys.stderr)
        return 1

    summary = {}
    for name in names:
        settings = load_config(CONFIG_DIR / CONFIGS[name])
        print(f"\n{'=' * 72}")
        print(
            f"{name}: agent={settings.agent.mode} fewshot={settings.sql.fewshot} "
            f"retries={settings.sql.max_retries} retrieval={settings.retrieval.mode} "
            f"rerank={settings.retrieval.rerank}"
        )
        print(f"{len(questions)} questions, judge={'off' if args.no_judge else 'on'}")
        print("=" * 72, flush=True)

        metrics, _ = run_evaluation(
            name,
            client,
            settings,
            questions=questions,
            use_judge=not args.no_judge,
            use_mlflow=not args.no_mlflow,
        )
        summary[name] = metrics
        for key in sorted(k for k in metrics if k.startswith("overall_")):
            value = metrics[key]
            if isinstance(value, float):
                print(f"    {key[8:]:<28} {value:.3f}")

    out = REPO_ROOT / "eval" / "runs" / "summary.json"
    existing = json.loads(out.read_text()) if out.is_file() else {}
    existing.update(summary)
    out.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")
    print(f"\nsummary written to {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
