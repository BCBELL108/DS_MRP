
import math, re, io
import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="Reorder Calculator — Clean Mac", layout="wide")
DATA_DIR = Path("data")
DEFAULT_IM = DATA_DIR / "item_master_default.csv"
DEFAULT_PROJ = DATA_DIR / "projections_default.csv"

# Defaults
st.session_state.setdefault("lt", 7)
st.session_state.setdefault("rc", 7)
st.session_state.setdefault("ss", 21)

# Month patterns (3- or 4-letter "Sep"/"Sept")
MONTHS_ORDER = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
MONTH_RE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4}\s+Qty$", re.IGNORECASE)
def month_key(col):
    parts = col.split()
    mon = parts[0].title()
    if mon == "Sept": mon = "Sep"
    year = int(parts[1])
    return (year, MONTHS_ORDER.index(mon))

# ---------- helpers
def read_any(file):
    name = getattr(file, "name", str(file)).lower()
    try:
        if name.endswith((".xlsx",".xls")):
            return pd.read_excel(file, header=None)
        return pd.read_csv(file, header=None)
    except Exception:
        if hasattr(file, "seek"):
            try: file.seek(0)
            except: pass
        return pd.read_csv(file, header=None, encoding="latin-1")

def detect_header_and_load(file):
    df_raw = read_any(file)
    header_row = 0
    for i in range(min(30, len(df_raw))):
        row = [str(x).strip() for x in df_raw.iloc[i].values]
        has_join = any(v.lower() in ["item number","del sol sku","delsolsku","itemnumber","sku"] for v in row)
        has_month = any(isinstance(v, str) and MONTH_RE.match(v) for v in row)
        if has_join and has_month:
            header_row = i
            break
    if hasattr(file, "seek"):
        try: file.seek(0)
        except: pass
    name = getattr(file, "name", str(file)).lower()
    if name.endswith((".xlsx",".xls")):
        df = pd.read_excel(file, header=header_row)
    else:
        df = pd.read_csv(file, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    return df

def first_col(df, options):
    for c in options:
        if c in df.columns: return c
    return None

def slim_item_master(im_df):
    # Map keys and optional vendor fields
    sku_col = first_col(im_df, ["SKU","Silverscreen Sku","ItemNumber","itemnumber","sku"])
    dels_col = first_col(im_df, ["DelSolSku","Del Sol Sku","ItemNumber","itemnumber"])
    if not sku_col or not dels_col:
        raise ValueError("Item Master must include Inventory SKU and DelSolSku/Item Number columns.")
    vendor = first_col(im_df, ["Primary Vendor","Vendor","PrimaryVendor","primary vendor","primary_vendor"])
    vendor_sku = first_col(im_df, ["Primary Vendor Sku","Primary Vendor SKU","Vendor Sku","Vendor SKU","primary vendor sku","primary_vendor_sku"])
    status = first_col(im_df, ["Status","Item Status","status"])
    keep = [sku_col, dels_col] + [c for c in [vendor, vendor_sku, status] if c]
    im = im_df[keep].copy()
    rename_map = {sku_col:"SKU", dels_col:"DelSolSku"}
    if vendor: rename_map[vendor] = "Primary Vendor"
    if vendor_sku: rename_map[vendor_sku] = "Primary Vendor Sku"
    if status: rename_map[status] = "Status"
    im = im.rename(columns=rename_map)
    # drop dupes on SKU, keep first
    im = im.drop_duplicates(subset=["SKU"], keep="first")
    return im

def slim_projections(proj_df):
    # Find join key and month columns, no aggregation
    join_col = first_col(proj_df, ["Item Number","Del Sol Sku","DelSolSku","ItemNumber","itemnumber"])
    if not join_col:
        raise ValueError("Projections need a join column: Item Number / DelSolSku")
    month_cols = [c for c in proj_df.columns if isinstance(c, str) and MONTH_RE.match(c.strip())]
    if not month_cols:
        raise ValueError("Projections sheet is missing month columns like 'Sep 2025 Qty'.")
    # Sort by year, then month
    month_cols_sorted = sorted(month_cols, key=month_key)
    # UI to choose
    selected = st.selectbox("Select projections month", month_cols_sorted, index=len(month_cols_sorted)-1)
    slim = proj_df[[join_col, selected]].copy()
    slim = slim.rename(columns={join_col:"ItemNumberJoin", selected:"VelocityMonthly"})
    # numeric
    slim["VelocityMonthly"] = pd.to_numeric(slim["VelocityMonthly"], errors="coerce").fillna(0.0)
    # remove dupes on join, keep first (no sum)
    slim = slim.drop_duplicates(subset=["ItemNumberJoin"], keep="first")
    return slim, selected

def slim_inventory(inv_df, aggregate=True):
    need = [c for c in ["SKU","OnHand"] if c not in inv_df.columns]
    if need:
        raise ValueError("Inventory is missing required columns: " + ", ".join(need))
    keep = [c for c in ["SKU","ProductName","WarehouseName","OnHand"] if c in inv_df.columns]
    inv = inv_df[keep].copy()
    inv["OnHand"] = pd.to_numeric(inv["OnHand"], errors="coerce").fillna(0)
    if aggregate:
        agg = {"OnHand":"sum"}
        if "ProductName" in inv.columns: agg["ProductName"] = "first"
        if "WarehouseName" in inv.columns: agg["WarehouseName"] = "first"
        inv = inv.groupby("SKU", as_index=False).agg(agg)
    return inv

def slim_open_orders(oo_df):
    item_col = first_col(oo_df, ["ItemNumber","Item Number","SKU","sku"])
    if item_col is None or "OrderQTY" not in oo_df.columns:
        raise ValueError("Open Orders require ItemNumber (or SKU) and OrderQTY")
    slim = oo_df[[item_col,"OrderQTY"]].copy().rename(columns={item_col:"ItemNumber"})
    slim["OrderQTY"] = pd.to_numeric(slim["OrderQTY"], errors="coerce").fillna(0.0)
    return slim

def to_csv_xlsx(df, base):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv = df.to_csv(index=False).encode("utf-8")
    import io
    xbuf = io.BytesIO()
    with pd.ExcelWriter(xbuf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="RecommendedOrders")
    return (csv, f"{base}_{now}.csv"), (xbuf.getvalue(), f"{base}_{now}.xlsx")

# ---------- UI layout
left, right = st.columns([0.65, 0.35])
b1, b2 = st.columns([0.5, 0.5])

with left:
    st.subheader("① Upload your data")
    inv_u = st.file_uploader("Inventory (ShipStation export; no scrubbing)", type=["csv","xlsx","xls"])
    im_u  = st.file_uploader("Item Master (optional; default bundled)", type=["csv","xlsx","xls"])
    proj_u= st.file_uploader("Projections (optional; default bundled)", type=["csv","xlsx","xls"])
    oo_u  = st.file_uploader("Open Orders (optional)", type=["csv","xlsx","xls"])
    st.caption("If you don't upload Item Master/Projections, the bundled defaults in /data are used.")

with right:
    st.subheader("② Parameters")
    lt = st.number_input("Lead Time (days)", min_value=0, max_value=365, value=st.session_state.lt, step=1)
    rc = st.number_input("Replen Cycle (days)", min_value=0, max_value=365, value=st.session_state.rc, step=1)
    ss = st.number_input("Safety Stock (days)", min_value=0, max_value=365, value=st.session_state.ss, step=1)
    aggregate = st.checkbox("Aggregate OnHand by SKU (sum across rows/locations)", value=True)

with b1:
    st.subheader("③ Data checks & mapping")
    issues = []
    inv = im = proj = oo = None
    selected_month = None

    # Inventory
    if inv_u is not None:
        inv_raw = detect_header_and_load(inv_u)
    else:
        inv_raw = None
    if inv_raw is not None:
        try:
            inv = slim_inventory(inv_raw, aggregate=aggregate)
            st.success("Inventory loaded.")
            st.dataframe(inv.head(10), use_container_width=True)
        except Exception as e:
            issues.append(str(e))

    # Item Master (default if none uploaded)
    if im_u is not None:
        im_raw = detect_header_and_load(im_u)
    elif DEFAULT_IM.exists():
        im_raw = detect_header_and_load(DEFAULT_IM)
    else:
        im_raw = None
    if im_raw is not None:
        try:
            im = slim_item_master(im_raw)
            st.success("Item Master ready.")
            st.dataframe(im.head(10), use_container_width=True)
        except Exception as e:
            issues.append("Item Master: " + str(e))
    else:
        issues.append("No Item Master found (upload one or place it in data/item_master_default.csv).")

    # Projections (default if none uploaded)
    if proj_u is not None:
        proj_raw = detect_header_and_load(proj_u)
    elif DEFAULT_PROJ.exists():
        proj_raw = detect_header_and_load(DEFAULT_PROJ)
    else:
        proj_raw = None
    if proj_raw is not None:
        try:
            proj, selected_month = slim_projections(proj_raw)
            st.success(f"Projections ready (month: {selected_month}).")
            st.dataframe(proj.head(10), use_container_width=True)
        except Exception as e:
            issues.append("Projections: " + str(e))
    else:
        issues.append("No Projections found (upload one or place it in data/projections_default.csv).")

    # Open Orders optional
    if oo_u is not None:
        try:
            oo_raw = detect_header_and_load(oo_u)
            oo = slim_open_orders(oo_raw)
            st.info("Open Orders included.")
            st.dataframe(oo.head(10), use_container_width=True)
        except Exception as e:
            issues.append("Open Orders: " + str(e))

    if issues:
        st.error(" • " + "\\n • ".join(issues))

with b2:
    st.subheader("④ Recommended Orders")
    if inv is not None and im is not None and proj is not None:
        # SKU -> Item Master (DelSolSku + vendor fields)
        merged = inv.merge(im, on="SKU", how="left")
        if "DelSolSku" not in merged.columns:
            st.error("Item Master did not provide DelSolSku/Item Number mapping.")
        else:
            # Join projections using ItemNumber
            merged = merged.merge(proj, left_on="DelSolSku", right_on="ItemNumberJoin", how="left")
            # Open Orders join (optional)
            if oo is not None:
                oo_agg = oo.groupby("ItemNumber", as_index=False)["OrderQTY"].sum()
                merged = merged.merge(oo_agg, left_on="SKU", right_on="ItemNumber", how="left")
                merged["OrderQTY"] = merged["OrderQTY"].fillna(0.0)
                merged = merged.drop(columns=["ItemNumber"], errors="ignore")
            else:
                merged["OrderQTY"] = 0.0

            # Compute
            merged["VelocityMonthly"] = pd.to_numeric(merged["VelocityMonthly"], errors="coerce").fillna(0.0)
            merged["daily_velocity"] = merged["VelocityMonthly"] / 30.0

            merged["target_level"] = merged["daily_velocity"] * (lt + rc + ss)
            merged["position_now"] = merged["OnHand"].fillna(0.0) + merged["OrderQTY"].fillna(0.0)
            merged["recommended"] = (merged["target_level"] - merged["position_now"]).apply(lambda x: max(0, math.ceil(x)))

            # Output filter
            out = merged[(merged["recommended"] > 0) | (merged["OrderQTY"] > 0)].copy()
            out["lead_time_days"] = lt
            out["replen_cycle_days"] = rc
            out["safety_stock_days"] = ss

            # Order output columns; include vendor fields if present
            cols = ["SKU","DelSolSku"]
            for opt in ["Primary Vendor","Primary Vendor Sku","Status","ProductName","WarehouseName"]:
                if opt in out.columns: cols.append(opt)
            cols += ["OnHand","OrderQTY","daily_velocity","lead_time_days","replen_cycle_days","safety_stock_days","target_level","position_now","recommended"]
            cols = [c for c in cols if c in out.columns]
            out = out[cols].sort_values(by=["recommended","OrderQTY"] if "OrderQTY" in out.columns else ["recommended"], ascending=[False,False])

            st.dataframe(out, use_container_width=True)

            csv, xlsx = to_csv_xlsx(out, "Final_Recommended_Orders_Report")
            st.download_button("Download CSV", data=csv[0], file_name=csv[1], mime="text/csv")
            st.download_button("Download XLSX", data=xlsx[0], file_name=xlsx[1], mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Upload Inventory. Item Master and Projections defaults are used automatically unless you upload new ones.")

st.caption("Clean Mac build: no-scrub inventory • Item Master as library • Projections as monthly velocity • Vendor fields included.")
