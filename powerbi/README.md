# Power BI dashboard

The pipeline writes everything the dashboard needs to `outputs/`. This guide builds a
three-page report in Power BI Desktop (free, Windows only).

## 1. Load the data

Home → Get data → Text/CSV, and load these files from `outputs/`:

| File | One row per | Used on page |
| --- | --- | --- |
| `weekly_total.csv` | week | Demand |
| `weekly_demand.csv` | product × week | Demand |
| `products.csv` | product | all pages (ABC class, description) |
| `accuracy_by_model.csv` | model | Forecast accuracy |
| `accuracy_by_horizon.csv` | model × weeks ahead | Forecast accuracy |
| `backtest_forecasts_1week.csv` | model × product × week | Forecast accuracy |
| `simulation_summary.csv` | model | Inventory |
| `simulation_weekly.csv` | model × week | Inventory |
| `reorder_plan.csv` | product | Inventory |

In Power Query, check that `week_start`, `cutoff` and `target_week` are typed as **Date**
and that `sku` is **Text** (some codes such as `85123A` contain letters).

## 2. Relationships (Model view)

- `products[sku]` 1 → * `weekly_demand[sku]`
- `products[sku]` 1 → * `backtest_forecasts_1week[sku]`
- `products[sku]` 1 → 1 `reorder_plan[sku]`

Add a date table so weeks line up across files (Modeling → New table):

```DAX
Calendar = ADDCOLUMNS(
    CALENDAR(DATE(2009,11,30), DATE(2011,12,31)),
    "Week start", [Date] - WEEKDAY([Date], 3),
    "Year", YEAR([Date]),
    "Month", FORMAT([Date], "MMM yyyy"))
```

Relate `Calendar[Date]` to `weekly_demand[week_start]` and `backtest_forecasts_1week[target_week]`.

## 3. Measures

Create these in the `backtest_forecasts_1week` table:

```DAX
Units Actual   = SUM(backtest_forecasts_1week[actual])
Units Forecast = SUM(backtest_forecasts_1week[forecast])
Abs Error      = SUMX(backtest_forecasts_1week,
                      ABS(backtest_forecasts_1week[forecast] - backtest_forecasts_1week[actual]))
WAPE           = DIVIDE([Abs Error], [Units Actual])
Bias           = DIVIDE([Units Forecast] - [Units Actual], [Units Actual])
```

And in `weekly_demand`:

```DAX
Units Sold      = SUM(weekly_demand[units])
Revenue         = SUM(weekly_demand[revenue])
Units Last Year = CALCULATE([Units Sold], DATEADD(Calendar[Date], -364, DAY))
```

Format WAPE and Bias as percentages.

## 4. Pages

**Page 1 - Demand**
- Line chart: `Calendar[Week start]` × `[Units Sold]` (shows the Christmas peak in both years).
- Bar chart: top 15 products by `[Revenue]`, coloured by `products[abc_class]`.
- Cards: total revenue, number of products, share of revenue from A-class.
- Slicer: `products[abc_class]`.

**Page 2 - Forecast accuracy**
- Bar chart: `accuracy_by_model[model]` × `wape` (sorted, lowest first).
- Line chart: `accuracy_by_horizon[horizon]` × `wape`, legend = `model`.
- Line chart for one product: `target_week` × `[Units Actual]` and `[Units Forecast]`,
  with slicers for `model` and `products[description]` (single select).
- Table: products with the highest `[WAPE]` for the chosen model - the ones a planner
  should review by hand.

**Page 3 - Inventory**
- Scatter: `simulation_summary` with `weeks_of_cover` on X, `fill_rate` on Y, details = `model`.
- Table: `reorder_plan` - description, abc_class, forecast_avg_weekly, safety_stock,
  order_up_to, sales_avg_last_4_weeks. Conditional formatting on `safety_stock_weeks`.
- Line chart: `simulation_weekly[week_start]` × `lost`, legend = `model`
  (when and how much each forecast would have run out).

## 5. Save

Save as `powerbi/retail_demand_forecasting.pbix`, and export screenshots of each page to
`reports/figures/powerbi_*.png` so the README can show them without Power BI installed.
