# Steel Plant Data Assistant
# All targets assume a .env file exists (cp .env.example .env).

SHELL := /bin/bash
PY := .venv/bin/python
UV := uv
COMPOSE := docker compose

.DEFAULT_GOAL := help
.PHONY: help setup up down wait-db psql seed-data seed index test test-all lint fmt clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup:  ## Create the virtualenv and install the project
	$(UV) venv --python 3.11 .venv
	$(UV) pip install --python $(PY) -e ".[dev,ui,eval]"

up:  ## Start the database
	$(COMPOSE) up -d db
	$(MAKE) wait-db

down:  ## Stop the stack, keep the data volume
	$(COMPOSE) down

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

seed: up seed-data  ## Full seed: database up, data loaded, corpus indexed
	$(PY) scripts/validate_corpus.py
	$(MAKE) index

index:  ## Build or refresh the retrieval index
	$(PY) scripts/build_index.py

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

clean:  ## Stop the stack AND destroy the database volume
	$(COMPOSE) down -v
	rm -rf data/raw/* data/processed/*
