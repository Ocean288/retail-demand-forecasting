"""Forecasting models.

Every model answers the same question: standing at the end of week `cutoff`,
how many units will each product sell in each of the next H weeks?

Baselines (no fitting):
  naive        - next weeks = last week
  moving_avg_4 - next weeks = average of the last 4 weeks
  seasonal     - next weeks = the same weeks last year

Statistical:
  ets          - Holt's exponential smoothing with a damped trend, one model per product

Machine learning:
  gbm          - one gradient-boosted tree model for all products together, trained on
                 "what we knew at a past week -> what sold h weeks later" examples
"""
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from statsmodels.tsa.holtwinters import ExponentialSmoothing

WEEK = pd.Timedelta(weeks=1)


def _history(panel: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Demand up to and including the cutoff week, as a products x weeks table."""
    return panel.loc[:, panel.columns <= cutoff]


def naive(panel, cutoff, horizon):
    last = _history(panel, cutoff).iloc[:, -1]
    return {h: last for h in range(1, horizon + 1)}


def moving_avg_4(panel, cutoff, horizon):
    mean = _history(panel, cutoff).iloc[:, -4:].mean(axis=1)
    return {h: mean for h in range(1, horizon + 1)}


def seasonal(panel, cutoff, horizon):
    """Same week last year (52 weeks earlier), averaged with the weeks either side
    to smooth out which exact weekday a holiday fell on."""
    out = {}
    for h in range(1, horizon + 1):
        target = cutoff + h * WEEK
        weeks = [target - 52 * WEEK + k * WEEK for k in (-1, 0, 1)]
        out[h] = panel.reindex(columns=weeks).mean(axis=1)
    return out


def ets(panel, cutoff, horizon):
    """Damped-trend exponential smoothing, fitted separately for each product."""
    history = _history(panel, cutoff)
    rows = {}
    for sku, series in history.iterrows():
        y = series.to_numpy(float)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fit = ExponentialSmoothing(y, trend="add", damped_trend=True,
                                           initialization_method="estimated").fit()
            rows[sku] = np.clip(fit.forecast(horizon), 0, None)
        except Exception:  # very short or flat series: fall back to the 4-week average
            rows[sku] = np.repeat(y[-4:].mean(), horizon)
    table = pd.DataFrame.from_dict(rows, orient="index")
    return {h: table[h - 1] for h in range(1, horizon + 1)}


# ---------- machine-learning model ----------

FEATURES = ["horizon", "last_week", "mean_4", "mean_12", "std_12",
            "last_year_same_week", "last_year_ratio", "target_week_of_year", "avg_price"]


def _features_at(panel, prices, origin, horizon):
    """Feature rows for every product, using only information available at `origin`."""
    hist = _history(panel, origin)
    rows = []
    for h in range(1, horizon + 1):
        target = origin + h * WEEK
        ly_weeks = [target - 52 * WEEK + k * WEEK for k in (-1, 0, 1)]
        ly_now = [origin - 52 * WEEK + k * WEEK for k in (-3, -2, -1, 0)]
        last_year_same = panel.reindex(columns=ly_weeks).mean(axis=1)
        last_year_recent = panel.reindex(columns=ly_now).mean(axis=1)
        mean_4 = hist.iloc[:, -4:].mean(axis=1)
        rows.append(pd.DataFrame({
            "sku": panel.index,
            "origin": origin,
            "target_week": target,
            "horizon": h,
            "last_week": hist.iloc[:, -1],
            "mean_4": mean_4,
            "mean_12": hist.iloc[:, -12:].mean(axis=1),
            "std_12": hist.iloc[:, -12:].std(axis=1),
            "last_year_same_week": last_year_same,
            # How last year's demand moved from "now" to the target week:
            # captures seasonal ramps such as the run-up to Christmas.
            "last_year_ratio": (last_year_same + 1) / (last_year_recent + 1),
            "target_week_of_year": target.isocalendar().week,
            "avg_price": prices,
        }))
    return pd.concat(rows, ignore_index=True)


def gbm(panel, cutoff, horizon, prices, min_history_weeks=12):
    """Train on every past origin that has known outcomes, then predict from `cutoff`."""
    weeks = panel.columns
    first_origin = weeks[0] + (min_history_weeks - 1) * WEEK
    train_parts = []
    for origin in weeks[(weeks >= first_origin) & (weeks <= cutoff - WEEK)]:
        feats = _features_at(panel, prices, origin, horizon)
        target_weeks = feats.target_week
        known = target_weeks <= cutoff  # never train on weeks after the cutoff
        feats = feats[known]
        feats["y"] = [panel.at[s, w] for s, w in zip(feats.sku, feats.target_week)]
        train_parts.append(feats)
    train = pd.concat(train_parts, ignore_index=True)

    model = HistGradientBoostingRegressor(loss="poisson", max_iter=300, learning_rate=0.05,
                                          max_leaf_nodes=31, min_samples_leaf=50,
                                          random_state=0)
    model.fit(train[FEATURES], train["y"])

    future = _features_at(panel, prices, cutoff, horizon)
    future["forecast"] = model.predict(future[FEATURES])
    return {h: future[future.horizon == h].set_index("sku")["forecast"]
            for h in range(1, horizon + 1)}


MODELS = {
    "naive": naive,
    "moving_avg_4": moving_avg_4,
    "seasonal": seasonal,
    "ets": ets,
    "gbm": gbm,
}
