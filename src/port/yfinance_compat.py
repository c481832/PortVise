"""Compatibility wrappers for noisy third-party yfinance internals."""

from __future__ import annotations

import warnings
from contextlib import contextmanager

from pandas.errors import Pandas4Warning


@contextmanager
def suppress_yfinance_pandas4_warnings():
    """Hide yfinance's internal deprecated ``Timestamp.utcnow`` warning."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Timestamp\.utcnow is deprecated.*",
            category=Pandas4Warning,
            module=r"yfinance\.scrapers\.history",
        )
        yield
