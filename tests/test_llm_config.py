from __future__ import annotations

from pathlib import Path
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


def test_make_llm_respects_runtime_override_default_model():
    o = LLMOverrides(llm_model="custom-default")
    tok = llm_runtime_overrides.set(o)
    try:
        llm = make_llm()
        assert llm.model_name == "custom-default"
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
    o = LLMOverrides(llm_model="custom-default")
    tok = llm_runtime_overrides.set(o)
    try:
        llm = make_llm()
        api_key = cast(SecretStr, llm.openai_api_key)
        assert api_key.get_secret_value() == "dummy"
    finally:
        llm_runtime_overrides.reset(tok)


def test_agent_without_override_uses_default_model():
    o = LLMOverrides(llm_model="one-model")
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
        llm = make_llm(agent="risk")
        assert llm.model_name == "model-for-risk"
    finally:
        llm_runtime_overrides.reset(tok)


def test_make_llm_uses_endpoint_for_selected_model(monkeypatch):
    import port.config as config

    new_llm = config.config.llm.model_copy(
        update={
            "base_url": "http://default.example/v1",
            "model_base_urls": '{"model-for-risk":"http://risk.example/v1"}',
        }
    )
    new_root = config._loaded.model_copy(update={"llm": new_llm})  # type: ignore[union-attr]
    monkeypatch.setattr(config, "_loaded", new_root)

    o = LLMOverrides(agent_models=(("risk", "model-for-risk"),))
    tok = llm_runtime_overrides.set(o)
    try:
        llm = make_llm(agent="risk")
        assert llm.model_name == "model-for-risk"
        assert str(llm.openai_api_base) == "http://risk.example/v1"
    finally:
        llm_runtime_overrides.reset(tok)


def test_make_llm_agent_summary_uses_configured_agent_model():
    llm = make_llm(agent="agent_summary")
    assert llm.model_name == "Qwen3.5-9B-Q4_K_M.gguf"


def test_make_llm_allocation_uses_configured_agent_model():
    llm = make_llm(agent="allocation")
    assert llm.model_name == "Qwen3.5-9B-Q4_K_M.gguf"


def test_make_llm_omits_extra_args_by_default():
    llm = make_llm(agent="risk")
    assert llm.extra_body is None


def test_blank_configured_agent_model_uses_default_model(monkeypatch):
    import port.config as config

    new_agents = config.config.agents.model_copy(update={"manager": ""})
    new_root = config._loaded.model_copy(update={"agents": new_agents})  # type: ignore[union-attr]
    monkeypatch.setattr(config, "_loaded", new_root)
    llm = make_llm(agent="manager")
    assert llm.model_name == "Qwen3.5-9B-Q4_K_M.gguf"


def test_freeze_agent_models_filters_unknown_keys():
    assert freeze_agent_models({"allocation": "b", "risk": "a", "nope": "c"}) == (
        ("allocation", "b"),
        ("risk", "a"),
    )


def test_api_config_endpoint():
    from starlette.testclient import TestClient

    from port.server import app

    client = TestClient(app)
    r = client.get("/api/config")
    assert r.status_code == 200
    j = r.json()
    assert "llm_model" in j
    assert "fast_llm_model" not in j
    assert "fast_llm_base_url" not in j
    assert "model_options" in j
    assert isinstance(j["model_options"], list)
    assert "model_base_urls" in j
    assert isinstance(j["model_base_urls"], dict)
    assert j["model_extra_args"] == ""
    assert "default_agent_models" in j
    assert j["default_agent_models"]["risk"]
    assert "llm_read_timeout" in j
    assert "llm_api_key" not in j
    assert j["llm_api_key_set"] is True
    assert j["search_provider"] == "searxng"
    assert j["searxng_url"]
    assert "tavily_api_key" not in j
    assert j["tavily_api_key_set"] is False


def _isolate_config_files(tmp_path, monkeypatch):
    """Point config at the test fixture + a throwaway local file so POST/DELETE never
    touch the real config.local.toml, and reload() merges the temp local override."""
    import port.config as config

    fixture = Path(__file__).resolve().parent / "fixtures" / "test_config.toml"
    local = tmp_path / "config.local.toml"
    monkeypatch.setattr(config, "DEFAULT_CONFIG_PATH", fixture)
    monkeypatch.setattr(config, "LOCAL_CONFIG_PATH", local)
    return fixture, local


def test_config_write_persists_and_applies(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    import port.config as config
    from port.server import app

    fixture, local = _isolate_config_files(tmp_path, monkeypatch)
    client = TestClient(app)
    try:
        r = client.post(
            "/api/config",
            json={
                "llm_base_url": "http://example:9000/v1",
                "llm_model": "model-x",
                "model_options": ["model-x", "model-y"],
                "model_base_urls": {
                    "model-x": "http://example:9000/v1",
                    "model-y": "http://example:9001/v1",
                },
                "model_extra_args": '{"model-x":{"extra_body":{"x":1}}}',
                "agent_models": {"risk": "model-y"},
                "llm_api_key": "secret123",
                "search_provider": "tavily",
                "searxng_url": "http://searx.example:8888",
                "tavily_api_key": "tvly-secret",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["llm_model"] == "model-x"
        assert body["llm_api_key_set"] is True
        assert "llm_api_key" not in body
        assert body["default_agent_models"]["risk"] == "model-y"
        assert set(body["model_options"]) == {"model-x", "model-y"}
        assert body["model_base_urls"] == {
            "model-x": "http://example:9000/v1",
            "model-y": "http://example:9001/v1",
        }
        assert body["model_extra_args"] == '{"model-x":{"extra_body":{"x":1}}}'
        assert body["search_provider"] == "tavily"
        assert body["searxng_url"] == "http://searx.example:8888"
        assert body["tavily_api_key_set"] is True
        assert "tavily_api_key" not in body

        disk = local.read_text(encoding="utf-8")
        assert "model-x" in disk and "secret123" in disk
        assert "searx.example" in disk and "tvly-secret" in disk
        assert config.config.llm.model == "model-x"
        assert config.config.llm.base_url == "http://example:9000/v1"
        assert (
            config.config.llm.model_base_urls
            == '{"model-x":"http://example:9000/v1","model-y":"http://example:9001/v1"}'
        )
        assert config.config.llm.model_extra_args == '{"model-x":{"extra_body":{"x":1}}}'
        assert config.config.agents.risk == "model-y"
        assert config.config.search.provider == "tavily"
        assert config.config.search.searxng_url == "http://searx.example:8888"
        assert config.config.search.tavily_api_key == "tvly-secret"

        r = client.post(
            "/api/config",
            json={
                "llm_base_url": "http://example:9000/v1",
                "llm_model": "model-z",
                "model_options": ["model-z"],
                "model_base_urls": {"model-z": "http://example:9002/v1"},
                "agent_models": {},
                "search_provider": "tavily",
                "searxng_url": "http://searx.example:8888",
            },
        )
        assert r.status_code == 200, r.text
        assert config.config.llm.api_key == "secret123"
        assert config.config.search.tavily_api_key == "tvly-secret"
        assert config.config.agents.risk == ""

        r = client.delete("/api/config")
        assert r.status_code == 200, r.text
        assert config.config.llm.model == "Qwen3.5-9B-Q4_K_M.gguf"
        assert config.config.llm.api_key == "dummy"
        assert config.config.agents.risk == "Qwen3.5-9B-Q4_K_M.gguf"
        assert config.config.search.provider == "searxng"
        assert config.config.search.searxng_url == "http://127.0.0.1:8888"
        assert config.config.search.tavily_api_key == ""
    finally:
        config.reload(fixture)


def test_config_rejects_bad_base_url_and_unknown_agent(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    import port.config as config
    from port.server import app

    fixture, local = _isolate_config_files(tmp_path, monkeypatch)
    client = TestClient(app)
    try:
        assert client.post("/api/config", json={"llm_base_url": "ftp://nope"}).status_code == 400
        assert (
            client.post(
                "/api/config",
                json={"model_base_urls": {"model-x": "ftp://nope"}},
            ).status_code
            == 400
        )
        assert (
            client.post("/api/config", json={"agent_models": {"bogus": "m"}}).status_code == 400
        )
        assert client.post("/api/config", json={"model_extra_args": "[]"}).status_code == 400
        assert client.post("/api/config", json={"model_extra_args": "{bad"}).status_code == 400
        assert client.post("/api/config", json={"searxng_url": "ftp://nope"}).status_code == 400
        assert client.post("/api/config", json={"search_provider": "bing"}).status_code == 400
        assert not local.exists()
    finally:
        config.reload(fixture)


def test_search_test_endpoint(tmp_path, monkeypatch):
    from starlette.testclient import TestClient

    import port.config as config
    import port.web.routes as routes
    from port.server import app

    fixture, _ = _isolate_config_files(tmp_path, monkeypatch)
    client = TestClient(app)

    async def ok_searxng(_url):
        return {"ok": True, "message": "SearXNG reachable."}

    async def bad_searxng(_url):
        return {"ok": False, "message": "SearXNG unreachable: boom"}

    async def ok_tavily(_key):
        return {"ok": True, "message": "Tavily key OK."}

    try:
        monkeypatch.setattr(routes, "_probe_searxng", ok_searxng)
        monkeypatch.setattr(routes, "_probe_tavily", ok_tavily)

        r = client.post(
            "/api/config/search/test", json={"search_provider": "searxng", "searxng_url": ""}
        )
        assert r.status_code == 400

        r = client.post("/api/config/search/test", json={"search_provider": "tavily"})
        assert r.status_code == 400

        r = client.post(
            "/api/config/search/test",
            json={"search_provider": "searxng", "searxng_url": "http://s:8888"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["message"] == "SearXNG reachable."

        r = client.post(
            "/api/config/search/test",
            json={"search_provider": "tavily", "tavily_api_key": "k"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["message"] == "Tavily key OK."

        monkeypatch.setattr(routes, "_probe_searxng", bad_searxng)
        r = client.post(
            "/api/config/search/test",
            json={"search_provider": "searxng", "searxng_url": "http://s:8888"},
        )
        assert r.status_code == 502
        assert "unreachable" in r.json()["detail"]

        r = client.post("/api/config/search/test", json={"search_provider": "bing"})
        assert r.status_code == 400
    finally:
        config.reload(fixture)


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
