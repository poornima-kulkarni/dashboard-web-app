# Fulfilment Dashboard

A lightweight, full-stack BI dashboard (styled after the reference Power BI
report) built with **Flask + pandas** on the backend and **vanilla HTML/CSS/JS
+ Chart.js** on the frontend. No build step, no database — it reads straight
from your Excel files.

## Project structure (6 files + data)

```
dashboard/
├── app.py                     # Flask backend: loads Excel, computes all KPIs/charts, serves API
├── requirements.txt           # Python dependencies
├── templates/
│   └── index.html             # Page structure
├── static/
│   ├── css/style.css          # All styling (teal header, hex KPIs, cards, responsive)
│   └── js/script.js           # Fetches API, renders Chart.js charts/tables, handles filters
│   └── js/chart.umd.js        # Chart.js, vendored locally (no CDN/internet needed)
└── data/
    ├── open_demands_dataset.xlsx
    ├── hr_dataset_1000_rows.xlsx
    └── account_mapping_file.xlsx
```

## Run it

```bash
cd dashboard
pip install -r requirements.txt
python3 app.py
```

Open **http://localhost:5000** in your browser.

## Swap in your own data

Replace the three files inside `data/` and **keep the same filenames and
column names** (or edit the column names referenced in `app.py`). On the next
restart the dashboard re-reads the files automatically — no other code
changes needed for new rows.

If you'd rather pull from **Google Sheets** instead of Excel: publish the
sheet, then in `app.py`'s `load_data()` swap the `pd.read_excel(...)` calls for
`pd.read_csv("https://docs.google.com/spreadsheets/d/<ID>/export?format=csv&gid=<GID>")`.
Everything downstream (filtering, KPIs, charts) stays the same since it all
works off the same pandas DataFrame.

## How filtering works

The sidebar checkboxes (Req. Classification, Region, Practice/SBU, Business
Unit Head, Account, Employment Type) are populated from `/api/filters`.
Every time you check/uncheck a box, the frontend re-calls
`/api/dashboard?sbu=...&account=...` and the backend re-filters the pandas
DataFrames and recomputes every metric, returning one JSON payload that
re-renders the whole page. "Clear all filters" resets everything.

## Notes on the metrics

A few widgets needed light reinterpretation since the source datasets don't
contain every exact field shown in the reference image (e.g. there's no
"Gender" or assessment-percentile column in the sample data):

- **Gender Diversity gauge** → replaced with **Offer Acceptance Rate** (real field: `Offer_Status`)
- **Hiring Band Percentile** → replaced with **Experience Band** (real field: `Experience_Years`)
- **Tier View** → derived from `Location` using a standard city-tier mapping
- **Type of Hire** → shown as **Employment Type** (`Full-Time` / `Contract` / `Internship`)
- **Client Interview** → shown as a distribution of interview-round counts (the data has 1–5 rounds per demand, not a yes/no flag)

Everything else (Onboarded, Pipeline, Open Jobs, Lead/Mean time to hire,
Replacement %, Practice, Account, Margin %, CPC, Source Mix, Monthly View,
Week-on-Week) is computed directly from real columns in your three files.
