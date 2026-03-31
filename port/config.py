"""LLM client factory — reads from .env / environment variables."""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict


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


settings = Settings()


def make_llm(temperature: float = 0.1, max_tokens: int = 2048, fast: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=settings.fast_llm_base_url if fast else settings.llm_base_url,
        model=settings.fast_llm_model if fast else settings.llm_model,
        api_key=settings.llm_api_key,
        temperature=temperature,
        max_tokens=max_tokens,  # type: ignore[call-arg]
        model_kwargs={"chat_template_kwargs": {"enable_thinking": False}},
    )
