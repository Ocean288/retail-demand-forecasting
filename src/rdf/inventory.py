"""Turn forecasts into stock decisions, and test those decisions on past weeks.

Policy (periodic review, order-up-to):
  Every Monday, order enough to bring stock on hand + on order up to
      S = forecast demand over the next (lead time + review period) weeks + safety stock
      safety stock = z x sigma x sqrt(lead time + review period)
  where sigma is the typical size of this model's recent 1-week forecast errors
  for that product, and z comes from the target service level
  (95% for A items -> z = 1.64, 90% for B items -> z = 1.28).

The dataset has no stock or supplier data, so the lead time (2 weeks) and the
service levels are assumptions, set in config.py.
"""
import numpy as np
import pandas as pd
from scipy.stats import norm

from . import config

WEEK = pd.Timedelta(weeks=1)
PROTECTION_WEEKS = config.LEAD_TIME_WEEKS + config.REVIEW_PERIOD_WEEKS


def z_value(service_level):
    """Standard-normal quantile: 0.95 -> 1.645, 0.90 -> 1.282."""
    return norm.ppf(np.asarray(service_level, float))


def safety_stock(sigma_weekly, service_level, weeks=PROTECTION_WEEKS):
    """z x sigma x sqrt(weeks): errors in different weeks partly cancel out."""
    return z_value(service_level) * np.asarray(sigma_weekly, float) * np.sqrt(weeks)


def error_sigma(backtest: pd.DataFrame, model: str, cutoff: pd.Timestamp,
                window: int = 12, min_points: int = 4) -> pd.Series:
    """Root-mean-square of the model's 1-week-ahead errors per product, using only
    forecasts whose outcome was already known at `cutoff`."""
    past = backtest[(backtest.model == model) & (backtest.horizon == 1) &
                    (backtest.target_week <= cutoff)]
    past = past.sort_values("target_week").groupby("sku").tail(window)
    err = past.assign(sq=(past.forecast - past.actual) ** 2).groupby("sku")
    rmse = np.sqrt(err.sq.mean())
    return rmse[err.size() >= min_points]


def order_up_to_levels(backtest: pd.DataFrame, model: str, abc: pd.DataFrame,
                       cutoff: pd.Timestamp) -> pd.DataFrame:
    """Order-up-to level S for every product at one cutoff."""
    fc = backtest[(backtest.model == model) & (backtest.cutoff == cutoff) &
                  (backtest.horizon <= PROTECTION_WEEKS)]
    demand = fc.groupby("sku").forecast.sum().rename("forecast_protection")
    sigma = error_sigma(backtest, model, cutoff).rename("sigma")
    out = pd.concat([demand, sigma], axis=1).dropna()
    level = abc.set_index("sku").abc_class.reindex(out.index).map(config.SERVICE_LEVEL)
    out["safety_stock"] = safety_stock(out.sigma, level)
    out["order_up_to"] = out.forecast_protection + out.safety_stock
    return out


def simulate(backtest: pd.DataFrame, model: str, abc: pd.DataFrame,
             actuals: pd.DataFrame, cutoffs: list) -> pd.DataFrame:
    """Replay the policy week by week with real demand (lost sales if out of stock).

    `actuals` is the products x weeks demand table. An order placed at the end of
    week t arrives at the start of week t + L + 1. Returns one row per product and week.
    """
    L = config.LEAD_TIME_WEEKS
    levels = {c: order_up_to_levels(backtest, model, abc, c) for c in cutoffs}
    skus = sorted(set.intersection(*(set(lv.index) for lv in levels.values())))

    on_hand = levels[cutoffs[0]].order_up_to.reindex(skus).to_numpy().copy()
    pipeline: dict[pd.Timestamp, np.ndarray] = {}
    rows = []
    for c in cutoffs:
        week = c + WEEK                       # the week that follows this Monday's order
        S = levels[c].order_up_to.reindex(skus).to_numpy()
        on_order = sum(pipeline.values()) if pipeline else np.zeros(len(skus))
        order = np.maximum(0.0, S - (on_hand + on_order))
        pipeline[c + (L + 1) * WEEK] = order

        on_hand = on_hand + pipeline.pop(week, 0.0)   # deliveries arriving this week
        demand = actuals[week].reindex(skus).to_numpy()
        sold = np.minimum(on_hand, demand)
        on_hand = on_hand - sold
        rows.append(pd.DataFrame({"model": model, "sku": skus, "week_start": week,
                                  "demand": demand, "sold": sold, "lost": demand - sold,
                                  "end_stock": on_hand, "order_qty": order,
                                  "order_up_to": S}))
    return pd.concat(rows, ignore_index=True)


def simulation_summary(sim: pd.DataFrame) -> pd.DataFrame:
    """Fill rate, average stock and stock-out frequency per model."""
    g = sim.groupby("model")
    weekly_demand = g.demand.sum() / sim.week_start.nunique()
    return pd.DataFrame({
        "fill_rate": g.sold.sum() / g.demand.sum(),
        "avg_stock_units": g.end_stock.sum() / sim.week_start.nunique(),
        "weeks_of_cover": (g.end_stock.sum() / sim.week_start.nunique()) / weekly_demand,
        "stockout_week_share": g.apply(lambda d: float(((d.lost > 0)).mean()),
                                       include_groups=False),
    }).reset_index()


def reorder_plan(future: pd.DataFrame, model_history: pd.DataFrame, abc: pd.DataFrame,
                 weekly: pd.DataFrame, cutoff: pd.Timestamp) -> pd.DataFrame:
    """Recommended safety stock and order-up-to level for each product after the
    last week of data. Stock on hand is not in the dataset, so the order quantity is
    order_up_to minus whatever is on hand and on order."""
    model = model_history.model.iloc[0]
    demand = (future[future.horizon <= PROTECTION_WEEKS]
              .groupby("sku").forecast.sum().rename("forecast_next_3_weeks"))
    weekly_fc = future.groupby("sku").forecast.mean().rename("forecast_avg_weekly")
    sigma = error_sigma(model_history, model, cutoff).rename("forecast_error_sigma")
    recent = (weekly[weekly.week_start > cutoff - 4 * WEEK]
              .groupby("sku").units.mean().rename("sales_avg_last_4_weeks"))
    info = abc.set_index("sku")[["abc_class", "revenue_52w"]]
    names = weekly.drop_duplicates("sku").set_index("sku").description
    plan = pd.concat([demand, weekly_fc, sigma], axis=1).dropna().join(info).join(recent)
    plan["service_level"] = plan.abc_class.map(config.SERVICE_LEVEL)
    plan["safety_stock"] = safety_stock(plan.forecast_error_sigma, plan.service_level)
    plan["order_up_to"] = plan.forecast_next_3_weeks + plan.safety_stock
    plan["safety_stock_weeks"] = plan.safety_stock / plan.forecast_avg_weekly.replace(0, np.nan)
    plan.insert(0, "description", names.reindex(plan.index))
    plan["model"] = model
    plan["plan_week"] = cutoff + WEEK
    plan = plan.reset_index().rename(columns={"index": "sku"})
    numeric = plan.select_dtypes("number").columns
    plan[numeric] = plan[numeric].round(2)
    return plan.sort_values("revenue_52w", ascending=False)
