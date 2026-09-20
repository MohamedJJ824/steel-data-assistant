"""Streamlit interface for the Steel Plant Data Assistant.

Talks to the API over HTTP only — no database access and no model loading — so
the container stays small and the API remains the single place where
authorisation and logging happen.

The interface is in French, matching the intended users.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
import pandas as pd
import streamlit as st

API_URL = os.environ.get("SDA_API_URL", "http://localhost:8000")
API_KEY = os.environ.get("SDA_API__KEY", "")
TIMEOUT_S = float(os.environ.get("SDA_UI_TIMEOUT_S", "600"))

EXAMPLES = [
    ("Combien de tôles ont un défaut Bumps ?", "SQL"),
    ("Quelle est la consommation totale d'énergie en 2018 ?", "SQL"),
    ("Quelle est la durée de mise en attente pour une rayure en Z ?", "Documents"),
    ("Qui doit être alerté pour un défaut de gravité 3 ?", "Documents"),
    ("Quelle fonction calcule le MTTR ?", "Code"),
    ("Quel défaut a causé le plus d'arrêts, et que dit sa procédure ?", "Multi-outils"),
]

st.set_page_config(page_title="Assistant Données Aciérie", page_icon="🏭", layout="wide")


def call_api(path: str, payload: dict[str, Any] | None = None, method: str = "POST") -> Any:
    """Call the API, returning the parsed body or raising for the caller."""
    headers = {"X-API-Key": API_KEY}
    with httpx.Client(base_url=API_URL, timeout=TIMEOUT_S) as client:
        response = (
            client.post(path, json=payload, headers=headers)
            if method == "POST"
            else client.get(path, headers=headers)
        )
        response.raise_for_status()
        return response.json()


def render_sql(sql: dict[str, Any]) -> None:
    """Show the query, its result table and a CSV download."""
    st.code(sql["query"], language="sql")
    if sql.get("explanation"):
        st.caption(sql["explanation"])
    if sql.get("rows"):
        frame = pd.DataFrame(sql["rows"], columns=sql["columns"])
        st.dataframe(frame, use_container_width=True, hide_index=True)
        caption = f"{sql['row_count']} ligne(s) · {sql['exec_ms']} ms"
        if sql.get("truncated"):
            caption += f" · affichage limité à {len(sql['rows'])}"
        if sql.get("attempts", 1) > 1:
            caption += f" · {sql['attempts']} tentatives"
        st.caption(caption)
        st.download_button(
            "Télécharger en CSV",
            frame.to_csv(index=False).encode("utf-8"),
            file_name="resultat.csv",
            mime="text/csv",
            key=f"csv-{hash(sql['query'])}",
        )
    else:
        st.info("La requête n'a retourné aucune ligne.")


def render_doc_sources(sources: list[dict[str, Any]]) -> None:
    """Show cited document sections, each expandable to its full text."""
    for source in sources:
        label = f"{source['id']}"
        if source.get("section"):
            label += f" § {source['section']}"
        with st.expander(label):
            st.markdown(source.get("snippet", ""))
            if st.button("Voir le document complet", key=f"doc-{label}"):
                try:
                    document = call_api(f"/v1/sources/doc/{source['id']}", method="GET")
                    st.markdown(document["content"])
                except httpx.HTTPError as exc:
                    st.error(f"Document indisponible : {exc}")


def render_code_sources(sources: list[dict[str, Any]]) -> None:
    """Show cited code spans with their line numbers."""
    for source in sources:
        label = source["id"]
        if source.get("start_line"):
            label += f" : lignes {source['start_line']}-{source['end_line']}"
        with st.expander(label):
            language = "sql" if source["id"].endswith(".sql") else "python"
            st.code(source.get("snippet", ""), language=language)


def render_answer(result: dict[str, Any]) -> None:
    """Render one answer with all of its evidence."""
    st.markdown(result["answer"])

    grounding = result.get("grounding", {})
    checked = grounding.get("numbers_checked", 0)
    grounded = grounding.get("numbers_grounded", 0)
    columns = st.columns(4)
    columns[0].metric("Latence", f"{result['latency_ms'] / 1000:.1f} s")
    columns[1].metric("Catégorie", result.get("category") or "—")
    columns[2].metric("Langue", result.get("language", "—"))
    columns[3].metric("Chiffres vérifiés", f"{grounded}/{checked}" if checked else "—")

    if checked and grounded < checked:
        st.warning(
            "Certains chiffres de la réponse n'ont pas été retrouvés dans les "
            f"sources : {', '.join(grounding.get('ungrounded', []))}. "
            "Vérifiez la requête et les documents cités."
        )

    if result.get("sql"):
        with st.expander("Requête SQL", expanded=True):
            render_sql(result["sql"])

    docs = [s for s in result.get("sources", []) if s["type"] == "doc"]
    if docs:
        with st.expander(f"Documents cités ({len(docs)})"):
            render_doc_sources(docs)

    code = [s for s in result.get("sources", []) if s["type"] == "code"]
    if code:
        with st.expander(f"Code cité ({len(code)})"):
            render_code_sources(code)

    if result.get("tool_calls"):
        with st.expander("Outils appelés"):
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Outil": tc["tool"],
                            "OK": "oui" if tc["ok"] else "non",
                            "Durée (ms)": tc["latency_ms"],
                            "Détail": tc.get("summary") or tc.get("error") or "",
                        }
                        for tc in result["tool_calls"]
                    ]
                ),
                use_container_width=True,
                hide_index=True,
            )


def render_feedback(trace_id: str, index: int) -> None:
    """Thumbs up/down with an optional comment."""
    st.caption("Cette réponse vous a-t-elle été utile ?")
    columns = st.columns([1, 1, 6])
    rating = None
    if columns[0].button("👍", key=f"up-{index}"):
        rating = 1
    if columns[1].button("👎", key=f"down-{index}"):
        rating = -1
    comment = st.text_input("Commentaire (facultatif)", key=f"comment-{index}")
    if rating is not None:
        try:
            call_api(
                "/v1/feedback", {"trace_id": trace_id, "rating": rating, "comment": comment or None}
            )
            st.success("Merci, votre retour a été enregistré.")
        except httpx.HTTPError as exc:
            st.error(f"Retour non enregistré : {exc}")


# ------------------------------------------------------------------ sidebar --

with st.sidebar:
    st.title("🏭 Assistant Aciérie")
    st.caption("Questions sur la production, les procédures et le code d'analyse.")

    try:
        health = call_api("/health", method="GET")
        if health["status"] == "ok":
            st.success("Service opérationnel")
        else:
            st.warning("Service dégradé")
        st.caption(
            f"Modèle : `{health['agent_model']}`  \n"
            f"Backend : `{health['llm_backend']}`  \n"
            f"Base de données : {'connectée' if health['database'] else 'injoignable'}"
        )
    except httpx.HTTPError as exc:
        st.error(f"API injoignable : {exc}")

    st.divider()
    mode = st.radio(
        "Mode de l'agent",
        ["router", "tool_calling"],
        help="router classe la question puis appelle les outils. "
        "tool_calling laisse le modèle choisir.",
    )
    rerank = st.checkbox("Réordonnancement (plus lent)", value=False)

    st.divider()
    st.subheader("Exemples")
    for question, kind in EXAMPLES:
        if st.button(question, key=f"ex-{question}", use_container_width=True):
            st.session_state["pending"] = question
        st.caption(kind)

    st.divider()
    st.caption(
        "Les réponses s'appuient sur des données publiques et une couche "
        "synthétique. Aucune donnée d'entreprise réelle n'est utilisée."
    )

# --------------------------------------------------------------------- main --

st.title("Assistant Données Aciérie")
st.caption(
    "Posez une question en français ou en anglais. La réponse cite toujours "
    "sa source : la requête SQL exécutée, la section du document, ou les "
    "lignes de code concernées."
)

if "history" not in st.session_state:
    st.session_state["history"] = []

for index, entry in enumerate(st.session_state["history"]):
    with st.chat_message("user"):
        st.write(entry["question"])
    with st.chat_message("assistant"):
        render_answer(entry["result"])
        render_feedback(entry["result"]["trace_id"], index)

question = st.chat_input("Votre question…") or st.session_state.pop("pending", None)

if question:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Recherche en cours… (le modèle local peut prendre une minute)"):
            try:
                result = call_api(
                    "/v1/ask",
                    {
                        "question": question,
                        "options": {"agent_mode": mode, "rerank": rerank},
                    },
                )
            except httpx.HTTPError as exc:
                st.error(f"La requête a échoué : {exc}")
                result = None
        if result:
            st.session_state["history"].append({"question": question, "result": result})
            st.rerun()
