from __future__ import annotations

import json
import logging
import time
import warnings

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage

from advisor.config import config
from advisor.llm.client import make_llm
from advisor.llm.context import (
    ReviewStoppedError,
    raise_if_review_stopped,
    review_stop_event,
)
from advisor.logging import flow_log
from advisor.util import clip_text, safe_text

warnings.filterwarnings(
    "ignore",
    message=r"Pydantic serializer warnings:[\s\S]*field_name='parsed'",
    category=UserWarning,
    module=r"pydantic\.main",
)

log = logging.getLogger(__name__)


class StructuredLLMOutputError(RuntimeError):
    def __init__(self, *, agent: str):
        self.agent = agent
        super().__init__(
            f"{agent.title()} agent returned malformed structured output after retries. "
            "The model produced invalid JSON, so the review could not continue. "
            "Retry the review, or choose a stronger model for this agent."
        )


def interruptible_sleep(seconds: float) -> None:
    event = review_stop_event.get()
    if event is None:
        time.sleep(seconds)
        return
    if event.wait(seconds):
        raise ReviewStoppedError("Review stopped by user.")


def messages_for_log(messages) -> str:
    cap = config.truncation.log_safe_text_max_chars
    rendered: list[str] = []
    for i, message in enumerate(messages):
        msg_type = getattr(message, "type", message.__class__.__name__)
        content = getattr(message, "content", message)
        rendered.append(f"[{i}] {msg_type}: {safe_text(content, max_chars=cap)}")
    return "\n".join(rendered)


def build_structured_messages(messages, schema):
    payload = schema.model_json_schema() if hasattr(schema, "model_json_schema") else schema
    schema_name = getattr(schema, "__name__", "StructuredOutput")
    instruction = (
        "Write all user-facing free text in English. Return only a valid JSON object. "
        "Do not wrap it in markdown. "
        f"The JSON object must validate against the {schema_name} schema below:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    copied = list(messages)
    if copied and isinstance(copied[0], SystemMessage):
        copied[0] = SystemMessage(content=f"{copied[0].content}\n\n{instruction}")
        return copied
    return [SystemMessage(content=instruction), *copied]


def parser_llm_output(exc: Exception) -> str | None:
    if not isinstance(exc, OutputParserException):
        return None
    output = exc.llm_output
    if isinstance(output, str) and output.strip():
        return output
    return None


def json_repair_message(exc: Exception, llm_output: str, *, max_chars: int) -> HumanMessage:
    return HumanMessage(
        content=(
            "Your previous response was rejected because it was not valid JSON. "
            f"Parser error: {exc}\n\n"
            "Return a complete corrected JSON object only. Preserve the intended analysis, "
            "but ensure every string is valid JSON: escape internal double quotes, backslashes, "
            "and control characters. Do not wrap the response in markdown.\n\n"
            f"Previous invalid response:\n{clip_text(llm_output, max_chars)}"
        )
    )


def is_length_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in config.llm.length_markers)


def invoke_structured(
    schema,
    messages,
    *,
    agent: str,
    max_tokens: int,
    temperature: float,
    use_agent_model: bool,
):
    raise_if_review_stopped()
    schema_name = getattr(schema, "__name__", "StructuredOutput")
    structured_messages = build_structured_messages(messages, schema)
    ceiling = config.llm.max_tokens_ceiling
    log_cap = config.truncation.log_safe_text_max_chars
    max_attempts = max(1, int(config.llm.invoke_max_attempts))
    agent_log = flow_log(agent)

    tokens = max_tokens
    attempt = 1
    base = make_llm(
        max_tokens=tokens,
        agent=agent if use_agent_model else None,
        temperature=temperature,
    )
    while True:
        raise_if_review_stopped()
        model_name = getattr(base, "model_name", "unknown")
        log.info(
            "LLM input agent=%r model=%r max_tokens=%d temperature=%.2f attempt=%d/%d messages=%d",
            agent,
            model_name,
            tokens,
            temperature,
            attempt,
            max_attempts,
            len(structured_messages),
        )
        agent_log.info(
            "LLM input model=%r max_tokens=%d temperature=%.2f attempt=%d/%d\n%s",
            model_name,
            tokens,
            temperature,
            attempt,
            max_attempts,
            messages_for_log(structured_messages),
        )

        try:
            result = base.with_structured_output(schema, method="json_schema").invoke(
                structured_messages
            )
        except ReviewStoppedError:
            raise
        except Exception as exc:
            if is_length_error(exc) and tokens < ceiling:
                tokens = min(tokens * 2, ceiling)
                log.info(
                    "structured output truncated for agent %r — retrying with max_tokens=%d",
                    agent,
                    tokens,
                )
                agent_log.info("structured output truncated — retrying with max_tokens=%d", tokens)
                base = make_llm(
                    max_tokens=tokens,
                    agent=agent if use_agent_model else None,
                    temperature=temperature,
                )
                continue

            parser_output = parser_llm_output(exc)
            if attempt >= max_attempts:
                log.exception(
                    "LLM invoke failed agent=%r attempt=%d/%d — giving up",
                    agent,
                    attempt,
                    max_attempts,
                )
                agent_log.exception(
                    "LLM invoke failed attempt=%d/%d — giving up", attempt, max_attempts
                )
                if parser_output is not None:
                    raise StructuredLLMOutputError(agent=agent) from exc
                raise

            if parser_output is not None:
                repair = json_repair_message(exc, parser_output, max_chars=log_cap)
                structured_messages = build_structured_messages([*messages, repair], schema)
            delay = config.llm.retry_base_seconds
            log.warning(
                "LLM invoke failed agent=%r attempt=%d/%d err=%s — retrying in %.1fs",
                agent,
                attempt,
                max_attempts,
                exc,
                delay,
            )
            agent_log.warning(
                "LLM invoke failed attempt=%d/%d err=%s — retrying in %.1fs",
                attempt,
                max_attempts,
                exc,
                delay,
            )
            interruptible_sleep(delay)
            attempt += 1
            continue

        raise_if_review_stopped()
        log.info("LLM output agent=%r schema=%s", agent, schema_name)
        agent_log.info("LLM output\n%s", safe_text(result, max_chars=log_cap))
        return result
