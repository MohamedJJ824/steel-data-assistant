# Steel Plant Data Assistant
# All targets assume a .env file exists (cp .env.example .env).

SHELL := /bin/bash
PY := .venv/bin/python
UV := uv
COMPOSE := docker compose
CONFIG ?= c3

.DEFAULT_GOAL := help
.PHONY: help setup up down wait-db psql logs seed-data seed index corpus validate \
	    test test-all lint fmt eval eval-all report api ui clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Create the virtualenv and install the project
	$(UV) venv --python 3.11 .venv
	$(UV) pip install --python $(PY) -e ".[dev,ui,eval]"

up:  ## Start the database
	$(COMPOSE) up -d db
	$(MAKE) wait-db

up-all:  ## Start the whole stack (db, api, ui, mlflow)
	$(COMPOSE) up -d --build
	$(MAKE) wait-db

down:  ## Stop the stack, keep the data volume
	$(COMPOSE) down

logs:  ## Follow the stack logs
	$(COMPOSE) logs -f --tail 100

wait-db:  ## Block until the database reports healthy
	@printf 'waiting for db '
	@for i in $$(seq 1 60); do \
	  if [ "$$($(COMPOSE) ps -q db | xargs -r docker inspect -f '{{.State.Health.Status}}' 2>/dev/null)" = healthy ]; then \
	    echo ' ready'; exit 0; fi; printf '.'; sleep 1; done; \
	  echo ' TIMEOUT'; $(COMPOSE) logs --tail 40 db; exit 1

psql:  ## Open a psql shell as the superuser
	$(COMPOSE) exec db psql -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-steel}

seed-data:  ## Download the UCI datasets, load them, generate the synthetic layer
	$(PY) scripts/download_data.py
	$(PY) scripts/load_db.py
	$(PY) scripts/generate_synthetic_tables.py

corpus:  ## Regenerate the French document corpus
	$(PY) scripts/generate_docs.py

validate:  ## Check the corpus against the database
	$(PY) scripts/validate_corpus.py

index:  ## Build or refresh the retrieval index
	$(PY) scripts/build_index.py

seed: up seed-data validate index  ## Full seed: database, data, corpus check, index

gold:  ## Run the gold SQL and the few-shot leakage check
	$(PY) scripts/prepare_gold.py

test:  ## Unit tests only (no DB, no LLM)
	$(PY) -m pytest -m "not llm and not db" -q

test-all:  ## Every test, including those needing the DB and an LLM
	$(PY) -m pytest -q

lint:  ## Lint and format check
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

fmt:  ## Apply formatting and autofixes
	$(PY) -m ruff check --fix .
	$(PY) -m ruff format .

eval: gold  ## Evaluate one configuration: make eval CONFIG=c3
	$(PY) scripts/run_eval.py --config $(CONFIG)

eval-all: gold  ## Evaluate every configuration (hours on a local model)
	$(PY) scripts/run_eval.py --all

eval-smoke:  ## Quick harness check: 5 questions, no judge
	$(PY) scripts/run_eval.py --config $(CONFIG) --limit 5 --no-judge --no-mlflow

report:  ## Regenerate docs/EVAL_REPORT.md from the run results
	$(PY) scripts/make_report.py

api:  ## Run the API locally
	$(PY) -m uvicorn steel_assistant.api.main:app --app-dir src --reload --port 8000

ui:  ## Run the Streamlit UI locally
	$(PY) -m streamlit run ui/app.py

mlflow:  ## Serve the MLflow UI over the local run store
	$(PY) -m mlflow ui --backend-store-uri ./mlruns --port 5000

clean:  ## Stop the stack AND destroy the database volume
	$(COMPOSE) down -v
	rm -rf data/raw/* data/processed/*
