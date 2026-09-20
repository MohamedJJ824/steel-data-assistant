"""LLM-as-judge scoring for faithfulness and answer correctness.

Two caveats that belong in the report, not buried here:

1. On this hardware the judge is the same model that produced the answer, so it
   is grading its own work. That inflates scores and the report must say so.
   `llm.judge_model` exists precisely so a stronger judge can be configured.
2. Judge scores are the least reliable numbers in the evaluation. The
   deterministic metrics — SQL execution accuracy, routing, refusal, number
   grounding — should carry the weight of any conclusion.

The rubric is published here rather than paraphrased in the report, so the
scores can be argued with.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from steel_assistant.llm.base import LLMClient

FAITHFULNESS_SYSTEM = """You grade whether an answer is supported by its evidence.

Score 1 to 5:
5 — every claim in the answer is directly supported by the evidence.
4 — all substantive claims are supported; minor phrasing goes slightly beyond it.
3 — most claims are supported, but at least one is not traceable to the evidence.
2 — several claims are unsupported, or a number appears that is not in the evidence.
1 — the answer is largely unsupported or contradicts the evidence.

Judge ONLY whether the evidence supports the answer. Do not judge whether the
answer is factually true in the world, and do not reward or punish style.

Return JSON only: {"score": <1-5>, "reason": "<one sentence>"}"""

CORRECTNESS_SYSTEM = """You grade an answer against a reference answer.

Score 1 to 5:
5 — same substance as the reference; wording and detail may differ.
4 — substantially correct, missing a minor element of the reference.
3 — partially correct; one important element is wrong or missing.
2 — mostly incorrect, with a small overlap.
1 — wrong, or it declines to answer a question the reference answers.

Numbers matter: a different number is a different answer. Language does not:
a correct French answer to an English reference scores full marks.

Return JSON only: {"score": <1-5>, "reason": "<one sentence>"}"""

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 5},
        "reason": {"type": "string"},
    },
    "required": ["score", "reason"],
}

MAX_EVIDENCE_CHARS = 6000


@dataclass(slots=True)
class Judgement:
    """One judge verdict."""

    score: float | None
    reason: str = ""
    ok: bool = True


def _ask(client: LLMClient, system: str, user: str, model: str | None) -> Judgement:
    """Run one judge call and parse its verdict."""
    try:
        response = client.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            model=model,
            response_format=SCORE_SCHEMA,
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001 - a judge failure must not abort a run
        return Judgement(score=None, reason=f"judge call failed: {exc}", ok=False)

    try:
        payload = json.loads(response.content)
        score = float(payload["score"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        return Judgement(score=None, reason=f"unparseable verdict: {exc}", ok=False)

    if not 1.0 <= score <= 5.0:
        return Judgement(score=None, reason=f"score {score} out of range", ok=False)
    return Judgement(score=score, reason=str(payload.get("reason", "")))


def judge_faithfulness(
    client: LLMClient,
    question: str,
    answer: str,
    evidence: list[str],
    *,
    model: str | None = None,
) -> Judgement:
    """Score whether the answer is supported by the tool outputs."""
    if not answer.strip():
        return Judgement(score=1.0, reason="empty answer")
    joined = "\n\n".join(evidence)[:MAX_EVIDENCE_CHARS]
    user = f"Question:\n{question}\n\nEvidence:\n{joined}\n\nAnswer:\n{answer}"
    return _ask(client, FAITHFULNESS_SYSTEM, user, model)


def judge_correctness(
    client: LLMClient,
    question: str,
    answer: str,
    gold_answer: str,
    *,
    model: str | None = None,
) -> Judgement:
    """Score the answer against the reference answer."""
    if not answer.strip():
        return Judgement(score=1.0, reason="empty answer")
    user = (
        f"Question:\n{question}\n\nReference answer:\n{gold_answer}\n\nAnswer to grade:\n{answer}"
    )
    return _ask(client, CORRECTNESS_SYSTEM, user, model)
