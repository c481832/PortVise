"""Small numeric helpers (no NumPy — keeps the stack lightweight)."""

from __future__ import annotations


def compute_trend(values: list[float]) -> float:
    """Simple end-minus-start trend per step; empty or singleton → 0."""
    if len(values) < 2:
        return 0.0
    return (values[-1] - values[0]) / (len(values) - 1)


def simple_linear_slope(y: list[float]) -> float:
    """OLS slope of y vs 0..n-1; for optional factor/return fits without NumPy."""
    n = len(y)
    if n < 2:
        return 0.0
    mean_y = sum(y) / n
    mean_x = (n - 1) / 2.0
    var_x = sum((i - mean_x) ** 2 for i in range(n))
    if var_x == 0:
        return 0.0
    cov_xy = sum((i - mean_x) * (y[i] - mean_y) for i in range(n))
    return cov_xy / var_x
