from langchain_openai import ChatOpenAI

LLM_BASE_URL = "http://localhost:8003/v1"
LLM_MODEL = "Qwen3.5-35B-A3B-UD-Q6_K_S.gguf"
LLM_API_KEY = "dummy"


def make_llm(temperature: float = 0.1, max_tokens: int = 2048) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        temperature=temperature,
        max_tokens=max_tokens,
    )
