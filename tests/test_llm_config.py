from __future__ import annotations

from port.config import LLMOverrides, freeze_agent_models, llm_runtime_overrides, make_llm


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
        assert llm.openai_api_key.get_secret_value() == "custom-key"
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
