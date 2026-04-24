from __future__ import annotations

from unittest.mock import patch

import run


def test_main_defaults_to_port_7860() -> None:
    with patch("sys.argv", ["run.py"]), patch("uvicorn.run") as uvicorn_run:
        run.main()

    assert uvicorn_run.call_args.kwargs["port"] == 7860
