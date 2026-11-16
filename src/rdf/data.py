"""Download the raw files, load them into SQLite, and run the SQL cleaning steps."""
import sqlite3
import urllib.request

import pandas as pd

from . import config


def download_raw(force: bool = False) -> None:
    """Fetch both CSV files into data/raw/ (about 90 MB in total)."""
    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    for spec in config.RAW_FILES.values():
        target = config.RAW_DIR / spec["file"]
        if target.exists() and not force:
            continue
        print(f"Downloading {spec['file']} ...")
        urllib.request.urlretrieve(spec["url"], target)


def read_raw() -> pd.DataFrame:
    """Read both years into one table with the same column names and ISO timestamps."""
    columns = ["invoice", "sku", "description", "quantity",
               "invoice_date", "unit_price", "customer_id", "country"]
    parts = []
    for name, spec in config.RAW_FILES.items():
        df = pd.read_csv(config.RAW_DIR / spec["file"], dtype=str, encoding=spec["encoding"])
        df.columns = columns
        df["invoice_ts"] = pd.to_datetime(df["invoice_date"], format=spec["date_format"])
        if name == "year1":
            # Rows from 1 Dec 2010 on also appear in the year-2 file.
            df = df[df["invoice_ts"] < config.YEAR2_START]
        parts.append(df)

    raw = pd.concat(parts, ignore_index=True)
    raw["quantity"] = raw["quantity"].astype(int)
    raw["unit_price"] = raw["unit_price"].astype(float)
    raw["sku"] = raw["sku"].str.strip().str.upper()
    raw["description"] = raw["description"].str.strip()
    raw["invoice_ts"] = raw["invoice_ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return raw.drop(columns="invoice_date")


def run_sql_file(con: sqlite3.Connection, name: str, params: dict | None = None) -> None:
    """Run every statement in a .sql file. Named parameters look like :last_week."""
    text = (config.SQL_DIR / name).read_text(encoding="utf-8")
    for statement in text.split(";"):
        if statement.strip():
            con.execute(statement, params or {})
    con.commit()


def build_database() -> sqlite3.Connection:
    """Raw CSV -> SQLite table raw_lines -> clean_lines view -> weekly_demand table."""
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if config.DB_PATH.exists():
        config.DB_PATH.unlink()
    con = sqlite3.connect(config.DB_PATH)

    raw = read_raw()
    raw.to_sql("raw_lines", con, index=False)
    con.execute("CREATE INDEX idx_raw_match ON raw_lines (sku, customer_id, quantity)")

    run_sql_file(con, "01_clean_lines.sql")
    run_sql_file(con, "02_weekly_demand.sql", {"last_week": config.LAST_FULL_WEEK})
    return con


def cleaning_summary(con: sqlite3.Connection) -> pd.DataFrame:
    """How many invoice lines are left after each cleaning rule (for the README)."""
    product_code = """(sku GLOB '[0-9][0-9][0-9][0-9][0-9]'
                       OR sku GLOB '[0-9][0-9][0-9][0-9][0-9][A-Za-z]'
                       OR sku GLOB '[0-9][0-9][0-9][0-9][0-9][A-Za-z][A-Za-z]')"""
    steps = [
        ("All invoice lines", "1=1"),
        ("Remove cancellation invoices", "invoice NOT LIKE 'C%'"),
        ("Remove returns / negative quantities", "quantity > 0"),
        ("Remove zero-price lines", "unit_price > 0"),
        ("Keep real product codes only", product_code),
    ]
    rows, where = [], []
    for label, condition in steps:
        where.append(condition)
        n = con.execute(f"SELECT COUNT(*) FROM raw_lines WHERE {' AND '.join(where)}").fetchone()[0]
        rows.append((label, n))
    n = con.execute("SELECT COUNT(*) FROM clean_lines").fetchone()[0]
    rows.append(("Remove orders later cancelled in full", n))
    return pd.DataFrame(rows, columns=["step", "lines_remaining"])


def load_weekly(con: sqlite3.Connection) -> pd.DataFrame:
    """Weekly demand for every product, plus its most common description."""
    df = pd.read_sql(
        """SELECT w.sku, n.description, w.week_start, w.units, w.revenue, w.orders
           FROM weekly_demand AS w LEFT JOIN product_names AS n USING (sku)""",
        con,
        parse_dates=["week_start"],
    )
    return df.sort_values(["sku", "week_start"]).reset_index(drop=True)
