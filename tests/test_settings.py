from __future__ import annotations

import os
from unittest.mock import patch


def test_settings_defaults():
    """Settings should have sensible defaults without any .env file."""
    from port.config import Settings

    s = Settings(_env_file=None)
    assert s.llm_base_url == "http://localhost:8003/v1"
    assert s.llm_model == "Qwen3.5-35B-A3B-UD-Q6_K_S.gguf"
    assert s.fast_llm_base_url == "http://localhost:8000/v1"
    assert s.fast_llm_model == "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
    assert s.llm_api_key == "dummy"


def test_settings_upper_case_env():
    """Settings should pick up ALL_CAPS env vars."""
    from port.config import Settings

    with patch.dict(os.environ, {"LLM_BASE_URL": "http://custom:9999/v1"}, clear=False):
        s = Settings(_env_file=None)
        assert s.llm_base_url == "http://custom:9999/v1"


def test_settings_lower_case_env():
    """Settings should pick up lowercase env vars too."""
    from port.config import Settings

    with patch.dict(os.environ, {"llm_base_url": "http://custom:8888/v1"}, clear=False):
        s = Settings(_env_file=None)
        assert s.llm_base_url == "http://custom:8888/v1"
