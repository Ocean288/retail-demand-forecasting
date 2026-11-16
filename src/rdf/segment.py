"""ABC classification, choosing which products to forecast, and outlier capping."""
import numpy as np
import pandas as pd

from . import config


def abc_classes(weekly: pd.DataFrame, end_week: str) -> pd.DataFrame:
    """Rank products by revenue over the 52 weeks up to end_week.

    A = products making up the first 80% of revenue, B = the next 15%, C = the rest.
    Also records the share of those weeks in which the product sold at all.
    """
    end = pd.Timestamp(end_week)
    year = weekly[(weekly.week_start > end - pd.Timedelta(weeks=52)) & (weekly.week_start <= end)]
    summary = (year.groupby("sku")
               .agg(revenue_52w=("revenue", "sum"),
                    units_52w=("units", "sum"),
                    active_week_share=("units", lambda s: float((s > 0).mean())))
               .sort_values("revenue_52w", ascending=False))
    summary = summary[summary.revenue_52w > 0]
    cumulative = summary.revenue_52w.cumsum() / summary.revenue_52w.sum()
    # A product is A-class if the products ranked above it make up less than 80%.
    previous = cumulative.shift(fill_value=0)
    summary["abc_class"] = np.select(
        [previous < config.ABC_A_SHARE, previous < config.ABC_B_SHARE], ["A", "B"], "C")
    summary["revenue_rank"] = np.arange(1, len(summary) + 1)
    return summary.reset_index()


def select_products(abc: pd.DataFrame) -> list[str]:
    """A and B products that sell in most weeks (the ones these models suit)."""
    keep = abc[abc.abc_class.isin(["A", "B"]) &
               (abc.active_week_share >= config.MIN_ACTIVE_WEEK_SHARE)]
    return sorted(keep.sku)


def cap_outliers(weekly: pd.DataFrame, fit_until: str) -> pd.DataFrame:
    """Cap unusually large weeks (one-off bulk orders) per product.

    The cap is Q3 + 3 x IQR of the product's non-zero weeks (Tukey's "far out"
    fence), computed only from weeks up to fit_until so the backtest period
    never influences it. Adds `units_capped`; `units` keeps the original value.
    """
    history = weekly[(weekly.week_start <= pd.Timestamp(fit_until)) & (weekly.units > 0)]
    q = history.groupby("sku").units.quantile([0.25, 0.75]).unstack()
    caps = (q[0.75] + 3 * (q[0.75] - q[0.25])).rename("cap")
    out = weekly.merge(caps, left_on="sku", right_index=True, how="left")
    out["units_capped"] = np.minimum(out.units, out.cap.fillna(np.inf))
    return out.drop(columns="cap")
