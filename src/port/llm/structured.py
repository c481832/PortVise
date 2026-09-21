"""Structured LLM invocation: JSON-mode calls with retry and repair.

Wraps a chat model so it returns a validated pydantic object, retrying
transient provider errors and re-prompting once with a repair message when the
model emits unparseable JSON.
"""

from __future__ import annotations

import json
import logging
import time
import warnings

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage

from port.config import config
from port.llm.client import make_llm
from port.llm.context import (
    ReviewStoppedError,
    StructuredLLMOutputError,
    raise_if_review_stopped,
    review_stop_event,
)
from port.llm.retry import backoff_seconds

warnings.filterwarnings(
    "ignore",
    message=r"Pydantic serializer warnings:[\s\S]*field_name='parsed'",
    category=UserWarning,
    module=r"pydantic\.main",
)
log = logging.getLogger(__name__)
def _interruptible_sleep(seconds: float) -> None:
    if seconds <= 0:
        raise_if_review_stopped()
        return
    event = review_stop_event.get()
    if event is None:
        time.sleep(seconds)
        return
    if event.wait(seconds):
        raise ReviewStoppedError("Review stopped by user.")
def _retry_backoff_seconds(attempt: int) -> float:
    base = max(0.0, config.llm.retry_base_seconds)
    cap = max(base, config.llm.retry_max_seconds)
    return backoff_seconds(attempt, base=base, cap=cap)
def _agent_flow_logger(agent: str) -> logging.Logger:
    return logging.getLogger(f"port.agentflow.{agent}")
def _safe_text(value, *, max_chars: int) -> str:
    try:
        if hasattr(value, "model_dump"):
            text = json.dumps(value.model_dump(), ensure_ascii=True, default=str)
        elif isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, ensure_ascii=True, default=str)
        else:
            text = str(value)
    except Exception:
        text = repr(value)
    if len(text) > max_chars:
        return f"{text[:max_chars]}\n... (truncated)"
    return text
def _messages_for_log(messages) -> str:
    rendered: list[str] = []
    cap = config.truncation.log_safe_text_max_chars
    for i, m in enumerate(messages):
        msg_type = getattr(m, "type", m.__class__.__name__)
        content = getattr(m, "content", m)
        rendered.append(f"[{i}] {msg_type}: {_safe_text(content, max_chars=cap)}")
    return "\n".join(rendered)
def _schema_json_for_prompt(schema) -> str:
    payload = schema.model_json_schema() if hasattr(schema, "model_json_schema") else schema
    return json.dumps(payload, ensure_ascii=False)
def _structured_messages(messages, schema):
    schema_name = getattr(schema, "__name__", "StructuredOutput")
    instruction = (
        "Write all user-facing free text in English. Return only a valid JSON object. "
        "Do not wrap it in markdown. "
        f"The JSON object must validate against the {schema_name} schema below:\n"
        f"{_schema_json_for_prompt(schema)}"
    )
    copied = list(messages)
    if copied and isinstance(copied[0], SystemMessage):
        first = copied[0]
        copied[0] = SystemMessage(content=f"{first.content}\n\n{instruction}")
        return copied
    return [SystemMessage(content=instruction), *copied]
def _parser_llm_output(exc: Exception) -> str | None:
    if isinstance(exc, OutputParserException):
        output = getattr(exc, "llm_output", None)
        return output if isinstance(output, str) and output.strip() else None
    return None
def _json_repair_message(exc: Exception, llm_output: str, *, max_chars: int) -> HumanMessage:
    truncated = llm_output[:max_chars]
    return HumanMessage(
        content=(
            "Your previous response was rejected because it was not valid JSON. "
            f"Parser error: {exc}\n\n"
            "Return a complete corrected JSON object only. Preserve the intended analysis, "
            "but ensure every string is valid JSON: escape internal double quotes, backslashes, "
            "and control characters. Do not wrap the response in markdown.\n\n"
            f"Previous invalid response:\n{truncated}"
        )
    )
def invoke_structured(
    schema,
    messages,
    *,
    agent: str,
    max_tokens: int,
    temperature: float,
    use_agent_model: bool = True,
):
    raise_if_review_stopped()
    structured_messages = _structured_messages(messages, schema)
    schema_name = getattr(schema, "__name__", "StructuredOutput")
    ceiling = config.llm.max_tokens_ceiling
    length_markers = config.llm.length_markers
    log_cap = config.truncation.log_safe_text_max_chars
    tokens = max_tokens
    flow_log = _agent_flow_logger(agent)
    max_attempts = max(1, int(config.llm.invoke_max_attempts))
    attempt = 0
    base = None
    cached_tokens: int | None = None
    while True:
        raise_if_review_stopped()
        attempt += 1
        if base is None or cached_tokens != tokens:
            base = make_llm(
                max_tokens=tokens,
                agent=agent if use_agent_model else None,
                temperature=temperature,
            )
            cached_tokens = tokens
        llm = base.with_structured_output(schema, method="json_mode")
        log.info(
            "LLM input agent=%r model=%r max_tokens=%d temperature=%.2f attempt=%d/%d messages=%d",
            agent,
            getattr(base, "model_name", "unknown"),
            tokens,
            temperature,
            attempt,
            max_attempts,
            len(structured_messages),
        )
        flow_log.info(
            "LLM input model=%r max_tokens=%d temperature=%.2f attempt=%d/%d\n%s",
            getattr(base, "model_name", "unknown"),
            tokens,
            temperature,
            attempt,
            max_attempts,
            _messages_for_log(structured_messages),
        )
        try:
            result = llm.invoke(structured_messages)
            raise_if_review_stopped()
            log.info("LLM output agent=%r schema=%s", agent, schema_name)
            flow_log.info("LLM output\n%s", _safe_text(result, max_chars=log_cap))
            return result
        except ReviewStoppedError:
            raise
        except Exception as exc:
            msg = str(exc).lower()
            parser_output = _parser_llm_output(exc)
            if any(m in msg for m in length_markers) and tokens < ceiling:
                tokens = min(tokens * 2, ceiling)
                log.info(
                    "structured output truncated for agent %r — retrying with max_tokens=%d",
                    agent,
                    tokens,
                )
                flow_log.info("structured output truncated — retrying with max_tokens=%d", tokens)
                attempt -= 1
                continue
            if attempt >= max_attempts:
                log.exception(
                    "LLM invoke failed agent=%r attempt=%d/%d — giving up",
                    agent,
                    attempt,
                    max_attempts,
                )
                flow_log.exception(
                    "LLM invoke failed attempt=%d/%d — giving up", attempt, max_attempts
                )
                if parser_output is not None:
                    raise StructuredLLMOutputError(
                        agent=agent,
                        schema_name=schema_name,
                    ) from exc
                raise
            if parser_output is not None:
                structured_messages = _structured_messages(
                    [
                        *messages,
                        _json_repair_message(exc, parser_output, max_chars=log_cap),
                    ],
                    schema,
                )
            backoff = _retry_backoff_seconds(attempt)
            log.warning(
                "LLM invoke failed agent=%r attempt=%d/%d err=%s — retrying in %.1fs",
                agent,
                attempt,
                max_attempts,
                exc,
                backoff,
            )
            flow_log.warning(
                "LLM invoke failed attempt=%d/%d err=%s — retrying in %.1fs",
                attempt,
                max_attempts,
                exc,
                backoff,
            )
            _interruptible_sleep(backoff)
