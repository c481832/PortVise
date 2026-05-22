from __future__ import annotations

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

import port.config as config_module
from port.config import ConfigNotLoadedError, RootConfig, reload


def _minimal_toml() -> str:
    """Return the canonical config.toml verbatim — tests use it as a starting point."""
    return (Path(__file__).resolve().parent / "fixtures" / "test_config.toml").read_text()


def test_load_returns_root_config(tmp_path: Path):
    toml = tmp_path / "config.toml"
    toml.write_text(_minimal_toml())
    cfg = reload(toml)
    assert isinstance(cfg, RootConfig)
    assert cfg.llm.base_url.startswith("http://")
    assert cfg.llm.model
    assert cfg.server.port > 0


def test_load_env_override_applies(tmp_path: Path):
    toml = tmp_path / "config.toml"
    toml.write_text(_minimal_toml())
    with patch.dict(os.environ, {"LLM_BASE_URL": "http://custom:9999/v1"}, clear=False):
        cfg = reload(toml)
        assert cfg.llm.base_url == "http://custom:9999/v1"


def test_config_proxy_raises_before_load(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config_module, "_loaded", None)
    with pytest.raises(ConfigNotLoadedError):
        _ = config_module.config.llm.base_url


def test_load_rejects_missing_required_field(tmp_path: Path):
    broken = textwrap.dedent(
        """
        [llm]
        # base_url omitted
        model = "x"
        """
    )
    toml = tmp_path / "broken.toml"
    toml.write_text(broken)
    with pytest.raises(Exception):
        reload(toml)


def test_load_missing_file_raises(tmp_path: Path):
    missing = tmp_path / "does_not_exist.toml"
    with pytest.raises(FileNotFoundError):
        reload(missing)
