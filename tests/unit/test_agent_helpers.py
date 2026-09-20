"""Agent helpers that need no model."""

import pytest

from steel_assistant.agent.graph import detect_language
from steel_assistant.agent.prompts import ROUTER_SCHEMA, ROUTER_SYSTEM, synthesis_user_prompt


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Quelle est la consommation totale en mars 2018 ?", "fr"),
        ("Combien de tôles sur la ligne L2 ?", "fr"),
        ("Quel défaut a causé le plus d'arrêts ?", "fr"),
        ("How many plates had a Z_Scratch fault?", "en"),
        ("Which function computes the energy intensity KPI?", "en"),
        ("What is the peak load alert threshold?", "en"),
    ],
)
def test_language_detection(question, expected):
    assert detect_language(question) == expected


def test_router_schema_covers_every_category():
    assert set(ROUTER_SCHEMA["properties"]["category"]["enum"]) == {
        "sql",
        "docs",
        "code",
        "multi",
        "out_of_scope",
    }


def test_router_prompt_carries_examples():
    """Zero-shot classification measured 7/10 on the default model and 9/10
    with these examples, so their presence is load-bearing."""
    assert "Examples:" in ROUTER_SYSTEM
    for category in ("sql", "docs", "code", "multi", "out_of_scope"):
        assert f"-> {category}" in ROUTER_SYSTEM


def test_synthesis_prompt_includes_the_evidence():
    prompt = synthesis_user_prompt("Combien ?", ["--- SOURCE SQL ---\n402"])
    assert "Combien ?" in prompt
    assert "402" in prompt


def test_synthesis_prompt_handles_no_evidence():
    prompt = synthesis_user_prompt("Combien ?", [])
    assert "no tool returned any result" in prompt
