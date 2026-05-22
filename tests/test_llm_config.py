from __future__ import annotations

from typing import cast

import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, SecretStr

from port.config import (
    LLMOverrides,
    StructuredLLMOutputError,
    freeze_agent_models,
    invoke_structured,
    llm_runtime_overrides,
    make_llm,
)


def test_make_llm_respects_runtime_override_primary():
    o = LLMOverrides(llm_model="custom-primary")
    tok = llm_runtime_overrides.set(o)
    try:
        llm = make_llm(fast=False)
        assert llm.model_name == "custom-primary"
    finally:
        llm_runtime_overrides.reset(tok)


def test_make_llm_respects_runtime_override_fast():
    o = LLMOverrides(fast_llm_model="custom-fast")
    tok = llm_runtime_overrides.set(o)
    try:
        llm = make_llm(fast=True)
        assert llm.model_name == "custom-fast"
    finally:
        llm_runtime_overrides.reset(tok)


def test_make_llm_respects_runtime_api_key_override():
    o = LLMOverrides(llm_api_key="custom-key")
    tok = llm_runtime_overrides.set(o)
    try:
        llm = make_llm()
        api_key = cast(SecretStr, llm.openai_api_key)
        assert api_key.get_secret_value() == "custom-key"
    finally:
        llm_runtime_overrides.reset(tok)


def test_make_llm_uses_config_api_key_when_runtime_override_omits_key():
    o = LLMOverrides(llm_model="custom-primary")
    tok = llm_runtime_overrides.set(o)
    try:
        llm = make_llm()
        api_key = cast(SecretStr, llm.openai_api_key)
        assert api_key.get_secret_value() == "dummy"
    finally:
        llm_runtime_overrides.reset(tok)


def test_agent_without_override_uses_primary_model():
    o = LLMOverrides(llm_model="one-model", fast_llm_model="fast-model")
    tok = llm_runtime_overrides.set(o)
    try:
        llm = make_llm(agent="planner")
        assert llm.model_name == "one-model"
    finally:
        llm_runtime_overrides.reset(tok)


def test_make_llm_per_agent_model_override():
    o = LLMOverrides(agent_models=(("risk", "model-for-risk"),))
    tok = llm_runtime_overrides.set(o)
    try:
        llm = make_llm(fast=False, agent="risk")
        assert llm.model_name == "model-for-risk"
    finally:
        llm_runtime_overrides.reset(tok)


def test_freeze_agent_models_filters_unknown_keys():
    assert freeze_agent_models({"risk": "a", "nope": "b"}) == (("risk", "a"),)


def test_api_config_endpoint():
    from starlette.testclient import TestClient

    from port.server import app

    client = TestClient(app)
    r = client.get("/api/config")
    assert r.status_code == 200
    j = r.json()
    assert "llm_model" in j
    assert "fast_llm_model" in j
    assert "model_options" in j
    assert isinstance(j["model_options"], list)
    assert "default_agent_models" in j
    assert j["default_agent_models"]["risk"]
    assert "llm_read_timeout" in j
    assert "llm_api_key" not in j


def test_invoke_structured_uses_json_object_mode(monkeypatch):
    class Payload(BaseModel):
        value: int

    seen = {}

    class FakeStructured:
        def invoke(self, messages):
            seen["messages"] = messages
            return Payload(value=7)

    class FakeLlm:
        model_name = "fake-model"

        def with_structured_output(self, schema, *, method):
            seen["schema"] = schema
            seen["method"] = method
            return FakeStructured()

    monkeypatch.setattr("port.config.make_llm", lambda **_kwargs: FakeLlm())

    result = cast(Payload, invoke_structured(Payload, [], agent="risk"))

    assert result.value == 7
    assert seen["schema"] is Payload
    assert seen["method"] == "json_mode"
    assert any("valid JSON object" in msg.content for msg in seen["messages"])
    assert any("Payload" in msg.content for msg in seen["messages"])


def test_invoke_structured_keeps_system_instruction_first(monkeypatch):
    class Payload(BaseModel):
        value: int

    seen = {}

    class FakeStructured:
        def invoke(self, messages):
            seen["messages"] = messages
            return Payload(value=7)

    class FakeLlm:
        model_name = "fake-model"

        def with_structured_output(self, schema, *, method):
            seen["schema"] = schema
            seen["method"] = method
            return FakeStructured()

    monkeypatch.setattr("port.config.make_llm", lambda **_kwargs: FakeLlm())

    invoke_structured(
        Payload,
        [SystemMessage(content="Base system prompt"), HumanMessage(content="Hello")],
        agent="risk",
    )

    messages = seen["messages"]
    assert isinstance(messages[0], SystemMessage)
    assert "Base system prompt" in messages[0].content
    assert "valid JSON object" in messages[0].content
    assert all(not isinstance(msg, SystemMessage) for msg in messages[1:])


def test_invoke_structured_retries_transient_errors(monkeypatch):
    """Transient parse/validation/network errors must be retried, not propagated on first failure."""  # noqa: E501

    import port.config as config

    class Payload(BaseModel):
        value: int

    monkeypatch.setattr(config, "_interruptible_sleep", lambda _s: None)

    attempts = {"count": 0}

    class FlakyStructured:
        def invoke(self, _messages):
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("transient upstream error")
            return Payload(value=42)

    class FakeLlm:
        model_name = "fake-model"

        def with_structured_output(self, _schema, *, method):
            return FlakyStructured()

    monkeypatch.setattr("port.config.make_llm", lambda **_kwargs: FakeLlm())

    result = cast(Payload, invoke_structured(Payload, [], agent="risk"))
    assert result.value == 42
    assert attempts["count"] == 3


def test_invoke_structured_adds_repair_prompt_after_invalid_json(monkeypatch):
    import port.config as config

    class Payload(BaseModel):
        value: int

    monkeypatch.setattr(config, "_interruptible_sleep", lambda _s: None)
    seen_messages = []
    attempts = {"count": 0}

    class FlakyStructured:
        def invoke(self, messages):
            attempts["count"] += 1
            seen_messages.append(messages)
            if attempts["count"] == 1:
                raise OutputParserException(
                    "Invalid json output",
                    llm_output='{"value": "bad "quote""}',
                )
            return Payload(value=42)

    class FakeLlm:
        model_name = "fake-model"

        def with_structured_output(self, _schema, *, method):
            return FlakyStructured()

    monkeypatch.setattr("port.config.make_llm", lambda **_kwargs: FakeLlm())

    result = cast(Payload, invoke_structured(Payload, [], agent="theme"))

    assert result.value == 42
    assert attempts["count"] == 2
    repair_messages = seen_messages[1]
    assert any("previous response was rejected" in msg.content for msg in repair_messages)
    assert any('bad "quote"' in msg.content for msg in repair_messages)


def test_invoke_structured_raises_friendly_error_after_invalid_json_retries(monkeypatch):
    import port.config as config

    class Payload(BaseModel):
        value: int

    new_llm = config.config.llm.model_copy(update={"invoke_max_attempts": 1})
    new_root = config._loaded.model_copy(update={"llm": new_llm})  # type: ignore[union-attr]
    monkeypatch.setattr(config, "_loaded", new_root)

    class BadStructured:
        def invoke(self, _messages):
            raise OutputParserException(
                "Invalid json output",
                llm_output='{"value": "bad "quote""}',
            )

    class FakeLlm:
        model_name = "fake-model"

        def with_structured_output(self, _schema, *, method):
            return BadStructured()

    monkeypatch.setattr("port.config.make_llm", lambda **_kwargs: FakeLlm())

    with pytest.raises(StructuredLLMOutputError) as exc_info:
        invoke_structured(Payload, [], agent="theme")

    assert exc_info.value.agent == "theme"
    assert "Theme agent returned malformed structured output" in str(exc_info.value)


def test_invoke_structured_gives_up_after_max_attempts(monkeypatch):
    """If every attempt fails, the final exception is surfaced after the retry budget is spent."""

    import port.config as config

    class Payload(BaseModel):
        value: int

    new_llm = config.config.llm.model_copy(update={"invoke_max_attempts": 3})
    new_root = config._loaded.model_copy(update={"llm": new_llm})  # type: ignore[union-attr]
    monkeypatch.setattr(config, "_loaded", new_root)
    monkeypatch.setattr(config, "_interruptible_sleep", lambda _s: None)

    attempts = {"count": 0}

    class AlwaysFailingStructured:
        def invoke(self, _messages):
            attempts["count"] += 1
            raise RuntimeError("upstream is down")

    class FakeLlm:
        model_name = "fake-model"

        def with_structured_output(self, _schema, *, method):
            return AlwaysFailingStructured()

    monkeypatch.setattr("port.config.make_llm", lambda **_kwargs: FakeLlm())

    import pytest

    with pytest.raises(RuntimeError, match="upstream is down"):
        invoke_structured(Payload, [], agent="risk")
    assert attempts["count"] == 3
