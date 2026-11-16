"""Charts for the README (saved as PNG in reports/figures/)."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import config  # noqa: E402

INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, AXIS, SURFACE = "#e1e0d9", "#c3c2b7", "#fcfcfb"
# Fixed colour per model so it never changes between charts.
MODEL_COLOURS = {"naive": "#2a78d6", "moving_avg_4": "#eb6834", "seasonal": "#1baf7a",
                 "ets": "#eda100", "gbm": "#6250d6"}
MODEL_LABELS = {"naive": "Naive (last week)", "moving_avg_4": "4-week average",
                "seasonal": "Same weeks last year", "ets": "Exponential smoothing",
                "gbm": "Gradient boosting"}

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
    "axes.titlesize": 13, "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": MUTED, "ytick.color": MUTED, "font.size": 10,
    "legend.frameon": False,
})


def _save(fig, name):
    fig.tight_layout()
    fig.savefig(config.FIGURE_DIR / name, dpi=150)
    plt.close(fig)


def weekly_total(weekly: pd.DataFrame):
    total = weekly.groupby("week_start").units.sum() / 1000
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.axvspan(pd.Timestamp(config.FIRST_CUTOFF), pd.Timestamp(config.LAST_FULL_WEEK),
               color=GRID, alpha=0.6, lw=0)
    ax.plot(total.index, total.values, color=MODEL_COLOURS["naive"], lw=2)
    ax.text(pd.Timestamp(config.FIRST_CUTOFF) + pd.Timedelta(days=5), total.max() * 0.97,
            "backtest period", color=INK_2, va="top")
    ax.set_title("Weekly units sold, all products")
    ax.set_ylabel("Thousand units")
    ax.grid(axis="x", visible=False)
    _save(fig, "weekly_total_demand.png")


def accuracy_by_model(acc: pd.DataFrame, best: str):
    acc = acc.sort_values("wape", ascending=False)
    fig, ax = plt.subplots(figsize=(7, 3.2))
    colours = [MODEL_COLOURS[best] if m == best else AXIS for m in acc.model]
    ax.barh([MODEL_LABELS[m] for m in acc.model], acc.wape * 100, color=colours, height=0.6)
    for y, v in enumerate(acc.wape * 100):
        ax.text(v + 0.8, y, f"{v:.1f}%", va="center", color=INK)
    ax.set_title("Forecast error by model (WAPE, lower is better)")
    ax.set_xlabel("WAPE, weekly forecasts 1-4 weeks ahead (%)")
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, acc.wape.max() * 100 * 1.15)
    _save(fig, "accuracy_by_model.png")


def accuracy_by_horizon(acc_h: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for model, g in acc_h.groupby("model"):
        ax.plot(g.horizon, g.wape * 100, marker="o", ms=6, lw=2,
                color=MODEL_COLOURS[model], label=MODEL_LABELS[model])
    ax.set_xticks(sorted(acc_h.horizon.unique()))
    ax.set_xlabel("Weeks ahead")
    ax.set_ylabel("WAPE (%)")
    ax.set_title("Error by weeks ahead: smoothing models beat simple rules")
    ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5))
    _save(fig, "accuracy_by_horizon.png")


def example_product(weekly: pd.DataFrame, results: pd.DataFrame, best: str):
    top = (weekly[weekly.sku.isin(results.sku.unique())]
           .groupby("sku").revenue.sum().idxmax())
    name = weekly.loc[weekly.sku == top, "description"].iloc[0]
    hist = weekly[(weekly.sku == top) &
                  (weekly.week_start >= pd.Timestamp(config.FIRST_CUTOFF) - pd.Timedelta(weeks=12))]
    fc = results[(results.sku == top) & (results.horizon == 1)]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(hist.week_start, hist.units_capped, color=INK_2, lw=2, label="Actual")
    for model, ls in ((best, "-"), ("moving_avg_4", "--")):
        g = fc[fc.model == model]
        ax.plot(g.target_week, g.forecast, color=MODEL_COLOURS[model], lw=2, ls=ls,
                label=f"{MODEL_LABELS[model]} (1 week ahead)")
    ax.set_title(f"Example: {name.title()} (product {top})")
    ax.set_ylabel("Units per week")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=3)
    _save(fig, "example_product_forecast.png")


def stock_tradeoff(sim_summary: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(7, 4))
    for _, r in sim_summary.iterrows():
        ax.scatter(r.weeks_of_cover, r.fill_rate * 100, s=80,
                   color=MODEL_COLOURS[r.model], edgecolor=SURFACE, linewidth=2, zorder=3)
        ax.annotate(MODEL_LABELS[r.model], (r.weeks_of_cover, r.fill_rate * 100),
                    xytext=(8, 4), textcoords="offset points", color=INK)
    ax.set_xlabel("Average stock held (weeks of demand)")
    ax.set_ylabel("Fill rate (% of demand served)")
    ax.set_title("Service vs stock in a 2-week lead-time simulation")
    ax.margins(x=0.25, y=0.2)
    _save(fig, "stock_tradeoff.png")


def make_all(weekly, results, acc, acc_h, sim_summary, best):
    weekly_total(weekly)
    accuracy_by_model(acc, best)
    accuracy_by_horizon(acc_h)
    example_product(weekly, results, best)
    stock_tradeoff(sim_summary)
