"""LLM client factory — reads from .env / environment variables."""

from __future__ import annotations

import warnings

# OpenAI SDK can type `parsed` as None while LangChain puts a Pydantic model there; harmless.
warnings.filterwarnings(
    "ignore",
    message=r"Pydantic serializer warnings:[\s\S]*field_name='parsed'",
    category=UserWarning,
    module=r"pydantic\.main",
)

import httpx  # noqa: E402
from langchain_openai import ChatOpenAI  # noqa: E402
from pydantic_settings import BaseSettings, SettingsConfigDict  # noqa: E402


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    llm_base_url: str = "http://localhost:8003/v1"
    llm_model: str = "Qwen3.5-35B-A3B-UD-Q6_K_S.gguf"
    fast_llm_base_url: str = "http://localhost:8000/v1"
    fast_llm_model: str = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    llm_api_key: str = "dummy"
    tavily_api_key: str = ""
    # Local llama.cpp can take many minutes per completion;
    # OpenAI defaults (e.g. 600s read) are easy to hit.
    llm_connect_timeout: float = 30.0
    llm_read_timeout: float = 1200.0
    llm_max_retries: int = 2


settings = Settings()


def _llm_http_timeout() -> httpx.Timeout:
    r = settings.llm_read_timeout
    return httpx.Timeout(
        connect=settings.llm_connect_timeout,
        read=r,
        write=r,
        pool=r,
    )


def make_llm(temperature: float = 0.1, max_tokens: int = 2048, fast: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.fast_llm_base_url if fast else settings.llm_base_url,
        model=settings.fast_llm_model if fast else settings.llm_model,
        api_key=settings.llm_api_key,
        temperature=temperature,
        max_tokens=max_tokens,  # type: ignore[call-arg]
        timeout=_llm_http_timeout(),
        max_retries=settings.llm_max_retries,
    )
