
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
    """Pick the best month column based on 'today'."""
    keys = sorted([(month_key(c), c) for c in month_cols], key=lambda x: x[0])
    today = datetime.now()
    today_key = (today.year, today.month - 1)  # month_key uses 0-based month index
    prior = [kc for kc in keys if kc[0] <= today_key]
    if prior:
        return prior[-1][1]   # closest not after today
    return keys[0][1]         # all future -> earliest available

# ========= Readers =========
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

DASHES = r"\u2010\u2011\u2012\u2013\u2014\u2212"  # hyphen variants
DASH_RE = re.compile(f"[{DASHES}]")

def _norm_key(x):
    if pd.isna(x): return None
    s = str(x)
    s = DASH_RE.sub("-", s)      # normalize fancy dashes to ASCII hyphen
    s = s.strip().upper()
    return re.sub(r"[^A-Z0-9\-_/]", "", s)  # keep A-Z,0-9,-,_,/

# ========= Slimmers =========
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
        "ItemNumber","Item Number","SKU","sku","Sku","DelSolSku","Del Sol Sku"
    ])
    if item_col is None:
        raise ValueError("Open Orders require ItemNumber (or SKU/DelSolSku).")

    qty_col = first_col(oo_df, [
        "OrderQTY","Qty Ordered","QtyOrdered","Quantity Ordered","Qty"
    ])
    if qty_col is None:
        raise ValueError("Open Orders require a quantity column (e.g., 'Qty Ordered', 'QtyOrdered', or 'OrderQTY').")

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
    """Auto-pick one month column; standardize to ItemNumberJoin + VelocityMonthly (floats)."""
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
    Accepts a simple 'allocated shortages' sheet with two columns:
    - SKU (or ItemNumber)
    - Qty (allocated/short)
    Duplicates are allowed; we aggregate by SKU.
    """
    item_col = first_col(alloc_df, ["SKU","sku","Sku","ItemNumber","Item Number","DelSolSku","Del Sol Sku"])
    if item_col is None:
        raise ValueError("Allocated Items sheet must include a 'SKU' or 'ItemNumber' column.")
    qty_col = first_col(alloc_df, ["Qty","QTY","Quantity","AllocatedQty","Allocated Qty"])
    if qty_col is None:
        raise ValueError("Allocated Items sheet must include a qty column (e.g., 'Qty').")
    slim = alloc_df[[item_col, qty_col]].copy()
    slim.columns = ["ItemKey","AllocatedQty"]
    slim["AllocatedQty"] = pd.to_numeric(slim["AllocatedQty"], errors="coerce").fillna(0)
    slim["ItemKey_norm"] = slim["ItemKey"].map(_norm_key)
    # aggregate duplicates by normalized key
    slim = slim.groupby("ItemKey_norm", as_index=False)["AllocatedQty"].sum()
    return slim

# ========= Build a master SKU set (ensures allocations-only SKUs are included) =========
def build_master_sku(inv, alloc, oo, im):
    """
    Returns a DataFrame with at least columns:
      SKU, DelSolSku, OnHand, ProductName, WarehouseName
    Ensures:
      - All Inventory SKUs are included.
      - All Allocations appear even if not in Inventory (OnHand=0).
      - Open Orders items are mapped via SKU or DelSolSku and included if missing.
    """
    # Start with inventory (if present)
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

    # Normalized keys for matching
    base["_JOIN_SKU"] = base["SKU"].map(_norm_key)
    if "DelSolSku" in base.columns:
        base["_JOIN_DELSOL"] = base["DelSolSku"].map(_norm_key)
    else:
        base["_JOIN_DELSOL"] = pd.NA

    # Build reverse mapping tables from Item Master
    im_map = None
    if im is not None:
        im_tmp = im.copy()
        im_tmp["_JOIN_SKU"] = im_tmp["SKU"].map(_norm_key)
        im_tmp["_JOIN_DELSOL"] = im_tmp["DelSolSku"].map(_norm_key)
        im_map = im_tmp

    # === Ensure Allocations-only rows exist ===
    if alloc is not None and len(alloc) > 0:
        alloc_keys = set(alloc["ItemKey_norm"].dropna().tolist())

        # Try to resolve alloc keys to inventory SKUs via either SKU or DelSolSku mapping
        resolved = []
        if im_map is not None:
            # map via SKU
            m1 = im_map[["_JOIN_SKU","SKU","DelSolSku"]].rename(columns={"_JOIN_SKU":"_JOIN"})
            # map via DelSol
            m2 = im_map[["_JOIN_DELSOL","SKU","DelSolSku"]].rename(columns={"_JOIN_DELSOL":"_JOIN"})
            im_union = pd.concat([m1,m2], ignore_index=True).dropna(subset=["_JOIN"]).drop_duplicates("_JOIN")
            im_lookup = dict(zip(im_union["_JOIN"], zip(im_union["SKU"], im_union["DelSolSku"])))
        else:
            im_lookup = {}

        for k in alloc_keys:
            if k in set(base["_JOIN_SKU"].dropna().tolist()) or k in set(base["_JOIN_DELSOL"].dropna().tolist()):
                continue  # already present in base
            sku_val, dsku_val = None, None
            if k in im_lookup:
                sku_val, dsku_val = im_lookup[k]
            else:
                # If we don't know which system this key is from, assume it's a SKU.
                sku_val = k  # will be a normalized token; keep also a raw "SKU_guess"
            resolved.append({"SKU": sku_val, "DelSolSku": dsku_val, "OnHand": 0.0})

        if resolved:
            to_add = pd.DataFrame(resolved)
            for col in ["ProductName","WarehouseName","Primary Vendor","Primary Vendor Sku","Status"]:
                if col not in to_add.columns:
                    to_add[col] = pd.NA
            base = pd.concat([base[["SKU","DelSolSku","ProductName","WarehouseName","OnHand",
                                    "Primary Vendor","Primary Vendor Sku","Status"]],
                              to_add[["SKU","DelSolSku","ProductName","WarehouseName","OnHand",
                                      "Primary Vendor","Primary Vendor Sku","Status"]]], ignore_index=True).drop_duplicates(subset=["SKU","DelSolSku"], keep="first")

        # Recompute join keys after appending
        base["_JOIN_SKU"] = base["SKU"].map(_norm_key)
        base["_JOIN_DELSOL"] = base["DelSolSku"].map(_norm_key) if "DelSolSku" in base.columns else pd.NA

    # === Ensure Open Orders-only rows exist ===
    if oo is not None and len(oo) > 0:
        oo_tmp = oo.copy()
        oo_tmp["_JOIN_ITEM"] = oo_tmp["ItemNumber"].map(_norm_key)
        present_keys = set(filter(None, base["_JOIN_SKU"].dropna().tolist() + base["_JOIN_DELSOL"].dropna().tolist()))
        missing_keys = sorted(list(set(oo_tmp["_JOIN_ITEM"].dropna().tolist()) - present_keys))

        extra = []
        for k in missing_keys:
            sku_val, dsku_val = None, None
            if im_map is not None:
                # If k matches known SKU join:
                row_sku = im_map.loc[im_map["_JOIN_SKU"] == k, ["SKU","DelSolSku"]]
                row_dls = im_map.loc[im_map["_JOIN_DELSOL"] == k, ["SKU","DelSolSku"]]
                if len(row_sku) > 0:
                    sku_val = row_sku.iloc[0]["SKU"]; dsku_val = row_sku.iloc[0]["DelSolSku"]
                elif len(row_dls) > 0:
                    sku_val = row_dls.iloc[0]["SKU"]; dsku_val = row_dls.iloc[0]["DelSolSku"]
                else:
                    # Unknown: assume it's a SKU token
                    sku_val = k
            else:
                sku_val = k
            extra.append({"SKU": sku_val, "DelSolSku": dsku_val, "OnHand": 0.0})

        if extra:
            extra_df = pd.DataFrame(extra)
            for col in ["ProductName","WarehouseName","Primary Vendor","Primary Vendor Sku","Status"]:
                if col not in extra_df.columns:
                    extra_df[col] = pd.NA
            base = pd.concat([base, extra_df], ignore_index=True).drop_duplicates(subset=["SKU","DelSolSku"], keep="first")

        # Recompute join keys again
        base["_JOIN_SKU"] = base["SKU"].map(_norm_key)
        base["_JOIN_DELSOL"] = base["DelSolSku"].map(_norm_key) if "DelSolSku" in base.columns else pd.NA

    return base

# ========= UI Layout =========
left, right = st.columns([0.65, 0.35])
b1, b2 = st.columns([0.5, 0.5])

with left:
    st.subheader("① Upload your data")
    st.caption("Start with Inventory + Open Orders. Item Master & Projections are optional (defaults can be used).")
    inv_u = st.file_uploader("Inventory (ShipStation export; no scrubbing)", type=["csv","xlsx","xls"])
    oo_u  = st.file_uploader("Open Orders (PO report)", type=["csv","xlsx","xls"])
    alloc_u = st.file_uploader("Allocated / Shortages (two columns: SKU or DelSolSku, Qty; duplicates OK)", type=["csv","xlsx","xls"])
    im_u   = st.file_uploader("Item Master (optional; default bundled)", type=["csv","xlsx","xls"])
    proj_u = st.file_uploader("Projections (optional; default bundled)", type=["csv","xlsx","xls"])

with right:
    st.subheader("② Parameters")
    lt = st.number_input("Lead Time (days)", min_value=0, max_value=365, value=st.session_state.lt, step=1)
    rc = st.number_input("Replen Cycle (days)", min_value=0, max_value=365, value=st.session_state.rc, step=1)
    ss = st.number_input("Safety Stock (days)", min_value=0, max_value=365, value=st.session_state.ss, step=1)
    aggregate = st.checkbox("Aggregate OnHand by SKU (sum across rows/locations)", value=True)
    force_include_alloc = st.checkbox("Force-include allocations-only SKUs", value=True,
                                      help="Always include SKUs found in the Allocations file, even if missing from Inventory.")

with b1:
    st.subheader("③ Data checks & mapping")

    issues = []
    inv = im = proj = oo = alloc = None
    selected_month = None

    # Inventory (optional but recommended; no longer strictly required)
    if inv_u is not None:
        inv_raw = load_tabular(inv_u)
        try:
            inv = slim_inventory(inv_raw, aggregate=aggregate)
            st.success("Inventory loaded.")
            st.dataframe(inv.head(10), use_container_width=True)
        except Exception as e:
            issues.append(str(e))

    # Open Orders (optional but recommended)
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

    # Allocations / Shortages (explicit demand)
    if alloc_u is not None:
        try:
            alloc_raw = load_tabular(alloc_u)
            alloc = slim_allocations(alloc_raw)
            st.success("Allocated/Shortages loaded & aggregated (explicit demand).")
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
        st.info("No Item Master uploaded; cross-mapping may be limited.")

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

    # Build a master list that includes inventory + allocations + open orders
    master = build_master_sku(inv, alloc, oo, im)

    # Map projections using DelSolSku (if present)
    if 'DelSolSku' in master.columns and proj is not None:
        master = master.merge(proj, left_on="DelSolSku", right_on="ItemNumberJoin", how="left")
    else:
        master["VelocityMonthly"] = 0.0

    # Merge Open Orders (sum duplicates; match by SKU and/or DelSolSku with normalization)
    if oo is not None and len(oo) > 0:
        oo_agg = oo.groupby("ItemNumber", as_index=False)["OrderQTY"].sum()
        master["_JOIN_SKU"]    = master["SKU"].map(_norm_key)
        master["_JOIN_DELSOL"] = master["DelSolSku"].map(_norm_key) if "DelSolSku" in master.columns else pd.NA
        oo_agg["_JOIN_ITEM"]   = oo_agg["ItemNumber"].map(_norm_key)

        m_sku = master.merge(
            oo_agg[["_JOIN_ITEM","OrderQTY"]].rename(columns={"OrderQTY":"OrderQTY_by_SKU"}),
            left_on="_JOIN_SKU", right_on="_JOIN_ITEM", how="left"
        )
        m_dls = master.merge(
            oo_agg[["_JOIN_ITEM","OrderQTY"]].rename(columns={"OrderQTY":"OrderQTY_by_DelSol"}),
            left_on="_JOIN_DELSOL", right_on="_JOIN_ITEM", how="left"
        )
        master["OrderQTY_by_SKU"]    = m_sku.get("OrderQTY_by_SKU")
        master["OrderQTY_by_DelSol"] = m_dls.get("OrderQTY_by_DelSol")
        master["OrderQTY"] = master[["OrderQTY_by_SKU","OrderQTY_by_DelSol"]].fillna(0).max(axis=1)

        total_uploaded_oo = float(oo_agg["OrderQTY"].sum())
        matched_rows = int((master["OrderQTY"] > 0).sum())
        matched_total = float(master["OrderQTY"].sum())
        st.caption(f"Open Orders uploaded total: {total_uploaded_oo:,.0f}  •  Rows matched: {matched_rows}  •  Matched total across master: {matched_total:,.0f}")

        with st.expander("Debug: Unmatched open-order keys", expanded=False):
            inv_keys = set(filter(None, (master["_JOIN_SKU"].dropna().tolist() + master["_JOIN_DELSOL"].dropna().tolist())))
            oo_keys  = set(filter(None, oo_agg["_JOIN_ITEM"].dropna().tolist()))
            missing  = sorted(list(oo_keys - inv_keys))[:50]
            st.write({"unmatched_count": len(oo_keys - inv_keys), "examples": missing})
            st.dataframe(oo_agg.head(20))
    else:
        master["OrderQTY"] = 0.0

    # Merge Allocations as EXPLICIT DEMAND (always included if present)
    if alloc is not None and len(alloc) > 0:
        # Prepare join columns
        if "_JOIN_SKU" not in master.columns:
            master["_JOIN_SKU"] = master["SKU"].map(_norm_key)
        master = master.merge(
            alloc.rename(columns={"ItemKey_norm":"_JOIN_SKU"})[["_JOIN_SKU","AllocatedQty"]],
            on="_JOIN_SKU",
            how="left"
        )
    else:
        master["AllocatedQty"] = 0.0

    # ========= Calculation =========
    # Interpretations:
    #   - AllocatedQty is explicit demand that must be ordered in full.
    #   - Safety stock is computed from velocity (days * daily_velocity).
    #   - Target level = (lt + rc + ss) * daily_velocity.
    #   - Available now = OnHand (inventory on-hand).
    #   - Effective requirement = AllocatedQty + max(0, Target - Available) - Open Orders already placed.
    #
    # This ensures allocations ALWAYS appear and are fully covered in recommendations,
    # plus any additional qty to reach the target level (including safety stock).
    master["VelocityMonthly"] = pd.to_numeric(master.get("VelocityMonthly", 0), errors="coerce").fillna(0.0)
    master["AllocatedQty"]    = pd.to_numeric(master.get("AllocatedQty", 0), errors="coerce").fillna(0.0)
    master["OnHand"]          = pd.to_numeric(master.get("OnHand", 0), errors="coerce").fillna(0.0)
    master["OrderQTY"]        = pd.to_numeric(master.get("OrderQTY", 0), errors="coerce").fillna(0.0)

    daily_velocity = master["VelocityMonthly"] / 30.0
    target_level   = daily_velocity * (lt + rc + ss)
    # additional needed to reach target (can't be negative)
    to_target      = (target_level - master["OnHand"]).clip(lower=0)

    # Explicit demand (allocations) is additive on top of target fill
    # Then subtract open orders already placed.
    master["recommended_raw"] = master["AllocatedQty"] + to_target - master["OrderQTY"]

    # Round up to whole units, min 0
    master["recommended"] = master["recommended_raw"].apply(lambda x: max(0, math.ceil(x)))

    # ========= Output (show everything that needs attention) =========
    # Always include rows with: recommended>0 OR AllocatedQty>0 OR OrderQTY>0
    out = master[(master["recommended"] > 0) | (master["AllocatedQty"] > 0) | (master["OrderQTY"] > 0)].copy()

    # If user wants to force-include allocations-only SKUs (even if recommended=0 after math), keep them:
    if force_include_alloc and alloc is not None and len(alloc) > 0:
        out = pd.concat([out, master[master["AllocatedQty"] > 0]], ignore_index=True).drop_duplicates(subset=["SKU","DelSolSku"], keep="first")

    # Select columns nicely
    cols = ["SKU","DelSolSku"]
    for opt in ["Primary Vendor","Primary Vendor Sku","Status","ProductName","WarehouseName"]:
        if opt in master.columns: cols.append(opt)
    cols += ["OnHand","AllocatedQty","OrderQTY","VelocityMonthly","recommended"]
    cols = [c for c in cols if c in master.columns]

    out = out[cols].sort_values(
        by=[c for c in ["recommended","AllocatedQty","OrderQTY"] if c in cols],
        ascending=[False, False, False]
    ).reset_index(drop=True)

    # Diagnostics for allocations coverage
    if alloc is not None and len(alloc) > 0:
        matched_alloc = float(out["AllocatedQty"].fillna(0).sum())
        uploaded_alloc = float(alloc["AllocatedQty"].sum())
        st.caption(f"Allocations uploaded total: {uploaded_alloc:,.0f}  •  Allocations reflected in output: {matched_alloc:,.0f}")

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
            st.subheader("Aggregated Allocations (by normalized key)")
            st.caption("Duplicates combined. Keys are normalized to improve matching against SKU or DelSolSku.")
            st.dataframe(alloc, use_container_width=True)

            # download for allocations-only report
            now = datetime.now().strftime("%Y%m%d_%H%M%S")
            alloc_csv = alloc.rename(columns={"ItemKey_norm":"Key"}).to_csv(index=False).encode("utf-8")
            xbuf2 = io.BytesIO()
            with pd.ExcelWriter(xbuf2, engine="openpyxl") as w:
                alloc.rename(columns={"ItemKey_norm":"Key"}).to_excel(w, index=False, sheet_name="Allocated")
            st.download_button("Download Allocations CSV", data=alloc_csv,
                               file_name=f"Material_Shortages_Allocated_{now}.csv", mime="text/csv")
            st.download_button("Download Allocations XLSX", data=xbuf2.getvalue(),
                               file_name=f"Material_Shortages_Allocated_{now}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            st.info("No Allocated/Shortages sheet uploaded; nothing to report.")

st.caption("SilverScreen – DelSol MRP")
