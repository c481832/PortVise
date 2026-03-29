from langchain_openai import ChatOpenAI

LLM_BASE_URL = "http://localhost:8003/v1"
LLM_MODEL = "local"
LLM_API_KEY = "dummy"


def make_llm(temperature: float = 0.1) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        temperature=temperature,
    )
