"""FastAPI server entrypoint for the portfolio review GUI.

Implementation lives under :mod:`port.web`; this module keeps the historical
``port.server`` import path stable for uvicorn, tests, and external callers.
"""

from __future__ import annotations

import httpx

from port.bootstrap import bootstrap

bootstrap()

from port.graph import build_graph
from port.market_data import fetch_corporate_actions, fetch_position_snapshot
from port.web.api_models import LLMConfigBody, StartRequest
from port.web.app import app
from port.web.events import graph_agent_for_chain_event as _graph_agent_for_chain_event
from port.web.events import merge_agent_output as _merge_agent_output
from port.web.events import serialise as _serialise
from port.web.routes import (
    _enrich_portfolio_actions,
    _llm_chat_completions_url,
    _position_actions_supplied,
    _reviews,
)
from port.web.sessions import ReviewSession

__all__ = [
    "LLMConfigBody",
    "ReviewSession",
    "StartRequest",
    "_enrich_portfolio_actions",
    "_graph_agent_for_chain_event",
    "_llm_chat_completions_url",
    "_merge_agent_output",
    "_position_actions_supplied",
    "_reviews",
    "_serialise",
    "app",
    "build_graph",
    "fetch_corporate_actions",
    "fetch_position_snapshot",
    "httpx",
]
