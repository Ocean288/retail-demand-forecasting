"""Project settings. Every assumption the pipeline makes lives here."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "retail.db"
SQL_DIR = ROOT / "sql"
OUTPUT_DIR = ROOT / "outputs"
FIGURE_DIR = ROOT / "reports" / "figures"

# Two CSV exports of the UCI "Online Retail II" dataset (CC BY 4.0).
# Year 1 (Dec 2009 - Dec 2010) and year 2 (Dec 2010 - Dec 2011) come from
# different mirrors; they overlap on 1-9 Dec 2010, which we keep only once.
RAW_FILES = {
    "year1": {
        "url": "https://raw.githubusercontent.com/PacktWorkshops/The-Data-Analysis-Workshop/"
               "master/Chapter08/Datasets/online_retail_II.csv",
        "file": "online_retail_2009_2010.csv",
        "date_format": "%d/%m/%Y %H:%M",
        "encoding": "utf-8-sig",
    },
    "year2": {
        "url": "https://raw.githubusercontent.com/databricks/Spark-The-Definitive-Guide/"
               "master/data/retail-data/all/online-retail-dataset.csv",
        "file": "online_retail_2010_2011.csv",
        "date_format": "%m/%d/%Y %H:%M",
        "encoding": "latin-1",
    },
}
YEAR2_START = "2010-12-01"  # year-1 rows from this date on are duplicates of year 2

# The data ends on Friday 9 Dec 2011, so the week starting 5 Dec is incomplete.
LAST_FULL_WEEK = "2011-11-28"

# Which products we forecast: A and B class (top 95% of revenue) that sold in
# at least 80% of weeks during the last year. Rarely-sold items need different
# methods (see README, "Limitations").
ABC_A_SHARE = 0.80
ABC_B_SHARE = 0.95
MIN_ACTIVE_WEEK_SHARE = 0.80

# Backtest: forecast 1-4 weeks ahead from every week between these dates.
# Outlier caps are fitted only on weeks before the first cutoff.
HORIZON_WEEKS = 4
FIRST_CUTOFF = "2011-04-04"
LAST_CUTOFF = "2011-10-31"
OUTLIER_FIT_UNTIL = "2011-03-28"
# The stock simulation starts 8 weeks later, once each model has a track record
# of errors to size safety stock from.
SIMULATION_START = "2011-05-30"

# Inventory policy assumptions (the dataset has no supplier or stock data).
LEAD_TIME_WEEKS = 2
REVIEW_PERIOD_WEEKS = 1
SERVICE_LEVEL = {"A": 0.95, "B": 0.90}
