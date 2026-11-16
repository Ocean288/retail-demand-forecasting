-- Turn raw invoice lines into clean product sales.
-- Input:  raw_lines (one row per invoice line, both years, dates as ISO text)
-- Output: clean_lines (view)

DROP VIEW IF EXISTS cancellations;
CREATE VIEW cancellations AS
SELECT invoice, sku, customer_id, -quantity AS quantity, invoice_ts
FROM raw_lines
WHERE invoice LIKE 'C%' AND quantity < 0;

DROP VIEW IF EXISTS clean_lines;
CREATE VIEW clean_lines AS
SELECT
    r.invoice,
    r.sku,
    r.description,
    r.quantity,
    r.unit_price,
    r.customer_id,
    r.country,
    r.invoice_ts,
    -- Monday of the invoice's week (SQLite: go back 6 days, then forward to Monday)
    date(r.invoice_ts, '-6 days', 'weekday 1') AS week_start
FROM raw_lines AS r
WHERE r.invoice NOT LIKE 'C%'                      -- 1. not a cancellation invoice
  AND r.quantity > 0                               -- 2. not a return or stock adjustment
  AND r.unit_price > 0                             -- 3. not a free sample or write-off
  AND (r.sku GLOB '[0-9][0-9][0-9][0-9][0-9]'      -- 4. a real product code:
       OR r.sku GLOB '[0-9][0-9][0-9][0-9][0-9][A-Za-z]'   --    5 digits, optionally
       OR r.sku GLOB '[0-9][0-9][0-9][0-9][0-9][A-Za-z][A-Za-z]') -- followed by 1-2 letters
                                                   --    (drops POSTAGE, fees, manual adjustments)
  AND NOT EXISTS (                                 -- 5. not later cancelled in full by
      SELECT 1 FROM cancellations AS c             --    the same customer
      WHERE c.sku = r.sku
        AND c.customer_id = r.customer_id
        AND c.quantity = r.quantity
        AND c.invoice_ts >= r.invoice_ts
  );
