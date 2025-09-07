
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

# ===== UI defaults (editable on the right) =====
st.session_state.setdefault("lt", 7)  # lead time (days)
st.session_state.setdefault("rc", 7)  # replen cycle (days)
st.session_state.setdefault("ss", 21) # safety stock (days)

# ===== Month helpers for projections =====
MONTHS_ORDER = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
MONTH_RE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4}\s+Qty$", re.IGNORECASE)

def month_key(col: str):
    parts = col.split()
    mon = parts[0].title()
    if mon == "Sept": mon = "Sep"
    year = int(parts[1])
    return (year, MONTHS_ORDER.index(mon))

# ===== General readers =====
def read_any(file, header=None):
    """Read csv/xlsx; header=None means no header; header=int uses that row as header."""
    name = getattr(file, "name", str(file)).lower()
    try:
        if name.endswith((".xlsx",".xls")):
            return pd.read_excel(file, header=header)
        return pd.read_csv(file, header=header)
    except Exception:
        if hasattr(file, "seek"):
            try: file.seek(0)
            except: pass
        if name.endswith((".xlsx",".xls")):
            return pd.read_excel(file, header=header)
        return pd.read_csv(file, header=header, encoding="latin-1")

def detect_header_and_load(file):
    """For projections: auto-find the header row that contains both a join key and month columns."""
    df_raw = read_any(file, header=None)
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
    df = read_any(file, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    return df

def load_tabular(file):
    """Read a simple CSV/XLSX that has its header in the first row (Inventory, Open Orders, Item Master)."""
    if hasattr(file, "seek"):
        try: file.seek(0)
        except: pass
    df = read_any(file, header=0)
    df.columns = [str(c).strip() for c in df.columns]
    return df

def first_col(df, options):
    for c in options:
        if c in df.columns: return c
    return None

# ===== Key normalizer (fixes spaces/case/weird dashes) =====
DASHES = r"\u2010\u2011\u2012\u2013\u2014\u2212"  # hyphen variants
DASH_RE = re.compile(f"[{DASHES}]")
def _norm_key(x):
    if pd.isna(x): return None
    s = str(x)
    s = DASH_RE.sub("-", s)      # normalize fancy dashes to ASCII hyphen
    s = s.strip().upper()
    return re.sub(r"[^A-Z0-9\-_/]", "", s)  # keep A-Z,0-9,-,_,/

# ===== Slimmers =====
def slim_inventory(inv_df, aggregate=True):
    """Use only SKU + OnHand; keep optional ProductName / WarehouseName; sum duplicates by SKU."""
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
    """Accept common item & quantity names; standardize to ItemNumber + OrderQTY (floats)."""
    item_col = first_col(oo_df, [
        "ItemNumber","Item Number",
        "SKU","sku","Sku",              # <- includes 'Sku' (your header)
        "DelSolSku","Del Sol Sku"
    ])
    if item_col is None:
        raise ValueError("Open Orders require ItemNumber (or SKU/DelSolSku).")
    qty_col = None
    for c in ["OrderQTY","Qty Ordered","Qty ordered","QTY ORDERED","QtyOrdered","Quantity Ordered"]:
        if c in oo_df.columns:
            qty_col = c; break
    if qty_col is None:
        raise ValueError("Open Orders require a quantity column (e.g., 'Qty Ordered' or 'OrderQTY').")
    slim = oo_df[[item_col, qty_col]].copy().rename(columns={item_col:"ItemNumber", qty_col:"OrderQTY"})
    slim["OrderQTY"] = pd.to_numeric(slim["OrderQTY"], errors="coerce").fillna(0.0)
    return slim

def slim_item_master(im_df):
    """Map Inventory SKU <-> DelSolSku; keep optional vendor fields for export."""
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
    im = im.drop_duplicates(subset=["SKU"], keep="first")
    return im

def slim_projections(proj_df):
    """Pick one month column; standardize to ItemNumberJoin + VelocityMonthly (floats)."""
    join_col = first_col(proj_df, ["Item Number","Del Sol Sku","DelSolSku","ItemNumber","itemnumber"])
    if not join_col:
        raise ValueError("Projections need a join column: Item Number / DelSolSku")
    month_cols = [c for c in proj_df.columns if isinstance(c, str) and MONTH_RE.match(c.strip())]
    if not month_cols:
        raise ValueError("Projections sheet is missing month columns like 'Sep 2025 Qty'.")
    month_cols_sorted = sorted(month_cols, key=month_key)
    selected = st.selectbox("Select projections month", month_cols_sorted, index=len(month_cols_sorted)-1)
    slim = proj_df[[join_col, selected]].copy()
    slim = slim.rename(columns={join_col:"ItemNumberJoin", selected:"VelocityMonthly"})
    slim["VelocityMonthly"] = pd.to_numeric(slim["VelocityMonthly"], errors="coerce").fillna(0.0)
    slim = slim.drop_duplicates(subset=["ItemNumberJoin"], keep="first")
    return slim, selected

# ===== UI Layout =====
left, right = st.columns([0.65, 0.35])
b1, b2 = st.columns([0.5, 0.5])

with left:
    st.subheader("① Upload your data")
    st.caption("Start with Inventory + Open Orders. Item Master & Projections are optional (defaults can be used).")
    inv_u = st.file_uploader("Inventory (ShipStation export; no scrubbing)", type=["csv","xlsx","xls"])
    oo_u  = st.file_uploader("Open Orders (PO report)", type=["csv","xlsx","xls"])
    im_u  = st.file_uploader("Item Master (optional; default bundled)", type=["csv","xlsx","xls"])
    proj_u= st.file_uploader("Projections (optional; default bundled)", type=["csv","xlsx","xls"])

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

    # Inventory (required)
    if inv_u is not None:
        inv_raw = load_tabular(inv_u)
        try:
            inv = slim_inventory(inv_raw, aggregate=aggregate)
            st.success("Inventory loaded.")
            st.dataframe(inv.head(10), use_container_width=True)
        except Exception as e:
            issues.append(str(e))
    else:
        issues.append("Upload Inventory.")

    # Open Orders (optional but recommended)
    if oo_u is not None:
        try:
            oo_raw = load_tabular(oo_u)
            oo = slim_open_orders(oo_raw)
            st.info("Open Orders included.")
            with st.expander("Debug: Open Orders mapping", expanded=False):
                item_guess = first_col(oo_raw, ["ItemNumber","Item Number","SKU","sku","Sku","DelSolSku","Del Sol Sku"])
                qty_guess  = first_col(oo_raw, ["OrderQTY","Qty Ordered","Qty ordered","QTY ORDERED","QtyOrdered","Quantity Ordered"])
                st.write(
                    {
                        "detected_item_column": item_guess,
                        "detected_qty_column": qty_guess,
                        "uploaded_rows": int(len(oo_raw)),
                        "uploaded_qty_total": float(oo["OrderQTY"].sum()),
                        "unique_items_in_upload": int(oo["ItemNumber"].nunique()),
                    }
                )
                st.dataframe(oo.head(20))
        except Exception as e:
            issues.append("Open Orders: " + str(e))

    # Item Master (optional; default if present)
    if im_u is not None:
        im_raw = load_tabular(im_u)
    elif DEFAULT_IM.exists():
        im_raw = load_tabular(DEFAULT_IM.open("rb"))
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
        st.info("No Item Master uploaded; projections join may be limited.")

    # Projections (optional; default if present)
    if proj_u is not None:
        proj_raw = detect_header_and_load(proj_u)
    elif DEFAULT_PROJ.exists():
        proj_raw = detect_header_and_load(DEFAULT_PROJ.open("rb"))
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
        st.info("No Projections uploaded; VelocityMonthly will be 0 unless defaults exist.")

    if issues:
        st.error(" • " + "\n • ".join(issues))

with b2:
    st.subheader("④ Recommended Orders")
    if inv is not None:
        merged = inv.copy()

        # Map DelSolSku via Item Master (for projections + alt open-order join)
        if im is not None:
            merged = merged.merge(im, on="SKU", how="left")  # adds DelSolSku + optional vendor fields
        else:
            merged["DelSolSku"] = merged.get("DelSolSku", pd.NA)

        # Join projections using DelSolSku (if present)
        if 'DelSolSku' in merged.columns and proj is not None:
            merged = merged.merge(proj, left_on="DelSolSku", right_on="ItemNumberJoin", how="left")
        else:
            merged["VelocityMonthly"] = 0.0

        # Open Orders join (sum duplicates; match by SKU and/or DelSolSku with normalization)
        if oo is not None and len(oo) > 0:
            oo_agg = oo.groupby("ItemNumber", as_index=False)["OrderQTY"].sum()
            merged["_JOIN_SKU"]    = merged["SKU"].map(_norm_key) if "SKU" in merged.columns else None
            merged["_JOIN_DELSOL"] = merged["DelSolSku"].map(_norm_key) if "DelSolSku" in merged.columns else None
            oo_agg["_JOIN_ITEM"]   = oo_agg["ItemNumber"].map(_norm_key)

            m_sku = merged.merge(
                oo_agg[["_JOIN_ITEM","OrderQTY"]].rename(columns={"OrderQTY":"OrderQTY_by_SKU"}),
                left_on="_JOIN_SKU", right_on="_JOIN_ITEM", how="left"
            )
            m_dls = merged.merge(
                oo_agg[["_JOIN_ITEM","OrderQTY"]].rename(columns={"OrderQTY":"OrderQTY_by_DelSol"}),
                left_on="_JOIN_DELSOL", right_on="_JOIN_ITEM", how="left"
            )
            merged["OrderQTY_by_SKU"]    = m_sku.get("OrderQTY_by_SKU")
            merged["OrderQTY_by_DelSol"] = m_dls.get("OrderQTY_by_DelSol")
            merged["OrderQTY"] = merged[["OrderQTY_by_SKU","OrderQTY_by_DelSol"]].fillna(0).max(axis=1)

            # diagnostics
            total_uploaded_oo = float(oo_agg["OrderQTY"].sum())
            matched_rows = int((merged["OrderQTY"] > 0).sum())
            matched_total = float(merged["OrderQTY"].sum())
            st.caption(f"Open Orders uploaded total: {total_uploaded_oo:,.0f}  •  Rows with matches: {matched_rows}  •  Matched total (across inv): {matched_total:,.0f}")

            with st.expander("Debug: Unmatched open-order keys", expanded=False):
                inv_keys = set(filter(None, (merged["_JOIN_SKU"].dropna().tolist() + merged["_JOIN_DELSOL"].dropna().tolist())))
                oo_keys  = set(filter(None, oo_agg["_JOIN_ITEM"].dropna().tolist()))
                missing  = sorted(list(oo_keys - inv_keys))[:50]
                st.write({"unmatched_count": len(oo_keys - inv_keys), "examples": missing})
                st.dataframe(oo_agg.head(20))

            merged.drop(columns=["_JOIN_SKU","_JOIN_DELSOL","_JOIN_ITEM","OrderQTY_by_SKU","OrderQTY_by_DelSol"], errors="ignore", inplace=True)
        else:
            merged["OrderQTY"] = 0.0

        # ===== Calculation =====
        # Spreadsheet equivalence:
        # target = (rc+ss+lt) * (VelocityMonthly/30)
        # recommended = target - (OnHand - Allocated + OpenQty) ; Allocated=0 here
        merged["VelocityMonthly"] = pd.to_numeric(merged.get("VelocityMonthly", 0), errors="coerce").fillna(0.0)
        daily_velocity = merged["VelocityMonthly"] / 30.0
        target_level = daily_velocity * (lt + rc + ss)
        position_now = merged["OnHand"].fillna(0.0) + 0.0 + merged["OrderQTY"].fillna(0.0) * (-1)  # equivalent to -(H - G + F) with G=0
        # Simpler and identical to spreadsheet with Allocated=0:
        position_now = merged["OnHand"].fillna(0.0) + merged["OrderQTY"].fillna(0.0) * 0  # keep 0 to not double-subtract
        # Final: target - OnHand - OpenQty
        merged["recommended"] = (target_level - merged["OnHand"].fillna(0.0) - merged["OrderQTY"].fillna(0.0)).apply(lambda x: max(0, math.ceil(x)))

        # ===== Output (omit lt/rc/ss columns per your note) =====
        out = merged[(merged["recommended"] > 0) | (merged["OrderQTY"] > 0)].copy()

        cols = ["SKU","DelSolSku"]
        for opt in ["Primary Vendor","Primary Vendor Sku","Status","ProductName","WarehouseName"]:
            if opt in out.columns: cols.append(opt)
        cols += ["OnHand","OrderQTY","VelocityMonthly","recommended"]
        cols = [c for c in cols if c in out.columns]
        out = out[cols].sort_values(by=["recommended","OrderQTY"] if "OrderQTY" in out.columns else ["recommended"], ascending=[False,False])

        st.dataframe(out, use_container_width=True)

        # downloads
        def to_csv_xlsx(df, base):
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv = df.to_csv(index=False).encode("utf-8")
            xbuf = io.BytesIO()
            with pd.ExcelWriter(xbuf, engine="openpyxl") as w:
                df.to_excel(w, index=False, sheet_name="RecommendedOrders")
            return (csv, f"{base}_{now}.csv"), (xbuf.getvalue(), f"{base}_{now}.xlsx")

        csv, xlsx = to_csv_xlsx(out, "Final_Recommended_Orders_Report")
        st.download_button("Download CSV", data=csv[0], file_name=csv[1], mime="text/csv")
        st.download_button("Download XLSX", data=xlsx[0], file_name=xlsx[1], mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("Upload Inventory to begin.")

st.caption("SilverScreen – DelSol Material Replenishment Calculator")
