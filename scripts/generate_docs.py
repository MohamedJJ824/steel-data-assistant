#!/usr/bin/env python
"""Generate the French document corpus in corpus/docs/.

Split of responsibility, which matters for evaluation:

* **Every fact is injected by this script**, read straight from the database —
  event ids, dates, downtime, thresholds, counts, hold durations. Facts are
  written into front matter and fact tables deterministically.
* **The LLM writes only the connecting prose.** It is given the facts and told
  not to invent numbers.

That split is deliberate. If the model invented the numbers, no document could
be checked against the database and no evaluation question over these documents
would have a gold answer. It also means a model failure degrades a document's
prose, never its correctness: each section falls back to a fixed paragraph.

Usage:
    python scripts/generate_docs.py               # all 40 documents
    python scripts/generate_docs.py --no-llm      # facts and fallback prose only
    python scripts/generate_docs.py --only PROC   # one family at a time
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from steel_assistant.db.engine import superuser_engine  # noqa: E402
from steel_assistant.llm.base import LLMClient  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "corpus" / "docs"

# Checkable facts derived from severity. These mirror QUALITY_HOLD_HOURS in
# corpus/legacy_code/config_thresholds.py on purpose: a question can ask
# whether the procedure and the code agree, and they must.
HOLD_HOURS_BY_SEVERITY = {1: 4, 2: 24, 3: 72}
ROLE_BY_SEVERITY = {
    1: "l'opérateur de contrôle qualité",
    2: "le chef d'équipe qualité",
    3: "le responsable qualité de site",
}
INSPECTION_FREQUENCY_BY_SEVERITY = {
    1: "une fois par poste",
    2: "toutes les deux heures",
    3: "en continu jusqu'à la levée de la mise en attente",
}
ESCALATION_MINUTES_BY_SEVERITY = {1: 120, 2: 60, 3: 15}


def fr_number(value: float, decimals: int = 1) -> str:
    """Format a number the French way: thin space thousands, comma decimal.

    These are French documents, so 959636.7 must read as "959 636,7". The
    number-grounding check has to recognise this form when it looks for an
    answer's figures in the tool outputs.
    """
    formatted = f"{value:,.{decimals}f}"
    integer, _, fraction = formatted.partition(".")
    integer = integer.replace(",", "\u202f")
    return f"{integer},{fraction}" if fraction else integer


@dataclass(slots=True)
class Document:
    """One markdown file, ready to write."""

    doc_id: str
    title: str
    doc_type: str
    body: str
    version: str = "1.0"
    doc_date: date = date(2018, 6, 1)
    line_id: str | None = None
    fault_code: str | None = None
    event_id: int | None = None

    def render(self) -> str:
        """Front matter plus body."""
        lines = [
            "---",
            f"doc_id: {self.doc_id}",
            f"title: {self.title}",
            f"doc_type: {self.doc_type}",
        ]
        if self.line_id:
            lines.append(f"line_id: {self.line_id}")
        if self.fault_code:
            lines.append(f"fault_code: {self.fault_code}")
        if self.event_id is not None:
            lines.append(f"event_id: {self.event_id}")
        lines += [f"version: {self.version}", f"date: {self.doc_date.isoformat()}", "---", ""]
        return "\n".join(lines) + self.body.rstrip() + "\n"


# --------------------------------------------------------------------- prose --

SYSTEM_PROMPT = (
    "Tu rédiges de la documentation industrielle interne pour une aciérie, en "
    "français professionnel et sobre. Règles absolues :\n"
    "- N'invente AUCUN chiffre, date, nom de personne ou référence. "
    "N'utilise que les faits fournis.\n"
    "- Pas de titre, pas de liste à puces, pas de markdown : uniquement un ou "
    "deux paragraphes de texte courant.\n"
    "- Pas de formule de politesse, pas d'introduction du type « voici ».\n"
    "- Désigne les personnes par leur rôle, jamais par un nom."
)


def write_prose(
    client: LLMClient | None, instruction: str, facts: dict[str, Any], fallback: str
) -> str:
    """Ask the model for one or two paragraphs, falling back on failure."""
    if client is None:
        return fallback

    fact_lines = "\n".join(f"- {key} : {value}" for key, value in facts.items())
    user = f"{instruction}\n\nFaits disponibles (les seuls autorisés) :\n{fact_lines}"
    try:
        response = client.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001 - a slow local model must not abort a 40-doc run
        print(f"    LLM failed ({type(exc).__name__}), using fallback prose", file=sys.stderr)
        return fallback

    prose = response.content.strip()
    # A model that returns almost nothing, or that starts emitting markdown
    # structure, is worse than the deterministic fallback.
    if len(prose) < 80 or prose.lstrip().startswith(("#", "-", "*", "|")):
        return fallback
    return prose


# ----------------------------------------------------------------- db facts --


def fetch_facts() -> dict[str, Any]:
    """Read everything the documents must stay consistent with."""
    engine = superuser_engine()
    with engine.connect() as conn:
        faults = [
            dict(row._mapping)
            for row in conn.execute(
                text(
                    "SELECT f.fault_code, f.label_fr, f.label_en, f.severity, "
                    "       f.procedure_doc_id, count(p.plate_id) AS plate_count "
                    "FROM plant.fault_types f "
                    "LEFT JOIN plant.plate_inspections p ON p.fault_code = f.fault_code "
                    "GROUP BY f.fault_code, f.label_fr, f.label_en, f.severity, "
                    "         f.procedure_doc_id ORDER BY f.fault_code"
                )
            )
        ]
        lines = [
            dict(row._mapping)
            for row in conn.execute(
                text(
                    "SELECT line_id, name_fr, name_en, process, commissioned_year "
                    "FROM plant.production_lines ORDER BY line_id"
                )
            )
        ]
        reports = [
            dict(row._mapping)
            for row in conn.execute(
                text(
                    "SELECT m.event_id, m.line_id, m.started_at, m.ended_at, "
                    "       m.downtime_minutes, m.category, m.fault_code, "
                    "       m.report_doc_id, f.label_fr AS fault_label_fr, f.severity "
                    "FROM plant.maintenance_events m "
                    "LEFT JOIN plant.fault_types f ON f.fault_code = m.fault_code "
                    "WHERE m.report_doc_id IS NOT NULL ORDER BY m.event_id"
                )
            )
        ]
        shifts = [
            dict(row._mapping)
            for row in conn.execute(
                text(
                    "SELECT shift_code, label_fr, start_hour, end_hour "
                    "FROM plant.shifts ORDER BY shift_code"
                )
            )
        ]
        top_line_by_fault = {
            row[0]: (row[1], row[2])
            for row in conn.execute(
                text(
                    "SELECT DISTINCT ON (fault_code) fault_code, line_id, count(*) "
                    "FROM plant.plate_inspections GROUP BY fault_code, line_id "
                    "ORDER BY fault_code, count(*) DESC"
                )
            )
        }
        line_stats = {
            row[0]: {"plates": row[1], "top_fault": row[2]}
            for row in conn.execute(
                text(
                    "SELECT p.line_id, count(*) AS plates, "
                    "  (SELECT fault_code FROM plant.plate_inspections i "
                    "   WHERE i.line_id = p.line_id GROUP BY fault_code "
                    "   ORDER BY count(*) DESC LIMIT 1) AS top_fault "
                    "FROM plant.plate_inspections p GROUP BY p.line_id"
                )
            )
        }
        threshold = conn.execute(
            text(
                "SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY usage_kwh) "
                "FROM plant.energy_readings"
            )
        ).scalar_one()
        energy = dict(
            conn.execute(
                text(
                    "SELECT round(sum(usage_kwh)::numeric, 1) AS total_kwh, "
                    "       round(sum(co2_tco2)::numeric, 2) AS total_tco2, "
                    "       round(max(usage_kwh)::numeric, 2) AS max_kwh "
                    "FROM plant.energy_readings"
                )
            )
            .one()
            ._mapping
        )

    return {
        "faults": faults,
        "lines": lines,
        "reports": reports,
        "shifts": shifts,
        "top_line_by_fault": top_line_by_fault,
        "line_stats": line_stats,
        "peak_threshold_exact": float(threshold),
        "peak_threshold_rounded": int(round(float(threshold))),
        "energy": energy,
    }


# --------------------------------------------------------------- generators --


def build_procedures(facts: dict[str, Any], client: LLMClient | None) -> list[Document]:
    """One handling procedure per fault type (7 documents)."""
    docs = []
    for fault in facts["faults"]:
        code = fault["fault_code"]
        severity = fault["severity"]
        hold_hours = HOLD_HOURS_BY_SEVERITY[severity]
        role = ROLE_BY_SEVERITY[severity]
        frequency = INSPECTION_FREQUENCY_BY_SEVERITY[severity]
        escalation = ESCALATION_MINUTES_BY_SEVERITY[severity]
        top_line, top_count = facts["top_line_by_fault"].get(code, ("L1", 0))

        detection = write_prose(
            client,
            f"Rédige un paragraphe décrivant comment un opérateur détecte visuellement "
            f"le défaut « {fault['label_fr']} » sur une tôle en sortie de ligne.",
            {
                "défaut": fault["label_fr"],
                "code": code,
                "gravité": f"{severity} sur 3",
                "ligne la plus touchée": top_line,
            },
            f"Le défaut {fault['label_fr']} ({code}) est relevé au contrôle visuel en "
            f"sortie de ligne. Il est de gravité {severity} sur 3. La ligne {top_line} "
            f"est celle où il est le plus fréquemment constaté.",
        )
        causes = write_prose(
            client,
            f"Rédige un paragraphe sur les causes racines habituelles du défaut "
            f"« {fault['label_fr']} » en aciérie et les points à vérifier sur la ligne.",
            {"défaut": fault["label_fr"], "gravité": f"{severity} sur 3"},
            f"Les causes racines du défaut {fault['label_fr']} sont recherchées du côté "
            f"des réglages de ligne, de l'état des outillages et des conditions de "
            f"surface en amont. Le contrôle porte en priorité sur les équipements en "
            f"contact direct avec la tôle.",
        )

        body = textwrap.dedent(f"""
            # Procédure de traitement du défaut {fault["label_fr"]} ({code})

            ## Identification

            | | |
            |---|---|
            | Code du défaut | `{code}` |
            | Libellé | {fault["label_fr"]} |
            | Gravité | {severity} sur 3 |
            | Tôles concernées en 2018 | {fault["plate_count"]} |
            | Ligne la plus touchée | {top_line} ({top_count} tôles) |

            ## Détection

            {detection}

            ## Actions immédiates

            1. Isoler la tôle concernée et la marquer au poste de contrôle.
            2. Mettre la tôle en attente qualité pendant **{hold_hours} heures**.
            3. Prévenir {role}.
            4. Renforcer le contrôle visuel : {frequency}.

            ## Escalade

            Si le défaut réapparaît sur plus de trois tôles consécutives, alerter
            {role} dans un délai de **{escalation} minutes**. Au-delà de ce délai
            sans réponse, l'arrêt de la ligne est demandé au chef de poste.

            ## Causes racines

            {causes}

            ## Règles de mise en attente qualité

            La durée de mise en attente pour ce défaut est de **{hold_hours} heures**,
            conformément au barème par gravité. La levée de l'attente est prononcée
            par {role} après contrôle contradictoire.
            """).strip()

        docs.append(
            Document(
                doc_id=fault["procedure_doc_id"],
                title=f"Procédure de traitement des défauts {code}",
                doc_type="procedure",
                fault_code=code,
                version="1.2",
                doc_date=date(2018, 4, 11),
                body=body,
            )
        )
    return docs


def build_manuals(facts: dict[str, Any], client: LLMClient | None) -> list[Document]:
    """One operating manual per production line (3 documents)."""
    docs = []
    for line in facts["lines"]:
        line_id = line["line_id"]
        stats = facts["line_stats"].get(line_id, {"plates": 0, "top_fault": "-"})
        overview = write_prose(
            client,
            f"Rédige un paragraphe présentant le rôle de la ligne « {line['name_fr']} » "
            f"dans le flux de production d'une aciérie.",
            {
                "ligne": line["name_fr"],
                "procédé": line["process"],
                "mise en service": line["commissioned_year"],
            },
            f"La ligne {line_id} assure l'étape de {line['process']} dans le flux de "
            f"production. Mise en service en {line['commissioned_year']}, elle alimente "
            f"les étapes situées en aval.",
        )

        body = textwrap.dedent(f"""
            # Manuel d'exploitation — {line["name_fr"]} ({line_id})

            ## Présentation

            {overview}

            | | |
            |---|---|
            | Identifiant | `{line_id}` |
            | Procédé | {line["process"]} |
            | Mise en service | {line["commissioned_year"]} |
            | Tôles inspectées en 2018 | {stats["plates"]} |
            | Défaut le plus fréquent | `{stats["top_fault"]}` |

            ## Organisation des postes

            La ligne fonctionne en 3x8. Le poste du matin couvre 6h-14h, le poste
            d'après-midi 14h-22h et le poste de nuit 22h-6h. Le poste de nuit franchit
            minuit : les heures situées après minuit sont imputées à la journée de
            début de poste.

            ## Contrôles en début de poste

            1. Vérifier l'état des outillages en contact avec la tôle.
            2. Relever le facteur de puissance et signaler toute valeur inférieure à 92 %.
            3. Consulter les mises en attente qualité non levées du poste précédent.

            ## Défaut dominant sur cette ligne

            Le défaut le plus fréquemment relevé sur {line_id} est `{stats["top_fault"]}`.
            La procédure de traitement correspondante s'applique sans adaptation locale.

            ## Arrêts et maintenance

            Tout arrêt supérieur à 15 minutes est consigné au journal de maintenance
            avec sa cause, sa durée et, le cas échéant, le code du défaut à l'origine
            de l'intervention.
            """).strip()

        docs.append(
            Document(
                doc_id=f"MAN-{line_id}",
                title=f"Manuel d'exploitation — {line['name_fr']}",
                doc_type="manual",
                line_id=line_id,
                version="2.0",
                doc_date=date(2018, 2, 15),
                body=body,
            )
        )
    return docs


def build_reports(facts: dict[str, Any], client: LLMClient | None) -> list[Document]:
    """One maintenance report per event that has one (20 documents)."""
    docs = []
    for report in facts["reports"]:
        event_id = report["event_id"]
        fault_code = report["fault_code"]
        started = report["started_at"]
        ended = report["ended_at"]
        hours = report["downtime_minutes"] / 60.0

        narrative = write_prose(
            client,
            "Rédige un paragraphe de compte rendu d'intervention de maintenance "
            "corrective en aciérie, décrivant le déroulement de l'intervention.",
            {
                "ligne": report["line_id"],
                "durée d'arrêt": f"{report['downtime_minutes']} minutes",
                "défaut à l'origine": report["fault_label_fr"] or "non renseigné",
                "type": report["category"],
            },
            f"L'intervention sur la ligne {report['line_id']} a été déclenchée à la "
            f"suite du constat du défaut {report['fault_label_fr']}. La ligne a été "
            f"arrêtée le temps du diagnostic et de la remise en état, soit "
            f"{report['downtime_minutes']} minutes au total.",
        )

        body = textwrap.dedent(f"""
            # Rapport de maintenance — intervention {event_id}

            ## Fiche d'intervention

            | | |
            |---|---|
            | Identifiant | {event_id} |
            | Ligne | `{report["line_id"]}` |
            | Type | {report["category"]} |
            | Début | {started:%Y-%m-%d %H:%M} |
            | Fin | {ended:%Y-%m-%d %H:%M} |
            | Durée d'arrêt | {report["downtime_minutes"]} minutes ({hours:.1f} h) |
            | Défaut à l'origine | `{fault_code}` |
            | Gravité | {report["severity"]} sur 3 |

            ## Déroulement

            {narrative}

            ## Suites données

            La procédure de traitement du défaut `{fault_code}` a été appliquée sur les
            tôles produites avant l'arrêt. Les tôles concernées ont été mises en attente
            qualité pour {HOLD_HOURS_BY_SEVERITY[report["severity"]]} heures.

            ## Remise en service

            La ligne {report["line_id"]} a été remise en service le
            {ended:%Y-%m-%d} à {ended:%H:%M}, après contrôle visuel de trois tôles
            consécutives sans défaut.
            """).strip()

        docs.append(
            Document(
                doc_id=report["report_doc_id"],
                title=f"Rapport de maintenance — intervention {event_id}",
                doc_type="maintenance_report",
                line_id=report["line_id"],
                fault_code=fault_code,
                event_id=event_id,
                version="1.0",
                doc_date=ended.date(),
                body=body,
            )
        )
    return docs


def build_policies(facts: dict[str, Any], client: LLMClient | None) -> list[Document]:
    """Five site policies, including the peak-load one with a data-derived threshold."""
    threshold = facts["peak_threshold_rounded"]
    exact = facts["peak_threshold_exact"]
    energy = facts["energy"]

    peak_prose = write_prose(
        client,
        "Rédige un paragraphe expliquant pourquoi une aciérie surveille ses pointes "
        "de consommation électrique et ce que coûte un dépassement.",
        {
            "seuil d'alerte": f"{threshold} kWh sur un intervalle de 15 minutes",
            "consommation annuelle": f"{fr_number(float(energy['total_kwh']))} kWh",
        },
        "La facturation de l'électricité industrielle dépend autant de la puissance "
        "appelée en pointe que de l'énergie totale consommée. Une pointe non "
        "anticipée se répercute sur l'ensemble de la période de facturation, ce qui "
        "justifie une surveillance au pas de quinze minutes.",
    )

    policies = [
        Document(
            doc_id="POL-ENR-PEAK",
            title="Politique de gestion des pointes de consommation électrique",
            doc_type="policy",
            version="3.1",
            doc_date=date(2018, 1, 22),
            body=textwrap.dedent(f"""
                # Politique de gestion des pointes de consommation électrique

                ## Objet

                {peak_prose}

                ## Seuil d'alerte

                Le seuil d'alerte de pointe est fixé à **{threshold} kWh** sur un
                intervalle de quinze minutes. Ce seuil correspond au 95e percentile de
                la consommation mesurée sur l'année de référence, soit
                {fr_number(exact, 2)} kWh avant arrondi.

                | | |
                |---|---|
                | Seuil d'alerte | {threshold} kWh / 15 min |
                | Base de calcul | 95e percentile de l'année de référence |
                | Consommation annuelle de référence | {fr_number(float(energy["total_kwh"]))} kWh |
                | Pointe maximale observée | {fr_number(float(energy["max_kwh"]), 2)} kWh |

                ## Conduite à tenir en cas de dépassement

                1. Le chef de poste est alerté dès le premier intervalle au-dessus du seuil.
                2. Si deux intervalles consécutifs dépassent le seuil, le délestage des
                   équipements non prioritaires est engagé.
                3. Tout dépassement est consigné et transmis au service Énergie sous
                   **48 heures**.

                ## Facteur de puissance

                Un facteur de puissance inductif inférieur à **92 %** est signalé au
                service Énergie. Le contrat fournisseur applique une pénalité en dessous
                de 90 % ; la marge de deux points permet de réagir avant pénalité.
                """).strip(),
        ),
        Document(
            doc_id="POL-QUA-HOLD",
            title="Politique de mise en attente qualité",
            doc_type="policy",
            version="2.3",
            doc_date=date(2018, 3, 5),
            body=textwrap.dedent(f"""
                # Politique de mise en attente qualité

                ## Principe

                Une tôle présentant un défaut de gravité 2 ou 3 est mise en attente
                qualité et ne peut pas être expédiée tant que le contrôle n'a pas statué.

                ## Barème des durées d'attente

                | Gravité | Durée d'attente |
                |---|---|
                | 1 | {HOLD_HOURS_BY_SEVERITY[1]} heures |
                | 2 | {HOLD_HOURS_BY_SEVERITY[2]} heures |
                | 3 | {HOLD_HOURS_BY_SEVERITY[3]} heures |

                ## Défauts toujours traités en gravité 3

                Les rayures `Z_Scratch` et `K_Scratch` sont traitées au niveau de
                gravité 3 quelle que soit la gravité déclarée dans la table de
                référence : une rayure traversante peut provoquer une rupture au
                formage chez le client.

                ## Revue manuelle de lot

                Un lot dont plus de **8 %** des tôles présentent un défaut critique
                part en revue manuelle avant toute décision d'expédition.

                ## Levée de l'attente

                La levée est prononcée par le responsable qualité de site pour les
                défauts de gravité 3, et par le chef d'équipe qualité pour la gravité 2.
                """).strip(),
        ),
        Document(
            doc_id="POL-MNT-PREV",
            title="Politique de maintenance préventive",
            doc_type="policy",
            version="1.4",
            doc_date=date(2018, 2, 1),
            body=textwrap.dedent("""
                # Politique de maintenance préventive

                ## Objet

                La maintenance préventive vise à réduire le nombre d'interventions
                correctives, qui sont les seules retenues dans le calcul du MTTR et du
                MTBF.

                ## Règles de planification

                1. Toute intervention préventive est planifiée hors période de production
                   lorsque la charge le permet.
                2. Une intervention préventive ne se voit jamais attribuer de code défaut :
                   le champ correspondant reste vide au journal.
                3. La durée cible d'une intervention préventive est de **45 minutes**.

                ## Consignation des arrêts

                Tout arrêt supérieur à **15 minutes** est consigné avec son heure de
                début, son heure de fin et sa durée. Les trois valeurs doivent rester
                cohérentes entre elles.

                ## Rédaction d'un rapport

                Un rapport écrit est exigé pour les interventions correctives les plus
                longues. Les interventions courtes ne donnent pas lieu à rapport : leur
                absence au corpus documentaire est normale et ne traduit pas un oubli.
                """).strip(),
        ),
        Document(
            doc_id="POL-DAT-ACC",
            title="Politique d'accès aux données de production",
            doc_type="policy",
            version="1.1",
            doc_date=date(2018, 5, 20),
            body=textwrap.dedent("""
                # Politique d'accès aux données de production

                ## Principe de moindre privilège

                Tout outil d'analyse accède à la base de production en **lecture seule**.
                Aucun outil d'aide à la décision ne dispose de droits d'écriture sur les
                tables métier.

                ## Deux couches indépendantes

                1. Le rôle de base de données utilisé par les outils d'analyse ne dispose
                   que du droit de lecture sur le schéma métier.
                2. Toute requête générée automatiquement est analysée avant exécution :
                   une seule instruction, de type lecture, sur les tables autorisées.

                Aucune des deux couches n'est considérée comme suffisante seule.

                ## Délai d'exécution

                Une requête d'analyse est interrompue au-delà de **5 secondes** afin
                qu'une requête mal formée ne puisse pas immobiliser la base.

                ## Journalisation

                Les requêtes sont journalisées avec leur identifiant de trace, leur durée
                et leur statut. Le contenu des lignes retournées n'est jamais journalisé.
                """).strip(),
        ),
        Document(
            doc_id="POL-ENV-CO2",
            title="Politique de suivi des émissions de CO2",
            doc_type="policy",
            version="2.0",
            doc_date=date(2018, 6, 12),
            body=textwrap.dedent(f"""
                # Politique de suivi des émissions de CO2

                ## Périmètre

                Le suivi porte sur les émissions associées à la consommation électrique
                des lignes de production, mesurées au même pas de quinze minutes que la
                consommation.

                ## Référence annuelle

                | | |
                |---|---|
                | Énergie consommée | {fr_number(float(energy["total_kwh"]))} kWh |
                | CO2 émis | {fr_number(float(energy["total_tco2"]), 2)} tonnes |

                ## Facteur d'émission

                Lorsque la mesure directe n'est pas disponible, le CO2 est estimé à
                partir d'un facteur d'émission de **0,000512 tonne par kWh**, issu du mix
                électrique de l'année de référence.

                ## Unités de restitution

                Le fichier source exprime le CO2 en **tonnes**. Le service Énergie
                raisonne en **kilogrammes par kWh** : la conversion multiplie par mille.
                Toute restitution précise l'unité employée.

                ## Fréquence

                Le bilan est produit **mensuellement** et consolidé une fois par an.
                """).strip(),
        ),
    ]
    return policies


def build_references(facts: dict[str, Any]) -> list[Document]:
    """Five reference documents. Fully deterministic: these are lookup tables."""
    shifts = facts["shifts"]
    faults = facts["faults"]
    lines = facts["lines"]
    threshold = facts["peak_threshold_rounded"]

    fault_rows = "\n".join(
        f"| `{f['fault_code']}` | {f['label_fr']} | {f['label_en']} | {f['severity']} | "
        f"`{f['procedure_doc_id']}` |"
        for f in faults
    )
    shift_rows = "\n".join(
        f"| `{s['shift_code']}` | {s['label_fr']} | {s['start_hour']}h | {s['end_hour']}h |"
        for s in shifts
    )
    line_rows = "\n".join(
        f"| `{line['line_id']}` | {line['name_fr']} | {line['process']} | "
        f"{line['commissioned_year']} |"
        for line in lines
    )
    escalation_rows = "\n".join(
        f"| {sev} | {ROLE_BY_SEVERITY[sev].capitalize()} | "
        f"{ESCALATION_MINUTES_BY_SEVERITY[sev]} minutes |"
        for sev in (1, 2, 3)
    )

    return [
        Document(
            doc_id="REF-GLOSSAIRE",
            title="Glossaire des termes de production et de qualité",
            doc_type="reference",
            version="1.5",
            doc_date=date(2018, 1, 8),
            body=textwrap.dedent(f"""
                # Glossaire

                ## Termes de production

                **Intervalle** — Période de quinze minutes sur laquelle la consommation
                est mesurée. L'horodatage associé marque la **fin** de l'intervalle, pas
                son début.

                **Régime de charge** — Classement d'un intervalle en `Light_Load`,
                `Medium_Load` ou `Maximum_Load` selon la puissance appelée.

                **Poste** — Période de travail de huit heures. Le site fonctionne en 3x8.

                **Nuance d'acier** — `A300` ou `A400`, selon les caractéristiques
                mécaniques visées.

                ## Termes de qualité

                **Mise en attente qualité** — Immobilisation d'une tôle jusqu'à décision
                du contrôle. La durée dépend de la gravité du défaut.

                **Gravité** — Niveau de 1 à 3 attribué à un type de défaut. La gravité 3
                correspond aux défauts pouvant entraîner une rupture chez le client.

                **Revue manuelle de lot** — Examen déclenché lorsque le taux de défauts
                critiques d'un lot dépasse 8 %.

                ## Termes de maintenance

                **Maintenance préventive** — Intervention planifiée, sans code défaut associé.

                **Maintenance corrective** — Intervention déclenchée par un défaut constaté.
                Seules ces interventions entrent dans le calcul du MTTR et du MTBF.

                **Durée d'arrêt** — Nombre de minutes pendant lesquelles la ligne est à
                l'arrêt, cohérent avec les heures de début et de fin consignées.

                ## Tables de référence

                | Code | Libellé | Label EN | Gravité | Procédure |
                |---|---|---|---|---|
                {fault_rows}
                """).strip(),
        ),
        Document(
            doc_id="REF-KPI",
            title="Définition des indicateurs de performance",
            doc_type="reference",
            version="2.1",
            doc_date=date(2018, 1, 15),
            body=textwrap.dedent(f"""
                # Définition des indicateurs

                ## Intensité énergétique

                Énergie consommée rapportée à la production.

                > intensité = énergie totale en kWh / **nombre de tôles produites**

                Le dénominateur est le **nombre de tôles**, et non le tonnage. La
                comptabilité tonnage n'étant pas fiable avant 2017, la définition a été
                conservée telle quelle pour que l'historique reste comparable.

                ## CO2 par kWh

                > ratio = (CO2 en tonnes × 1000) / énergie en kWh

                Le résultat est exprimé en **kilogrammes de CO2 par kWh**. Le facteur
                mille convertit les tonnes du fichier source en kilogrammes.

                ## TRS (OEE)

                > TRS = disponibilité × performance × qualité

                | Composante | Définition |
                |---|---|
                | Disponibilité | (temps prévu − arrêts) / temps prévu |
                | Performance | cadence réelle / cadence nominale |
                | Qualité | tôles conformes / tôles produites |

                La disponibilité est calculée à partir du journal de maintenance. La
                cadence nominale de référence est de **42 tôles par heure** et la durée
                théorique d'un poste de **480 minutes**.

                ## MTTR et MTBF

                > MTTR = minutes d'arrêt cumulées / nombre d'interventions correctives
                >
                > MTBF = temps d'ouverture / nombre d'interventions correctives

                Les interventions **préventives sont exclues** des deux indicateurs :
                planifiées, elles ne traduisent pas une défaillance.

                ## Seuil de pointe

                Le seuil d'alerte de pointe est de **{threshold} kWh** sur quinze minutes.
                """).strip(),
        ),
        Document(
            doc_id="REF-CONTACTS",
            title="Rôles et circuit d'escalade",
            doc_type="reference",
            version="1.3",
            doc_date=date(2018, 3, 19),
            body=textwrap.dedent(f"""
                # Rôles et circuit d'escalade

                Les contacts sont désignés par leur **rôle**. Aucun nom de personne ne
                figure dans ce document.

                ## Escalade qualité par gravité

                | Gravité | Rôle alerté | Délai d'escalade |
                |---|---|---|
                {escalation_rows}

                ## Fréquence de contrôle renforcé

                | Gravité | Fréquence |
                |---|---|
                | 1 | {INSPECTION_FREQUENCY_BY_SEVERITY[1].capitalize()} |
                | 2 | {INSPECTION_FREQUENCY_BY_SEVERITY[2].capitalize()} |
                | 3 | {INSPECTION_FREQUENCY_BY_SEVERITY[3].capitalize()} |

                ## Autres circuits

                | Sujet | Rôle destinataire | Délai |
                |---|---|---|
                | Dépassement de pointe électrique | Service Énergie | 48 heures |
                | Facteur de puissance sous 92 % | Service Énergie | Fin de poste |
                | Arrêt de plus de 15 minutes | Service Maintenance | Immédiat |
                | Revue manuelle de lot | Responsable qualité de site | Avant expédition |

                ## Décision d'arrêt de ligne

                L'arrêt d'une ligne est demandé au **chef de poste**, seul habilité à le
                prononcer.
                """).strip(),
        ),
        Document(
            doc_id="REF-LIGNES",
            title="Lignes de production et organisation des postes",
            doc_type="reference",
            version="1.0",
            doc_date=date(2018, 1, 5),
            body=textwrap.dedent(f"""
                # Lignes de production et postes

                ## Lignes

                | Identifiant | Nom | Procédé | Mise en service |
                |---|---|---|---|
                {line_rows}

                ## Postes

                | Code | Libellé | Début | Fin |
                |---|---|---|---|
                {shift_rows}

                ## Convention d'imputation du poste de nuit

                Le poste de nuit franchit minuit. Les heures comprises entre minuit et
                6h sont imputées à la **journée de début de poste**, c'est-à-dire la
                veille.

                Cette convention est celle du service Production. Elle **diffère de celle
                du système de paie**, qui coupe à minuit. Tout rapprochement entre les
                deux sources doit en tenir compte.

                ## Flux de production

                Le flux va du laminage à chaud vers le laminage à froid, puis vers la
                finition et l'inspection. Une tôle traverse les trois étapes dans cet
                ordre.
                """).strip(),
        ),
        Document(
            doc_id="REF-DONNEES",
            title="Dictionnaire des données de production",
            doc_type="reference",
            version="1.2",
            doc_date=date(2018, 4, 2),
            body=textwrap.dedent("""
                # Dictionnaire des données

                ## Mesures de consommation

                | Champ | Description | Unité |
                |---|---|---|
                | `ts` | Horodatage de **fin** de l'intervalle | — |
                | `usage_kwh` | Énergie active consommée sur l'intervalle | kWh |
                | `co2_tco2` | Émissions de CO2 sur l'intervalle | tonnes |
                | `lagging_current_power_factor` | Facteur de puissance inductif | % |
                | `leading_current_power_factor` | Facteur de puissance capacitif | % |
                | `nsm` | Secondes écoulées depuis minuit | s |
                | `load_type` | Régime de charge | — |

                ## Inspections de tôles

                | Champ | Description |
                |---|---|
                | `plate_id` | Identifiant de la tôle |
                | `fault_code` | Défaut constaté, un seul par tôle |
                | `steel_grade` | Nuance, `A300` ou `A400` |
                | `line_id` | Ligne d'inspection |
                | `inspected_at` | Date et heure de l'inspection |

                ## Journal de maintenance

                | Champ | Description |
                |---|---|
                | `event_id` | Identifiant de l'intervention |
                | `category` | `preventive` ou `corrective` |
                | `fault_code` | Vide pour une intervention préventive |
                | `downtime_minutes` | Durée d'arrêt |
                | `report_doc_id` | Rapport associé, vide si aucun rapport |

                ## Pièges connus

                Le fichier source de consommation est au format **jour/mois/année** et
                son horodatage marque la **fin** de l'intervalle. Le fichier n'est donc
                pas dans l'ordre chronologique : chaque journée va de 00:15 à 23:45 puis
                se termine par une ligne à 00:00.
                """).strip(),
        ),
    ]


# ------------------------------------------------------------------- driver --

FAMILIES = ("PROC", "MAN", "MNT", "POL", "REF")


def main() -> int:
    """Generate the corpus."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="skip prose generation and use the deterministic fallbacks",
    )
    parser.add_argument(
        "--only",
        choices=FAMILIES,
        help="generate a single family of documents",
    )
    args = parser.parse_args()

    print("Reading facts from the database")
    facts = fetch_facts()
    print(
        f"  {len(facts['faults'])} fault types, {len(facts['lines'])} lines, "
        f"{len(facts['reports'])} reports to write, "
        f"peak threshold {facts['peak_threshold_rounded']} kWh"
    )

    client: LLMClient | None = None
    if not args.no_llm:
        from steel_assistant.llm.factory import build_llm_client

        client = build_llm_client()
        if not client.is_available():
            print("  LLM backend unreachable, falling back to deterministic prose")
            client = None
        else:
            print("  LLM backend reachable; prose will be generated")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    builders = {
        "PROC": lambda: build_procedures(facts, client),
        "MAN": lambda: build_manuals(facts, client),
        "MNT": lambda: build_reports(facts, client),
        "POL": lambda: build_policies(facts, client),
        "REF": lambda: build_references(facts),
    }
    selected = [args.only] if args.only else list(FAMILIES)

    written = 0
    seen: set[str] = set()
    for family in selected:
        print(f"\n{family}")
        for document in builders[family]():
            if document.doc_id in seen:
                raise RuntimeError(f"duplicate doc_id: {document.doc_id}")
            seen.add(document.doc_id)
            path = DOCS_DIR / f"{document.doc_id}.md"
            path.write_text(document.render(), encoding="utf-8")
            print(f"  {document.doc_id:<18} {len(document.render()):>6,} chars")
            written += 1

    print(f"\n{written} documents written to {DOCS_DIR.relative_to(REPO_ROOT)}")
    print("Next: scripts/validate_corpus.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
