import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rdf import data, inventory, metrics, models, segment  # noqa: E402


# ---------- metrics ----------

def test_wape_and_bias():
    actual = [10, 0, 30]
    forecast = [12, 2, 24]
    assert metrics.wape(actual, forecast) == pytest.approx(10 / 40)
    assert metrics.bias(actual, forecast) == pytest.approx(-2 / 40)


def test_mape_ignores_zero_weeks():
    assert metrics.mape([0, 10], [5, 5]) == pytest.approx(0.5)


# ---------- SQL cleaning ----------

def _raw(rows):
    cols = ["invoice", "sku", "description", "quantity", "unit_price",
            "customer_id", "country", "invoice_ts"]
    return pd.DataFrame(rows, columns=cols)


def test_cleaning_rules():
    con = sqlite3.connect(":memory:")
    _raw([
        ("1", "21232", "MUG", 6, 1.5, "100", "UK", "2011-01-03 10:00:00"),       # keep
        ("C2", "21232", "MUG", -6, 1.5, "100", "UK", "2011-01-04 10:00:00"),     # cancellation
        ("3", "POST", "POSTAGE", 1, 18.0, "100", "UK", "2011-01-03 10:00:00"),   # not a product
        ("4", "22423", "CAKESTAND", 2, 0.0, "100", "UK", "2011-01-03 10:00:00"), # zero price
        ("5", "85123A", "T-LIGHT", 12, 2.55, "200", "UK", "2011-01-05 10:00:00"),  # keep
    ]).to_sql("raw_lines", con, index=False)
    data.run_sql_file(con, "01_clean_lines.sql")
    kept = pd.read_sql("SELECT invoice, week_start FROM clean_lines ORDER BY invoice", con)
    # Order 1 was cancelled in full by C2 for the same customer and quantity.
    assert kept.invoice.tolist() == ["5"]
    assert kept.week_start.tolist() == ["2011-01-03"]  # a Monday


def test_weekly_table_fills_missing_weeks_with_zero():
    con = sqlite3.connect(":memory:")
    _raw([
        ("1", "21232", "MUG", 6, 1.0, "1", "UK", "2011-01-03 10:00:00"),
        ("2", "21232", "MUG", 4, 1.0, "1", "UK", "2011-01-17 10:00:00"),
    ]).to_sql("raw_lines", con, index=False)
    data.run_sql_file(con, "01_clean_lines.sql")
    data.run_sql_file(con, "02_weekly_demand.sql", {"last_week": "2011-01-17"})
    weekly = pd.read_sql("SELECT week_start, units FROM weekly_demand ORDER BY week_start", con)
    assert weekly.units.tolist() == [6, 0, 4]


# ---------- segmentation ----------

def _weekly(values_by_sku, start="2011-01-03"):
    weeks = pd.date_range(start, periods=len(next(iter(values_by_sku.values()))), freq="7D")
    rows = [(sku, w, u, u * 1.0) for sku, vals in values_by_sku.items() for w, u in zip(weeks, vals)]
    return pd.DataFrame(rows, columns=["sku", "week_start", "units", "revenue"])


def test_abc_classes():
    weekly = _weekly({"a": [80] * 10, "b": [15] * 10, "c": [5] * 10})
    abc = segment.abc_classes(weekly, weekly.week_start.max()).set_index("sku")
    assert abc.abc_class.to_dict() == {"a": "A", "b": "B", "c": "C"}


def test_outlier_cap_uses_only_history():
    weekly = _weekly({"a": [10, 11, 9, 10, 12, 10, 500]})
    capped = segment.cap_outliers(weekly, weekly.week_start.iloc[5])
    assert capped.units_capped.iloc[-1] < 500
    assert capped.units_capped.iloc[:6].tolist() == weekly.units.iloc[:6].tolist()


# ---------- models never look past the cutoff ----------

def test_baselines_use_only_past_data():
    weeks = pd.date_range("2011-01-03", periods=60, freq="7D")
    panel = pd.DataFrame([np.arange(60, dtype=float)], index=["a"], columns=weeks)
    cutoff = weeks[55]
    assert models.naive(panel, cutoff, 2)[1]["a"] == 55
    assert models.moving_avg_4(panel, cutoff, 1)[1]["a"] == pytest.approx(53.5)
    # Same week last year for target week 56 = weeks 3, 4, 5 -> mean 4.
    assert models.seasonal(panel, cutoff, 1)[1]["a"] == pytest.approx(4)


# ---------- inventory ----------

def test_safety_stock_formula():
    # z(95%) = 1.645, sigma 10, 3 weeks of exposure -> 1.645 * 10 * sqrt(3)
    assert inventory.safety_stock(10, 0.95, weeks=3) == pytest.approx(28.49, abs=0.01)


def test_simulation_serves_demand_when_forecast_is_perfect():
    weeks = pd.date_range("2011-01-03", periods=20, freq="7D")
    actual = pd.DataFrame([[10.0] * 20], index=["a"], columns=weeks)
    rows = []
    for c in weeks[:14]:
        for h in range(1, 5):
            t = c + h * pd.Timedelta(weeks=1)
            rows.append(("m", "a", c, h, t, 10.0, 10.0))
    bt = pd.DataFrame(rows, columns=["model", "sku", "cutoff", "horizon",
                                     "target_week", "forecast", "actual"])
    abc = pd.DataFrame({"sku": ["a"], "abc_class": ["A"]})
    sim = inventory.simulate(bt, "m", abc, actual, cutoffs=list(weeks[6:14]))
    assert sim.lost.sum() == 0
    assert sim.sold.sum() == sim.demand.sum()
