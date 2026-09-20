"""Typed configuration, loaded from config/default.yaml and overridden by env.

Every setting lives here. Application code never hard-codes a URL, a model name
or a threshold. Env vars use the ``SDA_`` prefix with ``__`` as the nesting
separator, so ``SDA_LLM__BACKEND=openai_compatible`` overrides ``llm.backend``.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "default.yaml"


class DBSettings(BaseModel):
    """Postgres connection details and the two application roles."""

    host: str = "localhost"
    port: int = 5433
    name: str = "steel"
    assistant_user: str = "assistant_ro"
    app_user: str = "app_rw"
    statement_timeout_s: int = 5


class LLMSettings(BaseModel):
    """Which model backend to talk to, and with what limits."""

    backend: Literal["ollama", "openai_compatible"] = "ollama"
    base_url: str = "http://localhost:11434"
    api_key: SecretStr = SecretStr("")
    agent_model: str = "qwen2.5:3b-instruct"
    sql_model: str = "qwen2.5:3b-instruct"
    judge_model: str = "qwen2.5:3b-instruct"
    temperature: float = 0.0
    timeout_s: int = 300
    max_retries: int = 2
    num_ctx: int = 8192
    suppress_reasoning: bool = False


class RetrievalSettings(BaseModel):
    """Embedding, chunking and hybrid-search parameters."""

    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_dim: int = 768
    query_prefix: str = "query: "
    passage_prefix: str = "passage: "
    mode: Literal["dense", "hybrid"] = "hybrid"
    rerank: bool = False
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    top_k: int = 5
    candidates_per_branch: int = 20
    rrf_k: int = 60
    chunk_max_tokens: int = 500
    chunk_overlap_tokens: int = 50
    code_class_split_lines: int = 150


class SQLSettings(BaseModel):
    """Text-to-SQL generation, guarding and execution limits."""

    fewshot: Literal["none", "static", "dynamic"] = "static"
    fewshot_k: int = 4
    max_retries: int = 2
    max_rows_returned: int = 50
    default_limit: int = 200
    allowed_schemas: list[str] = Field(default_factory=lambda: ["plant"])


class AgentSettings(BaseModel):
    """Orchestration strategy."""

    mode: Literal["router", "tool_calling"] = "router"
    max_tool_calls: int = 5


class APISettings(BaseModel):
    """FastAPI service settings."""

    key: SecretStr = SecretStr("")
    host: str = "0.0.0.0"
    port: int = 8000


class EvalSettings(BaseModel):
    """Evaluation harness settings."""

    experiment_name: str = "steel-assistant-eval"
    seed: int = 42


class YamlSource(PydanticBaseSettingsSource):
    """Feeds config/default.yaml into the settings chain as the base layer."""

    def get_field_value(self, field: Any, field_name: str) -> tuple[Any, str, bool]:  # noqa: D102
        raise NotImplementedError  # pragma: no cover - the whole dict is returned below

    def __call__(self) -> dict[str, Any]:
        """Return the parsed YAML, or an empty dict when the file is absent."""
        if not CONFIG_PATH.is_file():
            return {}
        return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


class Settings(BaseSettings):
    """Root configuration object."""

    model_config = SettingsConfigDict(
        env_prefix="SDA_",
        env_nested_delimiter="__",
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db: DBSettings = Field(default_factory=DBSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    sql: SQLSettings = Field(default_factory=SQLSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    api: APISettings = Field(default_factory=APISettings)
    eval: EvalSettings = Field(default_factory=EvalSettings)
    seed: int = 42

    @classmethod
    def settings_customise_sources(  # noqa: D102, PLR0913
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Highest priority first: explicit args, then env, then .env, then YAML.
        return (init_settings, env_settings, dotenv_settings, YamlSource(settings_cls))


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, parsed once."""
    return Settings()


def load_config(path: Path) -> Settings:
    """Load settings from an explicit YAML file, for evaluation configs.

    Values in ``path`` override ``config/default.yaml``; env vars still win, so
    an eval config never silently picks up a stale shell override of its own
    knobs. Used by ``make eval CONFIG=c3``.
    """
    overrides = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    base = get_settings().model_dump()
    for section, values in overrides.items():
        if isinstance(values, dict) and isinstance(base.get(section), dict):
            base[section].update(values)
        else:
            base[section] = values
    return Settings(**base)
