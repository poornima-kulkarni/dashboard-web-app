"""
Fulfilment Dashboard - Backend
--------------------------------
Lightweight Flask app that loads three Excel files into memory (pandas),
applies live filters coming from the frontend, computes every KPI / chart
/ table the dashboard needs, and returns ONE JSON payload per request.

Data sources (kept in /data, swap-in-place with your own files):
  - open_demands_dataset.xlsx   -> requisition / demand level data
  - hr_dataset_1000_rows.xlsx   -> candidate / hiring pipeline data
  - account_mapping_file.xlsx   -> old -> new client account name lookup
"""

import os
from datetime import datetime

import pandas as pd
from flask import Flask, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

app = Flask(__name__)

# --------------------------------------------------------------------------
# 1. LOAD + CLEAN DATA  (runs once at startup)
# --------------------------------------------------------------------------

TIER_MAP = {
    "Bangalore": "Tier 1",
    "Mumbai": "Tier 1",
    "Delhi": "Tier 1",
    "Hyderabad": "Tier 2",
    "Pune": "Tier 2",
    "Chennai": "Tier 2",
}

EXP_BANDS = [
    (0, 2, "0-2 yrs"),
    (3, 5, "3-5 yrs"),
    (6, 8, "6-8 yrs"),
    (9, 100, "9+ yrs"),
]


def _band_experience(years):
    for lo, hi, label in EXP_BANDS:
        if lo <= years <= hi:
            return label
    return "9+ yrs"


def load_data():
    od = pd.read_excel(os.path.join(DATA_DIR, "open_demands_dataset.xlsx"))
    hr = pd.read_excel(os.path.join(DATA_DIR, "hr_dataset_1000_rows.xlsx"))
    mapping = pd.read_excel(os.path.join(DATA_DIR, "account_mapping_file.xlsx"))

    acc_lookup = dict(zip(mapping["Old_Account_Value"], mapping["Updated_Account_Value"]))

    for df in (od, hr):
        df["Account"] = df["Account"].map(lambda x: acc_lookup.get(x, x))
        df["Tier"] = df["Location"].map(lambda x: TIER_MAP.get(x, "Other"))

    date_cols_od = ["Target_Closure_Date", "Request_Creation_Date"]
    for c in date_cols_od:
        od[c] = pd.to_datetime(od[c], errors="coerce")

    date_cols_hr = ["Created_Date", "Interview_Date", "Joining_Date"]
    for c in date_cols_hr:
        hr[c] = pd.to_datetime(hr[c], errors="coerce")

    hr["Exp_Band"] = hr["Experience_Years"].map(_band_experience)

    return od, hr


OD, HR = load_data()
LAST_REFRESHED = datetime.now().strftime("%d %b %Y %H:%M:%S")

FILTER_FIELDS = {
    "demand_type": ("Demand_Type", "OD"),
    "sbu": ("SBU", "BOTH"),
    "account": ("Account", "BOTH"),
    "location": ("Location", "BOTH"),
    "employment_type": ("Employment_Type", "BOTH"),
    "bu_head": ("Business_Unit_Head", "OD"),
}


# --------------------------------------------------------------------------
# 2. FILTER HELPERS
# --------------------------------------------------------------------------

def apply_filters(od, hr, args):
    od_f, hr_f = od.copy(), hr.copy()
    for key, (col, scope) in FILTER_FIELDS.items():
        vals = args.getlist(key)
        if not vals:
            continue
        if scope in ("OD", "BOTH") and col in od_f.columns:
            od_f = od_f[od_f[col].isin(vals)]
        if scope in ("HR", "BOTH") and col in hr_f.columns:
            hr_f = hr_f[hr_f[col].isin(vals)]
    return od_f, hr_f


def pct(n, d):
    return round((n / d) * 100, 1) if d else 0.0


def safe_div(n, d, default=0):
    return round(n / d, 1) if d else default


# --------------------------------------------------------------------------
# 3. METRIC BUILDERS
# --------------------------------------------------------------------------

def build_kpis(od_f, hr_f):
    onboarded = int((hr_f["Joining_Status"] == "Joined").sum())
    in_pipeline = int((hr_f["Offer_Status"] == "Pending").sum())
    offers_accepted = int((hr_f["Offer_Status"] == "Accepted").sum())
    open_jobs = int((od_f["Number_of_Openings"] - od_f["Positions_Closed"]).clip(lower=0).sum())
    client_int_pct = pct(int((od_f["Client_Interview_Rounds"] >= 3).sum()), len(od_f))
    offer_to_joinee = pct(onboarded, offers_accepted)

    span_weeks = max(1, _week_span(hr_f["Created_Date"]))
    avg_onboards_wk = safe_div(onboarded, span_weeks)
    avg_pipeline_wk = safe_div(in_pipeline, span_weeks)

    joined = hr_f[hr_f["Joining_Status"] == "Joined"].copy()
    joined["lead_days"] = (joined["Joining_Date"] - joined["Created_Date"]).dt.days
    lead_time = int(joined["lead_days"].median()) if len(joined) else 0
    mean_time = int(joined["lead_days"].mean()) if len(joined) else 0

    replacement_pct = pct(int((od_f["Replacement_or_New"] == "Replacement").sum()), len(od_f))

    projection_current = onboarded + in_pipeline
    weeks_left = 13 - (span_weeks % 13) if span_weeks else 13
    weeks_left = weeks_left if weeks_left > 0 else 1
    projection_avg = onboarded + int(avg_onboards_wk * weeks_left)

    return {
        "onboarded": onboarded,
        "avg_onboards_week": avg_onboards_wk,
        "pipeline": in_pipeline,
        "avg_pipeline_week": avg_pipeline_wk,
        "open_jobs": open_jobs,
        "client_interview_pct": client_int_pct,
        "offer_to_joinee_ratio": offer_to_joinee,
        "lead_time_to_hire": lead_time,
        "mean_time_to_hire": mean_time,
        "replacement_pct": replacement_pct,
        "projection_current": projection_current,
        "projection_avg": projection_avg,
        "weeks_left": weeks_left,
        "total_open_demand_records": int(len(od_f)),
    }


def _week_span(dates):
    d = dates.dropna()
    if d.empty:
        return 1
    return max(1, int((d.max() - d.min()).days / 7))


def build_week_on_week(hr_f):
    created = hr_f.dropna(subset=["Created_Date"]).copy()
    joined = hr_f[hr_f["Joining_Status"] == "Joined"].dropna(subset=["Joining_Date"]).copy()
    if created.empty:
        return {"labels": [], "onboards": [], "pipeline": []}

    created["wk"] = created["Created_Date"].dt.to_period("W").apply(lambda p: p.start_time)
    joined["wk"] = joined["Joining_Date"].dt.to_period("W").apply(lambda p: p.start_time)

    pipeline_series = created.groupby("wk").size()
    onboard_series = joined.groupby("wk").size()

    all_weeks = sorted(set(pipeline_series.index) | set(onboard_series.index))[-13:]
    labels = [f"Week {i+1}" for i in range(len(all_weeks))]
    onboards = [int(onboard_series.get(w, 0)) for w in all_weeks]
    pipeline = [int(pipeline_series.get(w, 0)) for w in all_weeks]
    return {"labels": labels, "onboards": onboards, "pipeline": pipeline}


def build_tier_view(od_f):
    counts = od_f["Tier"].value_counts()
    total = counts.sum()
    order = ["Tier 1", "Tier 2", "Other"]
    labels = [t for t in order if t in counts.index]
    return {
        "labels": labels,
        "counts": [int(counts[t]) for t in labels],
        "pct": [pct(int(counts[t]), total) for t in labels],
    }


def build_client_interview(od_f):
    counts = od_f["Client_Interview_Rounds"].value_counts().sort_index()
    labels = [f"{int(r)} Round{'s' if r != 1 else ''}" for r in counts.index]
    return {"labels": labels, "counts": [int(c) for c in counts.values]}


def build_employment_split(od_f):
    counts = od_f["Employment_Type"].value_counts()
    total = counts.sum()
    labels = list(counts.index)
    return {
        "labels": labels,
        "counts": [int(c) for c in counts.values],
        "pct": [pct(int(c), total) for c in counts.values],
    }


def build_practice_table(od_f):
    counts = od_f["SBU"].value_counts()
    total = counts.sum()
    rows = [
        {"name": name, "count": int(c), "pct": pct(int(c), total)}
        for name, c in counts.items()
    ]
    rows.sort(key=lambda r: -r["count"])
    return rows


def build_employer_table(od_f):
    counts = od_f["Account"].value_counts()
    total = counts.sum()
    rows = [
        {"name": name, "count": int(c), "pct": pct(int(c), total)}
        for name, c in counts.items()
    ]
    rows.sort(key=lambda r: -r["count"])
    return rows


def build_margin(od_f):
    grp = od_f.groupby("Employment_Type")["Margin_Percentage"].mean().round(1)
    return {"labels": list(grp.index), "values": [float(v) for v in grp.values]}


def build_monthly_view(hr_f):
    joined = hr_f[hr_f["Joining_Status"] == "Joined"].dropna(subset=["Joining_Date"]).copy()
    if joined.empty:
        return {"labels": [], "counts": []}
    joined["month"] = joined["Joining_Date"].dt.to_period("M")
    grp = joined.groupby("month").size().sort_index().tail(6)
    labels = [p.strftime("%b'%y") for p in grp.index]
    return {"labels": labels, "counts": [int(v) for v in grp.values]}


def build_candidate_status(hr_f):
    counts = hr_f["Joining_Status"].value_counts()
    relabel = {"Joined": "Hired", "Yet to Join": "Pipeline", "Not Joined": "Lost"}
    labels = [relabel.get(k, k) for k in counts.index]
    return {"labels": labels, "counts": [int(c) for c in counts.values]}


def build_source_mix(od_f):
    counts = od_f["Sourcing_Channel"].value_counts()
    return {"labels": list(counts.index), "counts": [int(c) for c in counts.values]}


def build_experience_band(hr_f):
    order = ["0-2 yrs", "3-5 yrs", "6-8 yrs", "9+ yrs"]
    counts = hr_f["Exp_Band"].value_counts()
    total = counts.sum()
    rows = []
    for label in order:
        c = int(counts.get(label, 0))
        rows.append({"band": label, "count": c, "pct": pct(c, total)})
    return rows


def build_cpc_view(hr_f):
    def avg_cpc(emp_type, mode):
        sub = hr_f[(hr_f["Employment_Type"] == emp_type) & (hr_f["Work_Mode"] == mode)]
        return round(sub["Offer_CPC_Value_LPA"].mean(), 2) if len(sub) else 0

    return {
        "permanent": {
            "offshore": avg_cpc("Full-Time", "Remote"),
            "onsite": avg_cpc("Full-Time", "Onsite"),
        },
        "contractor": {
            "offshore": avg_cpc("Contract", "Remote"),
            "onsite": avg_cpc("Contract", "Onsite"),
        },
    }


def build_offer_acceptance(hr_f):
    total = len(hr_f)
    accepted = int((hr_f["Offer_Status"] == "Accepted").sum())
    return {"accepted_pct": pct(accepted, total), "accepted": accepted, "total": total}


# --------------------------------------------------------------------------
# 4. ROUTES
# --------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/filters")
def api_filters():
    return jsonify({
        "demand_type": sorted(OD["Demand_Type"].dropna().unique().tolist()),
        "sbu": sorted(OD["SBU"].dropna().unique().tolist()),
        "account": sorted(OD["Account"].dropna().unique().tolist()),
        "location": sorted(OD["Location"].dropna().unique().tolist()),
        "employment_type": sorted(OD["Employment_Type"].dropna().unique().tolist()),
        "bu_head": sorted(OD["Business_Unit_Head"].dropna().unique().tolist()),
    })


@app.route("/api/dashboard")
def api_dashboard():
    od_f, hr_f = apply_filters(OD, HR, request.args)

    payload = {
        "last_refreshed": LAST_REFRESHED,
        "kpis": build_kpis(od_f, hr_f),
        "week_on_week": build_week_on_week(hr_f),
        "tier_view": build_tier_view(od_f),
        "client_interview": build_client_interview(od_f),
        "employment_split": build_employment_split(od_f),
        "practice_table": build_practice_table(od_f),
        "employer_table": build_employer_table(od_f),
        "margin": build_margin(od_f),
        "monthly_view": build_monthly_view(hr_f),
        "candidate_status": build_candidate_status(hr_f),
        "source_mix": build_source_mix(od_f),
        "experience_band": build_experience_band(hr_f),
        "cpc_view": build_cpc_view(hr_f),
        "offer_acceptance": build_offer_acceptance(hr_f),
        "row_counts": {"open_demands": int(len(od_f)), "hr_records": int(len(hr_f))},
    }
    return jsonify(payload)


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
