-- Weekly units and revenue per product, with a row for every week
-- (weeks with no sales get 0, which matters for forecasting).
-- Parameter :last_week = last complete week (Monday, ISO date).

DROP TABLE IF EXISTS weekly_demand;
CREATE TABLE weekly_demand AS
WITH RECURSIVE
calendar(week_start) AS (                      -- every Monday in the data range
    SELECT MIN(week_start) FROM clean_lines
    UNION ALL
    SELECT date(week_start, '+7 days') FROM calendar
    WHERE week_start < :last_week
),
products AS (
    SELECT sku FROM clean_lines GROUP BY sku
),
sales AS (
    SELECT sku, week_start,
           SUM(quantity)              AS units,
           SUM(quantity * unit_price) AS revenue,
           COUNT(DISTINCT invoice)    AS orders
    FROM clean_lines
    WHERE week_start <= :last_week
    GROUP BY sku, week_start
)
SELECT p.sku,
       c.week_start,
       COALESCE(s.units, 0)   AS units,
       COALESCE(s.revenue, 0) AS revenue,
       COALESCE(s.orders, 0)  AS orders
FROM products AS p
CROSS JOIN calendar AS c
LEFT JOIN sales AS s
       ON s.sku = p.sku AND s.week_start = c.week_start;

CREATE INDEX idx_weekly_sku_week ON weekly_demand (sku, week_start);

-- One description per product: the one used most often.
DROP TABLE IF EXISTS product_names;
CREATE TABLE product_names AS
SELECT sku, description
FROM (
    SELECT sku, description,
           ROW_NUMBER() OVER (PARTITION BY sku ORDER BY COUNT(*) DESC) AS rn
    FROM clean_lines
    WHERE description IS NOT NULL
    GROUP BY sku, description
)
WHERE rn = 1;
