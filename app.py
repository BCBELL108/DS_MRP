import math, re, io
import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path
from datetime import datetime

# ------------------ App meta ------------------
st.set_page_config(page_title="DelSol MRP Tool", layout="wide")
APP_VERSION = "v5"  # tiny sidebar version tag
st.sidebar.markdown(f"**App version:** {APP_VERSION}")

# ------------------ Paths / defaults ------------------
DATA_DIR = Path("data")
DEFAULT_IM   = DATA_DIR / "item_master_default.csv"
DEFAULT_PROJ = DATA_DIR / "projections_default.csv"
LOGO_PATH    = DATA_DIR / "silverscreen_logo.png"   # <- add your logo here

# ------------------ Header / Branding ------------------
col_l, col_c, col_r = st.columns([1, 4, 1])
with col_c:
    if LOGO_PATH.exists():
        st.image(str(LOGO_PATH), use_container_width=True)
    else:
        st.markdown(
            "<h2 style='text-align:center;margin:0 0 0.25rem;'>SilverScreen – Decoration & Fulfillment</h2>",
            unsafe_allow_html=True,
        )
    st.markdown(
        "<div style='text-align:center;color:#9aa0a6;margin:-0.25rem 0 0.75rem;'>Built and Deployed by Brandon Bell</div>",
        unsafe_allow_html=True,
    )

# Parameters (same defaults)
st.session_state.setdefault("lt", 7)
st.session_state.setdefault("rc", 7)
st.session_state.setdefault("ss", 21)
st.session_state.setdefault("proj_month", None)  # chosen forecast month

# ------------------ Month helpers ------------------
MONTHS_ORDER = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
MONTH_RE = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4}\s+Qty$", re.IGNORECASE)

def month_key(col: str):
    parts = col.split()
    mon = parts[0].title()
    if mon == "Sept": mon = "Sep"
    year = int(parts[1])
    return (year, MONTHS_ORDER.index(mon))

def auto_select_projection_month(month_cols):
    keys = sorted([(month_key(c), c) for c in month_cols], key=lambda x: x[0])
    today = datetime.now()
    today_key = (today.year, today.month - 1)
    prior = [kc for kc in keys if kc[0] <= today_key]
    return prior[-1][1] if prior else keys[0][1]

def months_from_proj(df):
    return [c for c in df.columns if isinstance(c, str) and MONTH_RE.match(c.strip())]

# ------------------ Readers ------------------
def read_any(file, header=None):
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
    df_raw = read_any(file, header=None)
    header_row = 0
    for i in range(min(30, len(df_raw))):
        row = [str(x).strip() for x in df_raw.iloc[i].values]
        has_join  = any(v.lower() in ["item number","del sol sku","delsolsku","itemnumber","sku"] for v in row)
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
    if hasattr(file, "seek"):
        try: file.seek(0)
        except: pass
    df = read_any(file, header=0)
    df.columns = [str(c).strip() for c in df.columns]
    return df

# ------------------ Key normalization ------------------
DASHES = r"\u2010\u2011\u2012\u2013\u2014\u2212"
DASH_RE = re.compile(f"[{DASHES}]")
def _norm_key(x):
    if pd.isna(x): return None
    s = str(x)
    s = DASH_RE.sub("-", s)
    s = s.strip().upper()
    return re.sub(r"[^A-Z0-9\-_/]", "", s)

def first_col(df, options):
    normalize = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())
    norm_map = {normalize(c): c for c in df.columns}
    for opt in options:
        key = normalize(opt)
        if key in norm_map: return norm_map[key]
    for opt in options:
        if opt in df.columns: return opt
    return None

# ------------------ Slimmers ------------------
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
    item_col = first_col(oo_df, ["SKU","ItemNumber","Item Number","DelSolSku","Del Sol Sku"])
    if item_col is None:
        raise ValueError("Open Orders require a SKU/ItemNumber column.")
    qty_col = first_col(oo_df, ["Qty Ordered","OrderQTY","QtyOrdered","Quantity Ordered","Qty"])
    if qty_col is None:
        raise ValueError("Open Orders require a quantity column.")
    slim = oo_df[[item_col, qty_col]].copy()
    slim.columns = ["ItemNumber", "OrderQTY"]
    slim["OrderQTY"] = pd.to_numeric(slim["OrderQTY"], errors="coerce").fillna(0.0)
    return slim

def slim_item_master(im_df):
    # Required keys
    sku_col  = first_col(im_df, ["SKU","Silverscreen Sku","ItemNumber","itemnumber","sku"])
    dels_col = first_col(im_df, ["DelSolSku","Del Sol Sku","ItemNumber","itemnumber"])
    if not sku_col or not dels_col:
        raise ValueError("Item Master must include Inventory SKU and DelSolSku/Item Number.")
    # Optional fields (description/name + vendor fields)
    prod_col = first_col(im_df, [
        "ProductName","Product Name","Item Description","Description","Item Name","Name"
    ])
    vendor     = first_col(im_df, ["Primary Vendor","Vendor","PrimaryVendor","primary vendor","primary_vendor"])
    vendor_sku = first_col(im_df, ["Primary Vendor Sku","Primary Vendor SKU","Vendor Sku","Vendor SKU","primary vendor sku","primary_vendor_sku"])
    status     = first_col(im_df, ["Status","Item Status","status"])

    keep = [sku_col, dels_col] + [c for c in [prod_col, vendor, vendor_sku, status] if c]
    im = im_df[keep].copy()

    rename_map = {sku_col:"SKU", dels_col:"DelSolSku"}
    if prod_col:   rename_map[prod_col]   = "ProductName"
    if vendor:     rename_map[vendor]     = "Primary Vendor"
    if vendor_sku: rename_map[vendor_sku] = "Primary Vendor Sku"
    if status:     rename_map[status]     = "Status"

    im = im.rename(columns=rename_map)
    im = im.drop_duplicates(subset=["SKU"], keep="first")
    return im

def build_velocity(proj_df, selected_month):
    join_col = first_col(proj_df, ["Item Number","Del Sol Sku","DelSolSku","ItemNumber","itemnumber"])
    if not join_col:
        raise ValueError("Projections need a join column: Item Number / DelSolSku")
    if selected_month not in proj_df.columns:
        raise ValueError("Selected projection month not found in uploaded file.")
    slim = proj_df[[join_col, selected_month]].copy()
    slim = slim.rename(columns={join_col:"ItemNumberJoin", selected_month:"VelocityMonthly"})
    slim["ItemNumberJoin"] = slim["ItemNumberJoin"].astype(str).str.strip()
    slim.loc[slim["ItemNumberJoin"].str.lower().isin(["nan", "none", ""]), "ItemNumberJoin"] = np.nan
    slim["VelocityMonthly"] = pd.to_numeric(slim["VelocityMonthly"], errors="coerce").fillna(0.0)
    drop_words = {"total", "grand total", "subtotal"}
    slim = slim[slim["ItemNumberJoin"].notna()]
    slim = slim[~slim["ItemNumberJoin"].str.lower().isin(drop_words)]
    slim = slim[slim["ItemNumberJoin"].str.fullmatch(r"[A-Za-z0-9\-_\/]+")]
    slim = (slim
            .groupby("ItemNumberJoin", as_index=False, sort=False)
            .agg(VelocityMonthly=("VelocityMonthly", "sum")))
    return slim

def slim_allocations(alloc_df):
    item_col = first_col(alloc_df, ["SKU","sku","Sku","ItemNumber","Item Number"])
    if item_col is None:
        raise ValueError("Allocated items sheet must include a 'SKU' column.")
    qty_col = first_col(alloc_df, ["Qty","QTY","Quantity","AllocatedQty","Allocated Qty"])
    if qty_col is None:
        raise ValueError("Allocated items sheet must include a qty column.")
    df = alloc_df[[item_col, qty_col]].copy()
    df.columns = ["SKU","AllocatedQty"]
    df["AllocatedQty"] = pd.to_numeric(df["AllocatedQty"], errors="coerce").fillna(0).clip(lower=0)
    df["_JOIN_SKU"] = df["SKU"].map(_norm_key)
    df = df.groupby("_JOIN_SKU", as_index=False).agg(
        AllocatedQty=("AllocatedQty","sum"),
        SKU=("SKU","first")
    )
    return df

# ------------------ Build master rows (FIXED & ENRICHED) ------------------
def build_master_sku(inv, alloc, oo, im):
    """
    Build base SKU list from Inventory, add SKUs appearing only in Allocations/Open Orders (raw strings),
    then enrich all rows with Item Master fields by joining on a union key (SKU OR DelSolSku).
    """
    base_cols = ["SKU","ProductName","WarehouseName","OnHand"]
    if inv is not None:
        base = inv.copy()
        for c in base_cols:
            if c not in base.columns:
                base[c] = pd.NA if c != "OnHand" else 0.0
    else:
        base = pd.DataFrame(columns=base_cols)

    base["_JOIN_SKU"] = base["SKU"].map(_norm_key)

    # Ensure Allocation SKUs exist
    if alloc is not None and len(alloc) > 0:
        have = set(base["_JOIN_SKU"].dropna().tolist())
        missing_keys = sorted(list(set(alloc["_JOIN_SKU"].dropna().tolist()) - have))
        if missing_keys:
            raw_lookup = dict(zip(alloc["_JOIN_SKU"], alloc["SKU"]))  # normalized -> raw SKU
            add = [{"SKU": raw_lookup[k], "OnHand": 0.0} for k in missing_keys if k in raw_lookup]
            if add:
                add_df = pd.DataFrame(add)
                for col in ["ProductName","WarehouseName"]:
                    if col not in add_df.columns: add_df[col] = pd.NA
                base = pd.concat([base, add_df], ignore_index=True)
                base["_JOIN_SKU"] = base["SKU"].map(_norm_key)

    # Ensure Open-Order SKUs exist
    if oo is not None and len(oo) > 0:
        oo_tmp = oo.copy()
        oo_tmp["_JOIN_ITEM"] = oo_tmp["ItemNumber"].map(_norm_key)
        oo_raw_lookup = (
            oo_tmp.dropna(subset=["_JOIN_ITEM"])
                 .drop_duplicates("_JOIN_ITEM")
                 .set_index("_JOIN_ITEM")["ItemNumber"]
                 .to_dict()
        )
        have = set(base["_JOIN_SKU"].dropna().tolist())
        missing_keys = sorted(list(set(oo_tmp["_JOIN_ITEM"].dropna().tolist()) - have))
        if missing_keys:
            add = [{"SKU": oo_raw_lookup[k], "OnHand": 0.0} for k in missing_keys if k in oo_raw_lookup]
            if add:
                extra_df = pd.DataFrame(add)
                for col in ["ProductName","WarehouseName"]:
                    if col not in extra_df.columns: extra_df[col] = pd.NA
                base = pd.concat([base, extra_df], ignore_index=True)
                base["_JOIN_SKU"] = base["SKU"].map(_norm_key)

    # Deduplicate on normalized key (keep first occurrence)
    base = base.drop_duplicates(subset=["_JOIN_SKU"], keep="first")

    # Enrich with Item Master at the END using a UNION key (SKU OR DelSolSku)
    if im is not None and "SKU" in im.columns:
        im2 = im.copy()
        im2["_JOIN_SKU"]    = im2["SKU"].map(_norm_key)
        im2["_JOIN_DELSOL"] = im2["DelSolSku"].map(_norm_key) if "DelSolSku" in im2.columns else np.nan

        # Union table where either SKU or DelSolSku can match the base SKU
        im_union_a = im2.rename(columns={"_JOIN_SKU":"_JOIN"})[
            ["_JOIN","DelSolSku","ProductName","Primary Vendor","Primary Vendor Sku","Status"]
        ]
        im_union_b = im2.rename(columns={"_JOIN_DELSOL":"_JOIN"})[
            ["_JOIN","DelSolSku","ProductName","Primary Vendor","Primary Vendor Sku","Status"]
        ]
        im_union = pd.concat([im_union_a, im_union_b], ignore_index=True)
        im_union = im_union.dropna(subset=["_JOIN"]).drop_duplicates("_JOIN")

        base = base.merge(im_union, left_on="_JOIN_SKU", right_on="_JOIN", how="left", suffixes=("", "_im"))
        base.drop(columns=["_JOIN"], inplace=True, errors="ignore")

        # Fill blanks in base from right-side (*_im) columns, then drop *_im
        for c in ["DelSolSku","ProductName","Primary Vendor","Primary Vendor Sku","Status"]:
            if c + "_im" in base.columns:
                if c not in base.columns:
                    base[c] = pd.NA
                base[c] = base[c].combine_first(base[c + "_im"])
                base.drop(columns=[c + "_im"], inplace=True, errors="ignore")
    else:
        for c in ["DelSolSku","Primary Vendor","Primary Vendor Sku","Status"]:
            if c not in base.columns: base[c] = pd.NA

    return base

# ------------------ UI Layout ------------------
left, right = st.columns([0.66, 0.34])
b1, b2 = st.columns([0.5, 0.5])

with left:
    st.subheader("① Upload your data")
    st.caption("Allocations: your SKU + Qty. Duplicates will be summed.")
    inv_u   = st.file_uploader("Inventory", type=["csv","xlsx","xls"])
    oo_u    = st.file_uploader("Open Orders (PO report)", type=["csv","xlsx","xls"])
    alloc_u = st.file_uploader("Allocated / Shortages", type=["csv","xlsx","xls"])
    im_u    = st.file_uploader("Item Master (optional; default bundled)", type=["csv","xlsx","xls"])
    proj_u  = st.file_uploader("Projections (optional; default bundled)", type=["csv","xlsx","xls"])

with right:
    st.subheader("② Parameters")
    # Bind the number_inputs to session_state keys so session_state always reflects UI values
    lt  = st.number_input("Lead Time (days)",  min_value=0, max_value=365, value=st.session_state.lt, step=1, key="lt")
    rc  = st.number_input("Replen Cycle (days)", min_value=0, max_value=365, value=st.session_state.rc, step=1, key="rc")
    ss  = st.number_input("Safety Stock (days)", min_value=0, max_value=365, value=st.session_state.ss, step=1, key="ss")
    aggregate = st.checkbox("Aggregate OnHand by SKU (sum across locations)", value=True)

with b1:
    st.subheader("③ Setup")

    issues = []
    inv = im = proj = oo = alloc = None

    # Inventory
    if inv_u is not None:
        try:
            inv = slim_inventory(load_tabular(inv_u), aggregate=aggregate)
            st.success(f"Inventory loaded ({len(inv)} rows).")
        except Exception as e:
            issues.append(str(e))

    # Open Orders
    if oo_u is not None:
        try:
            oo = slim_open_orders(load_tabular(oo_u))
            st.success(f"Open Orders loaded ({len(oo)} rows).")
        except Exception as e:
            issues.append("Open Orders: " + str(e))

    # Allocations
    if alloc_u is not None:
        try:
            alloc = slim_allocations(load_tabular(alloc_u))
            st.success(f"Allocations loaded ({len(alloc)} SKUs after summing).")
        except Exception as e:
            issues.append("Allocations: " + str(e))

    # Item Master
    if im_u is not None:
        im_raw = load_tabular(im_u)
    elif DEFAULT_IM.exists():
        im_raw = load_tabular(DEFAULT_IM.open("rb"))
    else:
        im_raw = None
    if im_raw is not None:
        try:
            im = slim_item_master(im_raw)
            st.info("Item Master ready.")
        except Exception as e:
            issues.append("Item Master: " + str(e))

    # Projections + Month Picker (with Apply)
    proj_raw = None
    if proj_u is not None:
        proj_raw = detect_header_and_load(proj_u)
    elif DEFAULT_PROJ.exists():
        proj_raw = detect_header_and_load(DEFAULT_PROJ.open("rb"))

    if proj_raw is not None:
        try:
            month_cols = months_from_proj(proj_raw)
            if not month_cols:
                raise ValueError("Projections sheet is missing month columns like 'Sep 2025 Qty'.")
            auto_month = auto_select_projection_month(month_cols)
            idx = month_cols.index(st.session_state.get("proj_month") or auto_month)
            sel = st.selectbox("Forecast month", month_cols, index=idx, key="proj_month_select")
            if st.button("Apply month"):
                st.session_state.proj_month = sel
            selected_month = st.session_state.get("proj_month") or auto_month
            proj = build_velocity(proj_raw, selected_month)
            st.info(f"Using projection month: {selected_month}")
        except Exception as e:
            issues.append("Projections: " + str(e))
            proj = None
    else:
        proj = None
        st.info("No Projections uploaded; VelocityMonthly will be 0 unless defaults exist.")

    if issues:
        st.error(" • " + "\n • ".join(issues))

with b2:
    st.subheader("④ Recommended Orders")

    # Build master (now enriched via union IM join)
    master = build_master_sku(inv, alloc, oo, im)

    # Projections join (DelSolSku -> VelocityMonthly), else 0
    if 'DelSolSku' in master.columns and proj is not None:
        master = master.merge(proj, left_on="DelSolSku", right_on="ItemNumberJoin", how="left")
    if "VelocityMonthly" not in master.columns:
        master["VelocityMonthly"] = 0.0

    # Open Orders (aggregate by your SKU)
    if oo is not None and len(oo) > 0:
        oo_agg = oo.groupby("ItemNumber", as_index=False)["OrderQTY"].sum()
        master["_JOIN_SKU"]  = master["SKU"].map(_norm_key)
        oo_agg["_JOIN_ITEM"] = oo_agg["ItemNumber"].map(_norm_key)
        m = master.merge(
            oo_agg[["_JOIN_ITEM","OrderQTY"]].rename(columns={"OrderQTY":"OpenOrderQty"}),
            left_on="_JOIN_SKU", right_on="_JOIN_ITEM", how="left"
        )
        master["OpenOrderQty"] = m["OpenOrderQty"].fillna(0.0)
    else:
        master["OpenOrderQty"] = 0.0

    # Allocations (your SKU)
    if alloc is not None and len(alloc) > 0:
        if "_JOIN_SKU" not in master.columns:
            master["_JOIN_SKU"] = master["SKU"].map(_norm_key)
        master = master.merge(alloc[["_JOIN_SKU","AllocatedQty"]], on="_JOIN_SKU", how="left")
        master["AllocatedQty"] = master["AllocatedQty"].fillna(0.0)
    else:
        master["AllocatedQty"] = 0.0

    # --------- Calculation (matches your spreadsheet) ---------
    # RECOMMENDED = ((RC+SS+LT)*(VelocityMonthly/30)) - (OnHand - AllocatedQty + OpenOrderQty)
    # Use values from session_state which are kept in sync with the UI via keys above
    lt, rc, ss = st.session_state["lt"], st.session_state["rc"], st.session_state["ss"]

    master["VelocityMonthly"] = pd.to_numeric(master.get("VelocityMonthly", 0), errors="coerce").fillna(0.0)
    master["OnHand"]          = pd.to_numeric(master.get("OnHand", 0), errors="coerce").fillna(0.0)
    master["OpenOrderQty"]    = pd.to_numeric(master.get("OpenOrderQty", 0), errors="coerce").fillna(0.0)
    master["AllocatedQty"]    = pd.to_numeric(master.get("AllocatedQty", 0), errors="coerce").fillna(0.0)

    # compute daily velocity and target
    daily_velocity = master["VelocityMonthly"] / 30.0
    target_level   = (rc + ss + lt) * daily_velocity
    rhs            = master["OnHand"] - master["AllocatedQty"] + master["OpenOrderQty"]

    master["recommended_raw"] = target_level - rhs
    master["recommended"]     = master["recommended_raw"].apply(lambda x: max(0, math.ceil(float(x))))

    # --------- Output ---------
    cols = ["SKU","DelSolSku","ProductName",
            "Primary Vendor","Primary Vendor Sku","Status",
            "OnHand","AllocatedQty","OpenOrderQty","VelocityMonthly","recommended"]  # WarehouseName removed
    cols = [c for c in cols if c in master.columns]

    out = master[(master["AllocatedQty"] > 0) | (master["OpenOrderQty"] > 0) | (master["recommended"] > 0)][cols] \
            .sort_values(by=["recommended","AllocatedQty","OpenOrderQty"], ascending=[False, False, False]) \
            .reset_index(drop=True)

    st.dataframe(out, use_container_width=True)

    # Downloads
    def to_csv_xlsx(df, base):
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv = df.to_csv(index=False).encode("utf-8")
        xbuf = io.BytesIO()
        with pd.ExcelWriter(xbuf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="RecommendedOrders")
        return (csv, f"{base}_{now}.csv"), (xbuf.getvalue(), f"{base}_{now}.xlsx")

    csv, xlsx = to_csv_xlsx(out, "Final_Recommended_Orders_Report")
    st.download_button("Download CSV", data=csv[0], file_name=csv[1], mime="text/csv")
    st.download_button("Download XLSX", data=xlsx[0], file_name=xlsx[1],
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.caption("SilverScreen – DelSol MRP")
