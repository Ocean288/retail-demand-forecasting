"""Rolling-origin backtest.

Pretend it is Monday of each cutoff week, give every model only the data up to
then, forecast the next 1-4 weeks, and compare with what actually sold. Repeating
this over many cutoffs gives an honest estimate of accuracy on unseen weeks.
"""
import pandas as pd

from . import config, metrics
from .models import MODELS

WEEK = pd.Timedelta(weeks=1)


def make_panel(weekly: pd.DataFrame, skus: list[str], value: str = "units_capped") -> pd.DataFrame:
    """products x weeks table of demand."""
    sub = weekly[weekly.sku.isin(skus)]
    return sub.pivot(index="sku", columns="week_start", values=value).sort_index()


def run_backtest(weekly: pd.DataFrame, skus: list[str], models=None) -> pd.DataFrame:
    """One row per model x product x cutoff x horizon with forecast and actual."""
    models = models or list(MODELS)
    panel = make_panel(weekly, skus)
    prices = (weekly[weekly.sku.isin(skus) & (weekly.units > 0)]
              .assign(price=lambda d: d.revenue / d.units)
              .groupby("sku").price.median().reindex(panel.index))

    cutoffs = pd.date_range(config.FIRST_CUTOFF, config.LAST_CUTOFF, freq="7D")
    rows = []
    for cutoff in cutoffs:
        for name in models:
            fn = MODELS[name]
            kwargs = {"prices": prices} if name == "gbm" else {}
            preds = fn(panel, cutoff, config.HORIZON_WEEKS, **kwargs)
            for h, forecast in preds.items():
                target = cutoff + h * WEEK
                rows.append(pd.DataFrame({
                    "model": name,
                    "sku": panel.index,
                    "cutoff": cutoff,
                    "horizon": h,
                    "target_week": target,
                    "forecast": forecast.reindex(panel.index).fillna(0).clip(lower=0).to_numpy(),
                    "actual": panel[target].to_numpy(),
                }))
        print(f"  cutoff {cutoff.date()} done")
    return pd.concat(rows, ignore_index=True)


def score(results: pd.DataFrame, by=("model",)) -> pd.DataFrame:
    """Accuracy table grouped by the given columns."""
    def _score(g):
        return pd.Series({
            "wape": metrics.wape(g.actual, g.forecast),
            "bias": metrics.bias(g.actual, g.forecast),
            "mae": metrics.mae(g.actual, g.forecast),
            "mape": metrics.mape(g.actual, g.forecast),
            "forecasts": len(g),
        })
    return results.groupby(list(by)).apply(_score, include_groups=False).reset_index()


def forecast_future(weekly: pd.DataFrame, skus: list[str], model: str,
                    cutoff: str) -> pd.DataFrame:
    """Forecast the weeks after the last week of data (no actuals to compare with)."""
    panel = make_panel(weekly, skus)
    cutoff = pd.Timestamp(cutoff)
    kwargs = {}
    if model == "gbm":
        kwargs["prices"] = (weekly[weekly.sku.isin(skus) & (weekly.units > 0)]
                            .assign(price=lambda d: d.revenue / d.units)
                            .groupby("sku").price.median().reindex(panel.index))
    preds = MODELS[model](panel, cutoff, config.HORIZON_WEEKS, **kwargs)
    return pd.concat(
        [pd.DataFrame({"sku": panel.index, "horizon": h,
                       "target_week": cutoff + h * WEEK,
                       "forecast": f.reindex(panel.index).fillna(0).clip(lower=0).to_numpy()})
         for h, f in preds.items()],
        ignore_index=True)


def score_lead_time(results: pd.DataFrame, weeks: int) -> pd.DataFrame:
    """Accuracy of total demand over the next `weeks` weeks - what a reorder decision
    actually depends on. Weekly errors partly cancel out over a few weeks."""
    lt = (results[results.horizon <= weeks]
          .groupby(["model", "sku", "cutoff"])[["forecast", "actual"]].sum()
          .reset_index())
    return score(lt)
