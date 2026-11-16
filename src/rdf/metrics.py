"""Forecast accuracy measures.

WAPE is the headline measure: total absolute error divided by total actual units.
Unlike MAPE it still works when a product sells zero in a week, and it weights
each product by how much it sells, which is what matters for stock.
"""
import numpy as np


def wape(actual, forecast) -> float:
    """Weighted absolute percentage error: sum|A - F| / sum A."""
    actual, forecast = np.asarray(actual, float), np.asarray(forecast, float)
    return float(np.abs(actual - forecast).sum() / actual.sum())


def bias(actual, forecast) -> float:
    """Sum(F - A) / sum A. Positive = forecasts too high (risk of overstock)."""
    actual, forecast = np.asarray(actual, float), np.asarray(forecast, float)
    return float((forecast - actual).sum() / actual.sum())


def mae(actual, forecast) -> float:
    actual, forecast = np.asarray(actual, float), np.asarray(forecast, float)
    return float(np.abs(actual - forecast).mean())


def mape(actual, forecast) -> float:
    """Mean absolute percentage error over weeks with non-zero sales only.

    Shown for comparison; it overweights slow weeks (selling 1 instead of 2
    counts as a 50% error), which is why WAPE is the headline measure.
    """
    actual, forecast = np.asarray(actual, float), np.asarray(forecast, float)
    mask = actual > 0
    return float(np.mean(np.abs(actual[mask] - forecast[mask]) / actual[mask]))
