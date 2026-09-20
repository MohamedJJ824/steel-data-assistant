"""API contract checks that need neither a database nor a model."""

import pytest
from pydantic import ValidationError

from steel_assistant.api.schemas import AskRequest, AskResponse, FeedbackRequest


def test_question_is_required_and_bounded():
    with pytest.raises(ValidationError):
        AskRequest(question="")
    with pytest.raises(ValidationError):
        AskRequest(question="x" * 2001)
    assert AskRequest(question="ok").question == "ok"


def test_rating_is_restricted_to_thumbs():
    for rating in (-1, 1):
        assert FeedbackRequest(trace_id="t", rating=rating).rating == rating
    with pytest.raises(ValidationError):
        FeedbackRequest(trace_id="t", rating=0)


def test_response_defaults_are_safe():
    response = AskResponse(trace_id="t", answer="a", language="fr")
    assert response.tool_calls == []
    assert response.sources == []
    assert response.sql is None
    assert response.grounding.numbers_checked == 0


def test_options_reject_an_unknown_mode():
    with pytest.raises(ValidationError):
        AskRequest(question="q", options={"agent_mode": "telepathy"})
