
import math, re, io
import pandas as pd
import numpy as np
import streamlit as st
from pathlib import Path
from datetime import datetime

st.set_page_config(page_title="DelSol MRP Tool", layout="wide")

# ========= Paths to bundled defaults =========
DATA_DIR = Path("data")
DEFAULT_IM = DATA_DIR / "item_master_default.csv"
DEFAULT_PROJ = DATA_DIR / "projections_default.csv"

# ========= UI defaults =========
st.session_state.setdefault("lt", 7)   # lead time (days)
st.session_state.setdefault("rc", 7)   # replen cycle (days)
st.session_state.setdefault("ss", 21)  # safety stock (days)

# ========= Month helpers for projections =========
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
    if prior:
        return prior[-1][1]
    return keys[0][1]

# ========= Readers =========
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
    if hasattr(file, "seek"):
        try: file.seek(0)
        except: pass
    df = read_any(file, header=0)
    df.columns = [str(c).strip() for c in df.columns]
    return df

# ========= Column detection / key normalization =========
def first_col(df, options):
    normalize = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())
    norm_map = {normalize(c): c for c in df.columns}
    for opt in options:
        key = normalize(opt)
        if key in norm_map:
            return norm_map[key]
    for opt in options:
        if opt in df.columns:
            return opt
    return None

DASHES = r"\u2010\u2011\u2012\u2013\u2014\u2212"
DASH_RE = re.compile(f"[{DASHES}]")

def _norm_key(x):
    if pd.isna(x): return None
    s = str(x)
    s = DASH_RE.sub("-", s)
    s = s.strip().upper()
    return re.sub(r"[^A-Z0-9\-_/]", "", s)

# ========= Slimmers =========
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
    item_col = first_col(oo_df, ["ItemNumber","Item Number","SKU","sku","Sku","DelSolSku","Del Sol Sku"])
    if item_col is None:
        raise ValueError("Open Orders require ItemNumber (or SKU/DelSolSku).")
    qty_col = first_col(oo_df, ["OrderQTY","Qty Ordered","QtyOrdered","Quantity Ordered","Qty"])
    if qty_col is None:
        raise ValueError("Open Orders require a quantity column.")
    slim = oo_df[[item_col, qty_col]].copy().rename(columns={item_col:"ItemNumber", qty_col:"OrderQTY"})
    slim["OrderQTY"] = pd.to_numeric(slim["OrderQTY"], errors="coerce").fillna(0.0)
    return slim

def slim_item_master(im_df):
    sku_col  = first_col(im_df, ["SKU","Silverscreen Sku","ItemNumber","itemnumber","sku"])
    dels_col = first_col(im_df, ["DelSolSku","Del Sol Sku","ItemNumber","itemnumber"])
    if not sku_col or not dels_col:
        raise ValueError("Item Master must include Inventory SKU and DelSolSku/Item Number.")
    vendor     = first_col(im_df, ["Primary Vendor","Vendor","PrimaryVendor","primary vendor","primary_vendor"])
    vendor_sku = first_col(im_df, ["Primary Vendor Sku","Primary Vendor SKU","Vendor Sku","Vendor SKU","primary vendor sku","primary_vendor_sku"])
    status     = first_col(im_df, ["Status","Item Status","status"])
    keep = [sku_col, dels_col] + [c for c in [vendor, vendor_sku, status] if c]
    im = im_df[keep].copy()
    rename_map = {sku_col:"SKU", dels_col:"DelSolSku"}
    if vendor:     rename_map[vendor] = "Primary Vendor"
    if vendor_sku: rename_map[vendor_sku] = "Primary Vendor Sku"
    if status:     rename_map[status] = "Status"
    im = im.rename(columns=rename_map)
    im = im.drop_duplicates(subset=["SKU"], keep="first")
    return im

def slim_projections(proj_df):
    join_col = first_col(proj_df, ["Item Number","Del Sol Sku","DelSolSku","ItemNumber","itemnumber"])
    if not join_col:
        raise ValueError("Projections need a join column: Item Number / DelSolSku")
    month_cols = [c for c in proj_df.columns if isinstance(c, str) and MONTH_RE.match(c.strip())]
    if not month_cols:
        raise ValueError("Projections sheet is missing month columns like 'Sep 2025 Qty'.")
    selected = auto_select_projection_month(month_cols)
    st.caption(f"Projections month auto-selected: {selected}")
    slim = proj_df[[join_col, selected]].copy()
    slim = slim.rename(columns={join_col:"ItemNumberJoin", selected:"VelocityMonthly"})
    slim["VelocityMonthly"] = pd.to_numeric(slim["VelocityMonthly"], errors="coerce").fillna(0.0)
    slim = slim.drop_duplicates(subset=["ItemNumberJoin"], keep="first")
    return slim, selected

def slim_allocations(alloc_df):
    """
    Allocations file is ALWAYS your internal SKU + Qty.
    We SUM by SKU and preserve the exact SKU string for display.
    """
    item_col = first_col(alloc_df, ["SKU","sku","Sku","ItemNumber","Item Number"])
    if item_col is None:
        raise ValueError("Allocated Items sheet must include a 'SKU' column.")
    qty_col = first_col(alloc_df, ["Qty","QTY","Quantity","AllocatedQty","Allocated Qty"])
    if qty_col is None:
        raise ValueError("Allocated Items sheet must include a qty column (e.g., 'Qty').")

    df = alloc_df[[item_col, qty_col]].copy()
    df.columns = ["SKU", "AllocatedQty"]
    df["AllocatedQty"] = pd.to_numeric(df["AllocatedQty"], errors="coerce").fillna(0).clip(lower=0)
    # normalize key for matching; keep canonical raw SKU for output
    df["_JOIN_SKU"] = df["SKU"].map(_norm_key)
    # group: sum qty, keep first seen raw SKU spelling
    df = df.groupby("_JOIN_SKU", as_index=False).agg(
        AllocatedQty=("AllocatedQty", "sum"),
        SKU=("SKU", "first")
    )
    return df

# ========= Build a master SKU set (inventory + allocations + open orders) =========
def build_master_sku(inv, alloc, oo, im):
    cols = ["SKU","ProductName","WarehouseName","OnHand"]
    if inv is not None:
        base = inv.copy()
        for c in cols:
            if c not in base.columns:
                base[c] = pd.NA if c != "OnHand" else 0.0
    else:
        base = pd.DataFrame(columns=cols)

    # Add Item Master columns if present
    if im is not None:
        base = base.merge(im, on="SKU", how="left")
    else:
        base["DelSolSku"] = pd.NA

    # Join keys
    base["_JOIN_SKU"] = base["SKU"].map(_norm_key)

    # Ensure Allocations-only rows exist (use RAW SKU from allocations)
    if alloc is not None and len(alloc) > 0:
        alloc_keys = set(alloc["_JOIN_SKU"].dropna().tolist())
        present_keys = set(base["_JOIN_SKU"].dropna().tolist())
        missing_keys = sorted(list(alloc_keys - present_keys))
        if missing_keys:
            # map missing JOIN keys -> raw SKU string from alloc
            lookup_raw = dict(zip(alloc["_JOIN_SKU"], alloc["SKU"]))
            add = [{"SKU": lookup_raw[k], "OnHand": 0.0} for k in missing_keys]
            add_df = pd.DataFrame(add)
            # carry any expected columns
            for col in ["ProductName","WarehouseName","Primary Vendor","Primary Vendor Sku","Status","DelSolSku"]:
                if col not in add_df.columns:
                    add_df[col] = pd.NA
            base = pd.concat([base, add_df], ignore_index=True)
            base["_JOIN_SKU"] = base["SKU"].map(_norm_key)

    # Ensure Open Orders-only rows exist via normalized item key
    if oo is not None and len(oo) > 0:
        oo_tmp = oo.copy()
        oo_tmp["_JOIN_ITEM"] = oo_tmp["ItemNumber"].map(_norm_key)
        present_keys = set(base["_JOIN_SKU"].dropna().tolist())
        missing_keys = sorted(list(set(oo_tmp["_JOIN_ITEM"].dropna().tolist()) - present_keys))
        if missing_keys:
            extra = [{"SKU": k, "OnHand": 0.0} for k in missing_keys]  # best effort if SKU-like
            extra_df = pd.DataFrame(extra)
            for col in ["ProductName","WarehouseName","Primary Vendor","Primary Vendor Sku","Status","DelSolSku"]:
                if col not in extra_df.columns:
                    extra_df[col] = pd.NA
            base = pd.concat([base, extra_df], ignore_index=True).drop_duplicates(subset=["SKU"], keep="first")
            base["_JOIN_SKU"] = base["SKU"].map(_norm_key)

    return base

# ========= UI Layout =========
left, right = st.columns([0.66, 0.34])
b1, b2 = st.columns([0.5, 0.5])

with left:
    st.subheader("① Upload your data")
    st.caption("Inventory + Open Orders recommended. Allocations file is YOUR SKU + Qty; duplicates will be summed.")
    inv_u  = st.file_uploader("Inventory (ShipStation export; no scrubbing)", type=["csv","xlsx","xls"])
    oo_u   = st.file_uploader("Open Orders (PO report)", type=["csv","xlsx","xls"])
    alloc_u= st.file_uploader("Allocated / Shortages (Your SKU, Qty)", type=["csv","xlsx","xls"])
    im_u   = st.file_uploader("Item Master (optional; default bundled)", type=["csv","xlsx","xls"])
    proj_u = st.file_uploader("Projections (optional; default bundled)", type=["csv","xlsx","xls"])

with right:
    st.subheader("② Parameters")
    lt = st.number_input("Lead Time (days)", min_value=0, max_value=365, value=st.session_state.lt, step=1)
    rc = st.number_input("Replen Cycle (days)", min_value=0, max_value=365, value=st.session_state.rc, step=1)
    ss = st.number_input("Safety Stock (days)", min_value=0, max_value=365, value=st.session_state.ss, step=1)
    aggregate = st.checkbox("Aggregate OnHand by SKU (sum across rows/locations)", value=True)
    ignore_pos_for_alloc = st.checkbox(
        "Ignore open POs when covering allocations (recommended)",
        value=True,
        help="If ON, the shortage is always ordered in full. If OFF, we subtract open POs from the shortage."
    )
    sku_probe = st.text_input("Debug: probe a SKU (e.g., 4T93-XL)", value="")

with b1:
    st.subheader("③ Data checks & mapping")

    issues = []
    inv = im = proj = oo = alloc = None
    selected_month = None

    # Inventory (optional but recommended)
    if inv_u is not None:
        inv_raw = load_tabular(inv_u)
        try:
            inv = slim_inventory(inv_raw, aggregate=aggregate)
            st.success("Inventory loaded.")
            st.dataframe(inv.head(10), use_container_width=True)
        except Exception as e:
            issues.append(str(e))

    # Open Orders (optional)
    if oo_u is not None:
        try:
            oo_raw = load_tabular(oo_u)
            oo = slim_open_orders(oo_raw)
            st.info("Open Orders included.")
            with st.expander("Debug: Open Orders mapping", expanded=False):
                item_guess = first_col(oo_raw, ["ItemNumber","Item Number","SKU","sku","Sku","DelSolSku","Del Sol Sku"])
                qty_guess  = first_col(oo_raw, ["OrderQTY","Qty Ordered","QtyOrdered","Quantity Ordered","Qty"])
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

    # Allocations / Shortages (explicit demand; YOUR SKU)
    if alloc_u is not None:
        try:
            alloc_raw = load_tabular(alloc_u)
            alloc = slim_allocations(alloc_raw)
            st.success("Allocated/Shortages loaded & aggregated (explicit demand by YOUR SKU).")
            st.dataframe(alloc.head(10), use_container_width=True)
        except Exception as e:
            issues.append("Allocated/Shortages: " + str(e))
    else:
        st.info("No Allocated/Shortages sheet uploaded; assuming 0 allocations.")

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
        st.info("No Item Master uploaded; vendor mapping limited.")

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

    # Build master (inventory + allocations + open orders)
    master = build_master_sku(inv, alloc, oo, im)

    # Projections join (via DelSolSku if available; otherwise velocity=0)
    if 'DelSolSku' in master.columns and isinstance(master['DelSolSku'], pd.Series) and proj is not None:
        master = master.merge(proj, left_on="DelSolSku", right_on="ItemNumberJoin", how="left")
    else:
        master["VelocityMonthly"] = 0.0

    # Open Orders (aggregate; join by normalized key into master)
    if oo is not None and len(oo) > 0:
        oo_agg = oo.groupby("ItemNumber", as_index=False)["OrderQTY"].sum()
        master["_JOIN_SKU"]   = master["SKU"].map(_norm_key)
        oo_agg["_JOIN_ITEM"]  = oo_agg["ItemNumber"].map(_norm_key)
        m = master.merge(
            oo_agg[["_JOIN_ITEM","OrderQTY"]].rename(columns={"OrderQTY":"OpenOrderQty"}),
            left_on="_JOIN_SKU", right_on="_JOIN_ITEM", how="left"
        )
        master["OpenOrderQty"] = m.get("OpenOrderQty").fillna(0.0)
    else:
        master["OpenOrderQty"] = 0.0

    # Allocations merge (YOUR SKU)
    if alloc is not None and len(alloc) > 0:
        if "_JOIN_SKU" not in master.columns:
            master["_JOIN_SKU"] = master["SKU"].map(_norm_key)
        master = master.merge(alloc[["_JOIN_SKU","AllocatedQty"]], on="_JOIN_SKU", how="left")
        master["AllocatedQty"] = master["AllocatedQty"].fillna(0.0)
    else:
        master["AllocatedQty"] = 0.0

    # ========= Calculation =========
    master["VelocityMonthly"] = pd.to_numeric(master.get("VelocityMonthly", 0), errors="coerce").fillna(0.0)
    master["OnHand"]          = pd.to_numeric(master.get("OnHand", 0), errors="coerce").fillna(0.0)
    master["OpenOrderQty"]    = pd.to_numeric(master.get("OpenOrderQty", 0), errors="coerce").fillna(0.0)
    master["AllocatedQty"]    = pd.to_numeric(master.get("AllocatedQty", 0), errors="coerce").fillna(0.0)

    daily_velocity = master["VelocityMonthly"] / 30.0
    # Safety stock units (only if velocity exists; else 0 per your rule)
    ss_units = (daily_velocity * ss).apply(lambda x: math.ceil(x) if x > 0 else 0)

    # --- Allocated SKUs path: order shortage + safety stock (if velocity>0).
    #     If ignore_pos_for_alloc is OFF, subtract open POs from shortage.
    if ignore_pos_for_alloc:
        alloc_component = master["AllocatedQty"]
    else:
        alloc_component = (master["AllocatedQty"] - master["OpenOrderQty"]).clip(lower=0)

    rec_alloc = alloc_component + ss_units

    # --- Non-allocated SKUs path: standard target = (lt+rc+ss) * daily_velocity
    target_level = daily_velocity * (lt + rc + ss)
    to_target    = (target_level - master["OnHand"]).clip(lower=0)
    rec_normal   = (to_target - master["OpenOrderQty"]).apply(lambda x: math.ceil(x) if x > 0 else 0)

    # Choose path per row
    master["recommended"] = np.where(master["AllocatedQty"] > 0, rec_alloc, rec_normal)
    master["recommended"] = master["recommended"].apply(lambda x: max(0, math.ceil(float(x))))

    # ========= Output =========
    cols = ["SKU","DelSolSku","ProductName","WarehouseName","Primary Vendor","Primary Vendor Sku","Status",
            "OnHand","AllocatedQty","OpenOrderQty","VelocityMonthly","recommended"]
    cols = [c for c in cols if c in master.columns]

    # Always include all allocations, even if recommended == 0 due to settings
    out = master[(master["AllocatedQty"] > 0) | (master["recommended"] > 0)][cols] \
            .sort_values(by=["AllocatedQty","recommended","OpenOrderQty"], ascending=[False, False, False]) \
            .reset_index(drop=True)

    # Debug probe (e.g., 4T93-XL)
    if sku_probe:
        key = _norm_key(sku_probe)
        probe_cols = cols + [c for c in ["_JOIN_SKU"] if c in master.columns]
        probe = master[master["_JOIN_SKU"] == key][probe_cols]
        st.markdown("**Debug – Probe result**")
        st.dataframe(probe, use_container_width=True)

    # Diagnostics captions
    if alloc is not None and len(alloc) > 0:
        uploaded_alloc = float(alloc["AllocatedQty"].sum())
        reflected_alloc = float(out["AllocatedQty"].fillna(0).sum())
        st.caption(f"Allocations uploaded total: {uploaded_alloc:,.0f} • Allocations reflected in output: {reflected_alloc:,.0f}")

    st.dataframe(out, use_container_width=True)

    # ========= Downloads =========
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

    # ========= Standalone Material Shortages / Allocated Items report =========
    st.markdown("---")
    if st.button("Material Shortages / Allocated Items"):
        if alloc is not None and len(alloc) > 0:
            st.subheader("Aggregated Allocations (by YOUR SKU)")
            st.caption("Duplicates combined. Keys normalized to ensure clean matching.")
            st.dataframe(alloc.rename(columns={"_JOIN_SKU":"Key"}), use_container_width=True)
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            alloc_csv = alloc.rename(columns={"_JOIN_SKU":"Key"}).to_csv(index=False).encode("utf-8")
            xbuf2 = io.BytesIO()
            with pd.ExcelWriter(xbuf2, engine="openpyxl") as w:
                alloc.rename(columns={"_JOIN_SKU":"Key"}).to_excel(w, index=False, sheet_name="Allocated")
            st.download_button("Download Allocations CSV", data=alloc_csv,
                               file_name=f"Material_Shortages_Allocated_{now}.csv", mime="text/csv")
            st.download_button("Download Allocations XLSX", data=xbuf2.getvalue(),
                               file_name=f"Material_Shortages_Allocated_{now}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("No Allocated/Shortages sheet uploaded; nothing to report.")

st.caption("SilverScreen – DelSol MRP")
