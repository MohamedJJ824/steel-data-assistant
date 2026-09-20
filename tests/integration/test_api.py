"""End-to-end API tests.

The ones that need a model are marked `llm` and excluded from CI, where no
model is available and a single answer takes the better part of a minute.
"""

import os

import pytest

pytestmark = pytest.mark.db


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    if not os.environ.get("APP_RW_PASSWORD"):
        pytest.skip("APP_RW_PASSWORD not set")
    os.environ.setdefault("SDA_API__KEY", "test-key")
    from steel_assistant.api.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def key():
    return {"X-API-Key": os.environ.get("SDA_API__KEY", "test-key")}


def test_health_reports_dependencies(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["database"] is True


def test_ask_requires_a_key(client):
    assert client.post("/v1/ask", json={"question": "x"}).status_code == 401


def test_ask_rejects_a_wrong_key(client):
    response = client.post("/v1/ask", json={"question": "x"}, headers={"X-API-Key": "wrong"})
    assert response.status_code == 401


def test_ask_validates_the_body(client, key):
    assert client.post("/v1/ask", json={"question": ""}, headers=key).status_code == 422


def test_document_source_endpoint(client, key):
    response = client.get("/v1/sources/doc/PROC-FLT-ZSCR", headers=key)
    assert response.status_code == 200
    assert "Z_Scratch" in response.json()["content"]


def test_unknown_document_is_404(client, key):
    assert client.get("/v1/sources/doc/NOPE", headers=key).status_code == 404


def test_code_source_endpoint(client, key):
    response = client.get("/v1/sources/code", params={"path": "kpi_energy.py"}, headers=key)
    assert response.status_code == 200
    assert "energy_intensity" in response.json()["content"]


@pytest.mark.parametrize("path", ["../../../etc/passwd", "../../DECISIONS.md", "/etc/passwd"])
def test_path_traversal_is_blocked(client, key, path):
    response = client.get("/v1/sources/code", params={"path": path}, headers=key)
    assert response.status_code in (400, 404)


def test_feedback_rejects_an_unknown_trace(client, key):
    response = client.post(
        "/v1/feedback",
        json={"trace_id": "00000000-0000-0000-0000-000000000000", "rating": 1},
        headers=key,
    )
    assert response.status_code == 404


@pytest.mark.llm
@pytest.mark.parametrize(
    ("question", "expect_sql"),
    [
        ("Combien de tôles ont un défaut Bumps ?", True),
        ("Quelle est la durée de mise en attente pour une rayure en Z ?", False),
    ],
)
def test_ask_end_to_end(client, key, question, expect_sql):
    response = client.post("/v1/ask", json={"question": question}, headers=key)
    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["language"] == "fr"
    assert body["trace_id"]
    if expect_sql:
        assert body["sql"] is not None
        assert body["sql"]["row_count"] >= 1


@pytest.mark.llm
def test_out_of_scope_is_declined(client, key):
    from steel_assistant.eval.metrics import is_refusal

    response = client.post(
        "/v1/ask",
        json={"question": "Quel est le prix actuel de la tonne d'acier ?"},
        headers=key,
    )
    assert response.status_code == 200
    assert is_refusal(response.json()["answer"])


@pytest.mark.llm
def test_feedback_round_trip(client, key):
    ask = client.post(
        "/v1/ask", json={"question": "How many production lines are there?"}, headers=key
    )
    trace_id = ask.json()["trace_id"]
    response = client.post(
        "/v1/feedback",
        json={"trace_id": trace_id, "rating": 1, "comment": "ok"},
        headers=key,
    )
    assert response.status_code == 201
