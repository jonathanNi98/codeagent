"""
config.py — load .env, expose Config dataclass, build LLM client.

Public surface:
  - Config            frozen dataclass holding all settings
  - load_config()     read env (.env loaded automatically), return Config
  - make_client(cfg)  STUB — you pick the SDK and construct the client
  - get_config()      memoised loader used by the rest of the codebase

NOTE on SDK choice
------------------
This scaffold assumes your MiniMax endpoint speaks the **OpenAI protocol**
(the typical case for Chinese LLM providers — DeepSeek / Zhipu / MiniMax
all expose ``https://<host>/v1`` and you point openai.OpenAI at it).

If yours is **Anthropic-compatible** instead, swap ``make_client`` for
``anthropic.Anthropic(...)`` and adjust the agent loops in
``planner.py`` / ``coder.py`` to the Anthropic ``messages`` format
(stop_reason, content blocks, tool_result message shape).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _load_dotenv_file() -> None:
    """Load .env from the project root if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
    except ImportError as e:
        raise SystemExit(
            "python-dotenv is required. Install with: pip install python-dotenv"
        ) from e

    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)


@dataclass(frozen=True)
class Config:
    api_key: str
    base_url: str
    model_name: str
    workdir: Path
    test_cmd: str


def load_config() -> Config:
    """Read settings from env and return a frozen Config.

    Required env vars (missing -> SystemExit):
      MINIMAX_API_KEY       your provider key
      MINIMAX_BASE_URL      e.g. https://api.example.com/v1

    Optional env vars (defaults shown):
      MINIMAX_MODEL_NAME    "MiniMax-M3"
      AGENT_WORKDIR         "./test_target"
      TEST_CMD              "pytest -q"
    """
    _load_dotenv_file()

    api_key = os.environ.get("MINIMAX_API_KEY")
    base_url = os.environ.get("MINIMAX_BASE_URL")
    if not api_key or not base_url:
        raise SystemExit(
            "Missing MINIMAX_API_KEY or MINIMAX_BASE_URL. "
            "Copy .env.example to .env and fill in the values."
        )

    workdir = Path(os.environ.get("AGENT_WORKDIR", "./test_target")).resolve()
    return Config(
        api_key=api_key,
        base_url=base_url,
        model_name=os.environ.get("MINIMAX_MODEL_NAME", "MiniMax-M3"),
        workdir=workdir,
        test_cmd=os.environ.get("TEST_CMD", "pytest -q"),
    )


def make_client(cfg: Config) -> Any:
    """Build the LLM SDK client.

    TODO (you implement): pick the SDK matching your provider.

        # OpenAI-compatible (default expectation):
        from openai import OpenAI
        return OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)

        # Anthropic-compatible (alternative):
        from anthropic import Anthropic
        return Anthropic(api_key=cfg.api_key, base_url=cfg.base_url)

    Whatever you return must support a chat-style call that accepts
    ``model``, ``messages``, and ``tools=[...]``. The agent loops in
    planner.py / coder.py call it as

        client.chat.completions.create(
            model=cfg.model_name,
            messages=[system_msg, *history],
            tools=schemas,
        )
    """
    raise NotImplementedError(
        "TODO: import your SDK (openai.OpenAI or anthropic.Anthropic) and "
        "construct the client with cfg.api_key + cfg.base_url."
    )


_cached: Config | None = None


def get_config() -> Config:
    """Memoised loader — first call hits env, later calls reuse the same Config."""
    global _cached
    if _cached is None:
        _cached = load_config()
    return _cached
