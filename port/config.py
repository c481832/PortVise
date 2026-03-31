from langchain_openai import ChatOpenAI

# Best reasoning model — used for all analytical agents
LLM_BASE_URL = "http://localhost:8003/v1"
LLM_MODEL = "Qwen3.5-35B-A3B-UD-Q6_K_S.gguf"

# Fast router model — used for lightweight factual tasks (news agent)
FAST_LLM_BASE_URL = "http://localhost:8000/v1"
FAST_LLM_MODEL = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"

LLM_API_KEY = "dummy"


def make_llm(temperature: float = 0.1, max_tokens: int = 2048, fast: bool = False) -> ChatOpenAI:
    return ChatOpenAI(
        base_url=FAST_LLM_BASE_URL if fast else LLM_BASE_URL,
        model=FAST_LLM_MODEL if fast else LLM_MODEL,
        api_key=LLM_API_KEY,
        temperature=temperature,
        max_tokens=max_tokens,
        model_kwargs={"chat_template_kwargs": {"enable_thinking": False}},
    )

