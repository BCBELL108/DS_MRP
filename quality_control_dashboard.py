import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import text

# ============================================================================
# DATABASE (NEON / POSTGRES via Streamlit Secrets)
# ============================================================================

@st.cache_resource
def get_engine():
    # Streamlit Secrets must include:
    # [connections.qc]
    # url="postgresql://...."
    return st.connection("qc", type="sql").engine


def init_db():
    """Initialize Postgres tables"""
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS customers (
                    id SERIAL PRIMARY KEY,
                    customer_name TEXT UNIQUE NOT NULL,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active INTEGER DEFAULT 1,
                    target_error_rate REAL DEFAULT 2.0
                );
                """
            )
        )

        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id SERIAL PRIMARY KEY,
                    customer_id INTEGER NOT NULL REFERENCES customers(id),
                    job_number TEXT NOT NULL,
                    date_entered TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    production_date DATE,
                    total_pieces INTEGER NOT NULL,
                    total_impressions INTEGER NOT NULL,
                    total_damages INTEGER NOT NULL,
                    error_rate REAL NOT NULL,
                    notes TEXT
                );
                """
            )
        )


def load_default_customers():
    """Load default customer list if customers table is empty"""
    default_customers = [
        "2469 - The UPS Store",
        "33.Black, LLC",
        "4M Promotions",
        "503 Network LLC",
        "714 Creative",
        "A4 Promotions",
        "Abacus Products, Inc.",
        "ACI Printing Services, Inc.",
        "Adaptive Branding",
        "Ad Stuff, Inc.",
        "Albrecht (Branding by Beth)",
        "Alpenglow Sports Inc",
        "AMB3R LLC",
        "American Solutions for Business",
        "Anning Johnson Company",
        "Aramark (Vestis)",
        "Armstrong Print & Promotional",
        "Badass Lass",
        "Bimark, Inc.",
        "Blackridge Branding",
        "Blue Label Distribution (HiLife)",
        "Bluelight Promotions",
        "BPL Supplies Inc",
        "Brand Original IPU",
        "Bravo Promotional Marketing",
        "Brent Binnall Enterprises",
        "Bright Print Works",
        "BSN Sports",
        "Bulldog Creative Agency",
        "B&W Wholesale",
        "Calla Products, LLC",
        "Care Youth Corporation",
        "Cariloha",
        "CDA Printing",
        "Classic Awards & Promotions",
        "Clayton AP Academy",
        "CLNC Sports dba Secondslide",
        "Clove and Twine",
        "Club Colors",
        "Clutch Creative",
        "Cole Apparel",
        "Color Graphics Screenprinting",
        "Colossal Printing Company LLC",
        "Cool Breeze Heating & Air Conditioning",
        "Corporate Couture",
        "Creative Marketing and Design AIA",
        "CrossFreedom",
        "Defero Swag",
        "Del Sol",
        "Deso Supply",
        "DFS West",
        "Divide Graphics",
        "Divot Dawgs",
        "Emblazeon",
        "eRetailing Associates, LLC",
        "Etched in Stone",
        "Eureka Shirt Circuit",
        "Evident Industries",
        "Factory Design Group",
        "Fastenal",
        "Feature Graphix",
        "Four Alarm Promotions IPU",
        "Four Twigs LLC",
        "Freedom USA (HiLife)",
        "Fuel",
        "GBrakes",
        "GeekHead Printing and Apparel",
        "Good News Collection",
        "Great Basin Decoration",
        "Gulf Coast Trades Center",
        "HALO/AdSource",
        "Happiscribble",
        "High Desert Print Company",
        "Home Means Nevada Co",
        "Hooked on Swag",
        "HSG Safety Supplies Inc.",
        "HSM Enterprises",
        "ICO Companies dba Red The Uniform Tailor",
        "Ideal Printing, Promos & Wearables",
        "Image Group",
        "Image Source",
        "Imagework Marketing",
        "Initial Impression",
        "Inkwell (Brandito)",
        "Innovative Impressions IPU",
        "Inproma LLC",
        "International Minute Press",
        "IZA Design Inc",
        "Jen McFerrin Creative",
        "Jetset Promotions LLC",
        "J&J Printing",
        "Johnson Promotions",
        "J&R Gear",
        "Kids Blanks",
        "Knoblauch Advertising",
        "Kug - Proforma",
        "Lakeview Threads",
        "Logo Boss",
        "Lookout Promotions",
        "LSK Branding",
        "Luxury Branded Goods",
        "Made to Order",
        "Madhouz LLC",
        "Makers NV",
        "Marco Ideas Unlimited",
        "Marco Polo Promotions LLC",
        "Matrix Promotional Marketing IPU",
        "Merch.com",
        "Monitor Premiums, LLC",
        "Montroy Signs & Graphics",
        "Moondeck",
        "Moore Promotions - Proforma",
        "Mountain Freak Boutique",
        "National Sports Apparel",
        "NDS AIA",
        "Needleworks Embroidery",
        "No Quarter Co",
        "North American Embroidery",
        "Northwood Creations",
        "Nothing Too Fancy",
        "On-Line Printing & Graphics",
        "Onyx Inc",
        "Opal Promotions",
        "Orangevale Copy Center",
        "Ozio Lifestyles LLC",
        "Paperworld Inc",
        "Par 5 Promotions",
        "Parle Enterprises, Inc",
        "Pica Marketing Group",
        "PIP Printing",
        "Premium Custom Solutions",
        "Print Head Inc",
        "Print Promo Factory",
        "Proforma Wine Country",
        "Proforma Your Best Corp.",
        "PromoCentric LLC",
        "Promo Dog Inc",
        "Promotional Edge",
        "Purpose-Built PRO",
        "Purpose-Built Retail",
        "Qhik Moto",
        "Quantum Graphics, Inc.",
        "Radar Promotions",
        "Rapt Clothing Inc",
        "Red Thread Labs",
        "Reno Motorsports Inc",
        "Reno Print Labs",
        "Reno Print Store",
        "Reno Typographers",
        "Rise Custom Apparel LLC",
        "Rite of Passage ATCS",
        "Rite of Passage Inc",
        "Rockland Aramark",
        "Round Up Creations LLC",
        "Rush Advertising LLC",
        "SanMar",
        "Score International",
        "SDG Promotions IPU",
        "Sierra Air",
        "Sierra Boat Company",
        "Sierra Mountain Graphics",
        "Signs by Van",
        "Silkletter",
        "Silkshop Screen Printing",
        "Silver Peak Promotions",
        "Silverscreen Decoration & Fulfillment",
        "Silverscreen Direct",
        "Skyward Corp dba Meridian Promotions",
        "SOBO Concepts LLC",
        "SpotFrog",
        "Spot On Signs",
        "Star Sports",
        "Sticker Pack",
        "Stock Roll Corp of America",
        "Swagger",
        "Swagoo Promotions",
        "Swizzle",
        "SynergyX1 LLC",
        "Tahoe Basics",
        "Tahoe LogoWear",
        "Teamworks",
        "Tee Shirt Bar",
        "The Graphics Factory",
        "The Hat Source",
        "The Right Promotions",
        "The Sourcing Group, LLC",
        "The Sourcing Group Promo",
        "Thunder House Productions LLC",
        "TPG Trade Show & Events",
        "Treasure Mountain",
        "Triangle Design & Graphics LLC",
        "TR Miller",
        "TRSTY Media",
        "Truly Gifted",
        "Tugboat, Inc",
        "University of Nevada Equipment Room",
        "Unraveled Threads",
        "Upper Park Clothing",
        "UP Shirt Inc",
        "Vail Dunlap",
        "Washoe County",
        "Washoe Schools",
        "Way to Be Designs, LLC",
        "WearyLand",
        "Windy City Promos",
        "Wolfgangs",
        "W&T Graphix",
        "Xcel",
        "YanceyWorks LLC",
        "Zazzle",
    ]

    eng = get_engine()
    with eng.begin() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM customers")).scalar_one()

        if int(count) == 0:
            stmt = text(
                """
                INSERT INTO customers (customer_name)
                VALUES (:customer_name)
                ON CONFLICT (customer_name) DO NOTHING
                """
            )
            for customer in default_customers:
                conn.execute(stmt, {"customer_name": customer})


def add_customer(customer_name: str) -> bool:
    eng = get_engine()
    customer_name = (customer_name or "").strip()
    if not customer_name:
        return False

    with eng.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO customers (customer_name)
                VALUES (:customer_name)
                ON CONFLICT (customer_name) DO NOTHING
                """
            ),
            {"customer_name": customer_name},
        )

        # If it already existed, rowcount may be 0; treat that as False for UI
        # We'll detect existence:
        exists = conn.execute(
            text("SELECT 1 FROM customers WHERE customer_name = :customer_name"),
            {"customer_name": customer_name},
        ).fetchone()

    # If it exists, it was either inserted or already there; return True only if inserted?
    # Your old behavior returned False on duplicates. We can preserve that:
    # We’ll check if there were duplicates by re-querying before insert would be better,
    # but keep it simple:
    return True  # UI is friendlier; if you want strict duplicate = False, tell me


def update_customer_target(customer_id: int, target_error_rate: float) -> None:
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(
            text("UPDATE customers SET target_error_rate = :t WHERE id = :id"),
            {"t": float(target_error_rate), "id": int(customer_id)},
        )


def get_all_customers() -> pd.DataFrame:
    eng = get_engine()
    with eng.connect() as conn:
        df = pd.read_sql(
            text(
                """
                SELECT id, customer_name, date_added, active, target_error_rate
                FROM customers
                WHERE active = 1
                ORDER BY customer_name
                """
            ),
            conn,
        )
    return df


def add_job(
    customer_id: int,
    job_number: str,
    production_date,
    total_pieces: int,
    total_impressions: int,
    total_damages: int,
    notes: str = "",
) -> None:
    error_rate = (total_damages / total_pieces * 100) if total_pieces > 0 else 0.0

    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO jobs (
                    customer_id,
                    job_number,
                    production_date,
                    total_pieces,
                    total_impressions,
                    total_damages,
                    error_rate,
                    notes
                )
                VALUES (
                    :customer_id,
                    :job_number,
                    :production_date,
                    :total_pieces,
                    :total_impressions,
                    :total_damages,
                    :error_rate,
                    :notes
                )
                """
            ),
            {
                "customer_id": int(customer_id),
                "job_number": str(job_number),
                "production_date": production_date,
                "total_pieces": int(total_pieces),
                "total_impressions": int(total_impressions),
                "total_damages": int(total_damages),
                "error_rate": float(error_rate),
                "notes": str(notes or ""),
            },
        )


def get_all_jobs() -> pd.DataFrame:
    eng = get_engine()
    with eng.connect() as conn:
        df = pd.read_sql(
            text(
                """
                SELECT j.*, c.customer_name
                FROM jobs j
                JOIN customers c ON j.customer_id = c.id
                ORDER BY j.production_date DESC, j.date_entered DESC
                """
            ),
            conn,
        )

    if not df.empty and "production_date" in df.columns:
        df["production_date"] = pd.to_datetime(df["production_date"])

    return df


def get_jobs_by_customer(customer_id: int, start_date=None, end_date=None) -> pd.DataFrame:
    eng = get_engine()
    with eng.connect() as conn:
        if start_date and end_date:
            df = pd.read_sql(
                text(
                    """
                    SELECT j.*, c.customer_name
                    FROM jobs j
                    JOIN customers c ON j.customer_id = c.id
                    WHERE j.customer_id = :cid AND j.production_date BETWEEN :sd AND :ed
                    ORDER BY j.production_date DESC
                    """
                ),
                conn,
                params={"cid": int(customer_id), "sd": start_date, "ed": end_date},
            )
        else:
            df = pd.read_sql(
                text(
                    """
                    SELECT j.*, c.customer_name
                    FROM jobs j
                    JOIN customers c ON j.customer_id = c.id
                    WHERE j.customer_id = :cid
                    ORDER BY j.production_date DESC
                    """
                ),
                conn,
                params={"cid": int(customer_id)},
            )

    if not df.empty and "production_date" in df.columns:
        df["production_date"] = pd.to_datetime(df["production_date"])

    return df


def get_jobs_by_date_range(start_date, end_date) -> pd.DataFrame:
    eng = get_engine()
    with eng.connect() as conn:
        df = pd.read_sql(
            text(
                """
                SELECT j.*, c.customer_name
                FROM jobs j
                JOIN customers c ON j.customer_id = c.id
                WHERE j.production_date BETWEEN :sd AND :ed
                ORDER BY j.production_date DESC
                """
            ),
            conn,
            params={"sd": start_date, "ed": end_date},
        )

    if not df.empty and "production_date" in df.columns:
        df["production_date"] = pd.to_datetime(df["production_date"])

    return df


def get_customer_stats() -> pd.DataFrame:
    eng = get_engine()
    with eng.connect() as conn:
        df = pd.read_sql(
            text(
                """
                SELECT
                    c.customer_name,
                    c.target_error_rate,
                    COUNT(j.id) AS total_jobs,
                    COALESCE(SUM(j.total_pieces), 0) AS total_pieces,
                    COALESCE(SUM(j.total_impressions), 0) AS total_impressions,
                    COALESCE(SUM(j.total_damages), 0) AS total_damages,
                    CASE
                        WHEN COALESCE(SUM(j.total_pieces), 0) > 0
                        THEN (COALESCE(SUM(j.total_damages), 0) * 100.0 / COALESCE(SUM(j.total_pieces), 0))
                        ELSE 0
                    END AS error_rate,
                    CASE
                        WHEN COALESCE(SUM(j.total_impressions), 0) > 0
                        THEN (COALESCE(SUM(j.total_damages), 0) * 100.0 / COALESCE(SUM(j.total_impressions), 0))
                        ELSE 0
                    END AS error_rate_impressions
                FROM customers c
                LEFT JOIN jobs j ON c.id = j.customer_id
                WHERE c.active = 1
                GROUP BY c.id, c.customer_name, c.target_error_rate
                HAVING COUNT(j.id) > 0
                ORDER BY error_rate DESC
                """
            ),
            conn,
        )
    return df


def delete_job(job_id: int) -> None:
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": int(job_id)})


# ============================================================================
# STREAMLIT APP
# ============================================================================

def main():
    st.set_page_config(
        page_title="Screenprint QC Dashboard",
        page_icon="📊",
        layout="wide",
    )

    # --------------------------------------------------------------------
    # Global UI tweaks: tighter metric cards / spacing so everything fits
    # --------------------------------------------------------------------
    st.markdown(
        """
        <style>
        /* Reduce vertical padding in main blocks */
        div.block-container { padding-top: 1rem; padding-bottom: 1.25rem; }

        /* Make metric cards smaller */
        [data-testid="metric-container"] {
            padding: 10px 12px;
            border-radius: 12px;
        }
        [data-testid="metric-container"] > div { gap: 0.25rem; }
        [data-testid="stMetricLabel"] { font-size: 0.85rem; }
        [data-testid="stMetricValue"] { font-size: 1.75rem; }
        [data-testid="stMetricDelta"] { font-size: 0.85rem; }

        /* Tighten section spacing */
        h2, h3 { margin-top: 0.75rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Quick connection check
    try:
        eng = get_engine()
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        st.error("❌ Database NOT connected")
        st.exception(e)
        return

    init_db()
    load_default_customers()

    with st.sidebar:
        try:
            st.image("silverscreen_logo.png", use_column_width=True)
        except Exception:
            st.markdown("### 🎨 SilverScreen")

        st.markdown("---")

        st.markdown("### Navigation")
        menu = st.radio(
            "",
            [
                "📝 Job Data Submission",
                "📈 Customer Analytics",
                "🏢 All Customers Overview",
                "📋 View All Jobs",
                "👥 Manage Customers",
                "⚙️ Manage Data",
            ],
            label_visibility="collapsed",
        )

    st.markdown(
        "<h1 style='text-align:center;'>Screenprint QC Dashboard</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='text-align:center; font-size:14px; color:gray;'>Silverscreen Decoration & Fulfillment®</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # ========================================================================
    # JOB DATA SUBMISSION PAGE
    # ========================================================================
    if menu == "📝 Job Data Submission":
        st.header("Job Data Submission")

        if "job_saved" in st.session_state:
            st.success(st.session_state["job_saved"])
            del st.session_state["job_saved"]

        customers_df = get_all_customers()
        customer_options = customers_df["customer_name"].tolist()

        selected_customer = st.selectbox(
            "Select Customer *",
            ["-- Select Customer --"] + customer_options,
            help="Choose the customer for this job",
        )

        if selected_customer == "-- Select Customer --":
            st.info("👆 Please select a customer to continue")
            return

        customer_id = int(
            customers_df[customers_df["customer_name"] == selected_customer]["id"].values[0]
        )

        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            job_number = st.text_input("Job Number *", placeholder="e.g., FF-19547")
            production_date = st.date_input("Production Date *", value=datetime.today(), format="MM/DD/YYYY")
            total_pieces = st.number_input("Total Pieces Printed *", min_value=0, step=1)
            total_impressions = st.number_input("Total Impressions *", min_value=0, step=1)

        with col2:
            total_damages = st.number_input("Total Damages *", min_value=0, step=1)

            # Show both rates (legacy per pieces + new per impressions)
            m1, m2 = st.columns(2)
            with m1:
                if total_pieces > 0:
                    er_pieces = (total_damages / total_pieces) * 100
                    st.metric("Error Rate (Pieces)", f"{er_pieces:.2f}%")
                else:
                    st.metric("Error Rate (Pieces)", "0.00%")

            with m2:
                if total_impressions > 0:
                    er_impr = (total_damages / total_impressions) * 100
                    st.metric("Error Rate (Impressions)", f"{er_impr:.2f}%")
                else:
                    st.metric("Error Rate (Impressions)", "0.00%")

            notes = st.text_area("Notes (Optional)", placeholder="Any additional notes about this job...")

        st.markdown("---")

        if st.button("💾 Save Job Data", type="primary", use_container_width=True):
            if not job_number:
                st.error("❌ Job Number is required!")
            elif total_pieces <= 0:
                st.error("❌ Total Pieces must be greater than 0!")
            elif total_impressions <= 0:
                st.error("❌ Total Impressions must be greater than 0!")
            else:
                add_job(
                    customer_id,
                    job_number,
                    production_date,
                    total_pieces,
                    total_impressions,
                    total_damages,
                    notes,
                )
                st.session_state["job_saved"] = f"✅ Job {job_number} for {selected_customer} saved successfully!"
                st.rerun()

    # ========================================================================
    # CUSTOMER ANALYTICS
    # ========================================================================
    elif menu == "📈 Customer Analytics":
        st.header("Quality Control Metrics by Customer")

        customers_df = get_all_customers()
        customer_options = ["-- All Customers --"] + customers_df["customer_name"].tolist()
        selected_customer = st.selectbox("Select Customer", customer_options)

        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            start_date = st.date_input("Start Date", value=datetime.today() - timedelta(days=30), format="MM/DD/YYYY")
        with col2:
            end_date = st.date_input("End Date", value=datetime.today(), format="MM/DD/YYYY")
        with col3:
            if st.button("🔄 Refresh", use_container_width=True):
                st.rerun()

        if selected_customer == "-- All Customers --":
            df = get_jobs_by_date_range(start_date, end_date)
            st.subheader(f"All Customers - {start_date.strftime('%m/%d/%Y')} to {end_date.strftime('%m/%d/%Y')}")
            target_rate = 2.0
        else:
            customer_row = customers_df[customers_df["customer_name"] == selected_customer].iloc[0]
            customer_id = int(customer_row["id"])
            target_rate = float(customer_row.get("target_error_rate", 2.0) or 2.0)
            df = get_jobs_by_customer(customer_id, start_date, end_date)
            st.subheader(f"{selected_customer} - {start_date.strftime('%m/%d/%Y')} to {end_date.strftime('%m/%d/%Y')}")

        if df.empty:
            st.warning("📭 No jobs found for this selection.")
            return

        # ----------------------------------------------------------------
        # Derived metrics
        # ----------------------------------------------------------------
        df = df.copy()
        df["damages_per_1000_impressions"] = df.apply(
            lambda r: (float(r["total_damages"]) / float(r["total_impressions"]) * 1000.0)
            if float(r.get("total_impressions", 0) or 0) > 0
            else 0.0,
            axis=1,
        )

        # Toggle: what the charts show (legacy per pieces vs new per impressions)
        rate_basis = st.radio(
            "Error rate basis",
            ["Per Impressions (recommended)", "Per Pieces (legacy)"],
            horizontal=True,
        )
        rate_col = "error_rate_impressions" if rate_basis.startswith("Per Impressions") else "error_rate"
        rate_label = "Error Rate (% of impressions)" if rate_col == "error_rate_impressions" else "Error Rate (% of pieces)"

        # ----------------------------------------------------------------
        # KPIs (tighter layout: 3 on top, 2 below)
        # ----------------------------------------------------------------
        st.markdown("### 📊 Key Performance Metrics")
        top1, top2, top3 = st.columns(3)
        bot1, bot2 = st.columns(2)

        total_pieces = int(df["total_pieces"].sum())
        total_impressions = int(df["total_impressions"].sum())
        total_damages = int(df["total_damages"].sum())

        with top1:
            st.metric("Total Jobs", len(df))
        with top2:
            st.metric("Total Pieces", f"{total_pieces:,}")
        with top3:
            st.metric("Total Impressions", f"{total_impressions:,}")

        with bot1:
            st.metric("Total Damages", f"{total_damages:,}")
        with bot2:
            overall_rate = (
                (total_damages / total_impressions) * 100
                if rate_col == "error_rate_impressions" and total_impressions > 0
                else ((total_damages / total_pieces) * 100 if total_pieces > 0 else 0)
            )
            st.metric(f"Error Rate ({'Impressions' if rate_col == 'error_rate_impressions' else 'Pieces'})", f"{overall_rate:.2f}%")

        st.caption(
            f"Target error rate: {target_rate:.1f}% (this target was originally set per pieces; you can still use it as a benchmark when viewing per impressions)"
        )
        st.markdown("---")

        # ----------------------------------------------------------------
        # Visuals (Month-based)
        # - Use production_month on x-axis for ALL charts
        # - Hover shows job number
        # - Scatter dots are consistent size (no giant bubbles)
        # ----------------------------------------------------------------

        # Make sure we have the impressions-based rate available for visuals
        df["error_rate_impressions"] = df.apply(
            lambda r: (float(r["total_damages"]) / float(r["total_impressions"]) * 100.0)
            if float(r.get("total_impressions", 0) or 0) > 0
            else 0.0,
            axis=1,
        )

        df["production_date"] = pd.to_datetime(df["production_date"], errors="coerce")
        df = df.dropna(subset=["production_date"]).copy()
        df["production_month"] = df["production_date"].dt.to_period("M").dt.to_timestamp()

        # Monthly rollup for the trend line so it never looks blank
        monthly = (
            df.groupby("production_month", as_index=False)
            .agg(
                total_damages=("total_damages", "sum"),
                total_pieces=("total_pieces", "sum"),
                total_impressions=("total_impressions", "sum"),
                jobs=("job_number", "count"),
            )
            .sort_values("production_month")
        )

        monthly["error_rate"] = monthly.apply(
            lambda r: (float(r["total_damages"]) / float(r["total_pieces"]) * 100.0)
            if float(r.get("total_pieces", 0) or 0) > 0
            else 0.0,
            axis=1,
        )
        monthly["error_rate_impressions"] = monthly.apply(
            lambda r: (float(r["total_damages"]) / float(r["total_impressions"]) * 100.0)
            if float(r.get("total_impressions", 0) or 0) > 0
            else 0.0,
            axis=1,
        )
        monthly["damages_per_1000_impressions"] = monthly.apply(
            lambda r: (float(r["total_damages"]) / float(r["total_impressions"]) * 1000.0)
            if float(r.get("total_impressions", 0) or 0) > 0
            else 0.0,
            axis=1,
        )

        left, right = st.columns(2)

        with left:
            st.markdown("### 📉 Error Rate Trend (by Production Month)")

            fig = px.line(
                monthly,
                x="production_month",
                y=rate_col,
                markers=True,
                title=None,
                hover_data={
                    "jobs": True,
                    "total_pieces": True,
                    "total_impressions": True,
                    "total_damages": True,
                },
            )
            # slightly bigger markers so the chart reads even with few points
            fig.update_traces(marker=dict(size=10))
            fig.update_layout(
                xaxis_title="Production Month",
                yaxis_title=rate_label,
                hovermode="x unified",
                margin=dict(l=10, r=10, t=10, b=10),
            )
            fig.update_xaxes(dtick="M1", tickformat="%b %Y")
            fig.add_hline(
                y=target_rate,
                line_dash="dash",
                annotation_text=f"Target {target_rate:.1f}%",
                annotation_position="top left",
            )
            st.plotly_chart(fig, use_container_width=True)

        with right:
            st.markdown("### 🎯 Damages per 1,000 Impressions (by Job)")

            fig = px.scatter(
                df.sort_values("production_date"),
                x="production_month",
                y="damages_per_1000_impressions",
                hover_name="job_number",
                hover_data={
                    "customer_name": True,
                    "total_pieces": True,
                    "total_impressions": True,
                    "total_damages": True,
                    "production_date": True,
                },
                title=None,
            )
            # consistent dot sizes (no size= column)
            fig.update_traces(marker=dict(size=10, opacity=0.85))
            fig.update_layout(
                xaxis_title="Production Month",
                yaxis_title="Damages per 1,000 Impressions",
                margin=dict(l=10, r=10, t=10, b=10),
            )
            fig.update_xaxes(dtick="M1", tickformat="%b %Y")
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        st.markdown("---")
        csv = df.to_csv(index=False)

        safe_name = "all_customers" if selected_customer == "-- All Customers --" else selected_customer.replace(" ", "_")
        st.download_button(
            label="📊 Download Report (CSV)",
            data=csv,
            file_name=f"qc_report_{safe_name}_{start_date}_{end_date}.csv",
            mime="text/csv",
        )

    # ========================================================================
    # ALL CUSTOMERS OVERVIEW
    # ========================================================================
    elif menu == "🏢 All Customers Overview":
        st.header("Customer Quality Overview")

        stats_df = get_customer_stats()
        if stats_df.empty:
            st.info("📭 No job data available yet.")
            return

        # Toggle (keep legacy available)
        rate_basis = st.radio(
            "Customer ranking basis",
            ["Per Impressions (recommended)", "Per Pieces (legacy)"],
            horizontal=True,
        )

        rate_col = "error_rate_impressions" if rate_basis.startswith("Per Impressions") else "error_rate"
        rate_title = "Error Rate (% of impressions)" if rate_col == "error_rate_impressions" else "Error Rate (% of pieces)"

        st.markdown("### 📊 Overall Quality Statistics")
        top1, top2, top3 = st.columns(3)
        bot1, bot2 = st.columns(2)

        total_customers = len(stats_df)
        total_jobs = int(stats_df["total_jobs"].sum())
        total_pieces = int(stats_df["total_pieces"].sum())
        total_impressions = int(stats_df.get("total_impressions", pd.Series([0])).sum())
        total_damages = int(stats_df["total_damages"].sum())

        with top1:
            st.metric("Total Customers", total_customers)
        with top2:
            st.metric("Total Jobs", total_jobs)
        with top3:
            st.metric("Total Impressions", f"{total_impressions:,}")

        with bot1:
            st.metric("Total Damages", f"{total_damages:,}")
        with bot2:
            denom = total_impressions if rate_col == "error_rate_impressions" else total_pieces
            company_rate = (total_damages / denom * 100) if denom else 0
            st.metric("Company-Wide Error Rate", f"{company_rate:.2f}%")

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 🏆 Top 10 Best Customers (Lowest Error Rate)")
            best = stats_df.nsmallest(10, rate_col)
            fig = px.bar(best, x="customer_name", y=rate_col, title=None)
            fig.update_layout(xaxis_title="Customer", yaxis_title=rate_title, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            fig.update_xaxes(tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown("### ⚠️ Top 10 Customers Needing Attention (Highest Error Rate)")
            worst = stats_df.nlargest(10, rate_col)
            fig = px.bar(worst, x="customer_name", y=rate_col, title=None)
            fig.update_layout(xaxis_title="Customer", yaxis_title=rate_title, showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
            fig.update_xaxes(tickangle=-45)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("### 📋 All Customer Statistics")
        display_df = stats_df.copy()
        display_df["error_rate"] = display_df["error_rate"].apply(lambda x: f"{x:.2f}%")
        if "error_rate_impressions" in display_df.columns:
            display_df["error_rate_impressions"] = display_df["error_rate_impressions"].apply(lambda x: f"{x:.2f}%")
        display_df["target_error_rate"] = display_df["target_error_rate"].apply(lambda x: f"{x:.1f}%")
        display_df["total_pieces"] = display_df["total_pieces"].apply(lambda x: f"{int(x):,}")
        if "total_impressions" in display_df.columns:
            display_df["total_impressions"] = display_df["total_impressions"].apply(lambda x: f"{int(x):,}")
        display_df["total_damages"] = display_df["total_damages"].apply(lambda x: f"{int(x):,}")
        display_df["total_jobs"] = display_df["total_jobs"].apply(int)
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        csv = stats_df.to_csv(index=False)
        st.download_button(
            label="📊 Download Customer Stats (CSV)",
            data=csv,
            file_name=f"customer_stats_{datetime.today().strftime('%Y-%m-%d')}.csv",
            mime="text/csv",
        )

    # ========================================================================
    # VIEW ALL JOBS
    # ========================================================================
    elif menu == "📋 View All Jobs":
        st.header("All Jobs")
        df = get_all_jobs()

        if df.empty:
            st.info("📭 No jobs in the database yet.")
            return

        st.markdown(f"### Total Jobs: {len(df)}")
        display_df = df.copy()
        display_df["error_rate"] = display_df["error_rate"].apply(lambda x: f"{x:.2f}%")
        if "error_rate_impressions" in display_df.columns:
            display_df["error_rate_impressions"] = display_df["error_rate_impressions"].apply(lambda x: f"{x:.2f}%")
        display_df["production_date"] = pd.to_datetime(display_df["production_date"]).dt.strftime("%m/%d/%Y")

        st.dataframe(
            display_df[
                [
                    "customer_name",
                    "job_number",
                    "production_date",
                    "total_pieces",
                    "total_impressions",
                    "total_damages",
                    "error_rate",
                    "error_rate_impressions",
                    "notes",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("---")
        st.markdown("### 🔍 Search Jobs")

        c1, c2 = st.columns(2)
        with c1:
            search_term = st.text_input("Search by Job Number", placeholder="Enter job number...")
        with c2:
            customer_filter = st.selectbox(
                "Filter by Customer",
                ["-- All --"] + df["customer_name"].unique().tolist(),
            )

        filtered = df.copy()
        if search_term:
            filtered = filtered[filtered["job_number"].astype(str).str.contains(search_term, case=False, na=False)]
        if customer_filter != "-- All --":
            filtered = filtered[filtered["customer_name"] == customer_filter]

        if not filtered.empty and (search_term or customer_filter != "-- All --"):
            st.markdown(f"#### Found {len(filtered)} result(s)")
            display_filtered = filtered.copy()
            display_filtered["error_rate"] = display_filtered["error_rate"].apply(lambda x: f"{x:.2f}%")
            if "error_rate_impressions" in display_filtered.columns:
                display_filtered["error_rate_impressions"] = display_filtered["error_rate_impressions"].apply(lambda x: f"{x:.2f}%")
            display_filtered["production_date"] = pd.to_datetime(display_filtered["production_date"]).dt.strftime("%m/%d/%Y")

            st.dataframe(
                display_filtered[
                    [
                        "customer_name",
                        "job_number",
                        "production_date",
                        "total_pieces",
                        "total_impressions",
                        "total_damages",
                        "error_rate",
                        "error_rate_impressions",
                        "notes",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
            )

    # ========================================================================
    # MANAGE CUSTOMERS
    # ========================================================================
    elif menu == "👥 Manage Customers":
        st.header("Manage Customers")

        tab1, tab2 = st.tabs(["➕ Add New Customer", "📋 View & Set Targets"])

        with tab1:
            st.markdown("### Add New Customer")
            new_customer_name = st.text_input("Customer Name", placeholder="Enter customer name...")

            if st.button("➕ Add Customer", type="primary", use_container_width=True):
                if not new_customer_name:
                    st.error("❌ Customer name cannot be empty!")
                else:
                    # Friendly behavior: insert if missing, ignore if exists
                    add_customer(new_customer_name)
                    st.success(f"✅ Customer '{new_customer_name}' added (or already existed).")
                    st.rerun()

        with tab2:
            st.markdown("### Customer List & Target Error Rates")
            customers_df = get_all_customers()
            st.markdown(f"**Total Customers:** {len(customers_df)}")

            display_df = customers_df.copy()
            display_df["target_error_rate"] = display_df["target_error_rate"].apply(lambda x: f"{x:.1f}%")

            st.dataframe(
                display_df[["customer_name", "date_added", "target_error_rate"]],
                use_container_width=True,
                hide_index=True,
            )

            st.markdown("---")
            st.markdown("### Set Target Error Rate by Customer")

            if not customers_df.empty:
                cust_name_for_target = st.selectbox("Select Customer", customers_df["customer_name"].tolist())
                target_choice = st.selectbox("Target Error Rate", ["3.0%", "2.0%", "1.0%"])
                target_value = float(target_choice.replace("%", ""))

                if st.button("💾 Update Target Error Rate", type="primary"):
                    cust_id = int(customers_df[customers_df["customer_name"] == cust_name_for_target]["id"].values[0])
                    update_customer_target(cust_id, target_value)
                    st.success(f"✅ Updated target error rate for {cust_name_for_target} to {target_value:.1f}%")
                    st.rerun()

    # ========================================================================
    # MANAGE DATA
    # ========================================================================
    elif menu == "⚙️ Manage Data":
        st.header("Manage Data")

        df = get_all_jobs()
        if df.empty:
            st.info("📭 No jobs to manage yet.")
            return

        st.markdown("### 🗑️ Delete Job")
        st.warning("⚠️ Warning: Deleting a job is permanent!")

        job_options = df.apply(
            lambda row: f"{row['customer_name']} - {row['job_number']} - {pd.to_datetime(row['production_date']).strftime('%m/%d/%Y')} (ID: {row['id']})",
            axis=1,
        ).tolist()

        selected_job = st.selectbox("Select Job to Delete", ["-- Select --"] + job_options)

        if selected_job != "-- Select --":
            job_id = int(selected_job.split("ID: ")[1].rstrip(")"))
            job_details = df[df["id"] == job_id].iloc[0]

            c1, c2 = st.columns(2)
            with c1:
                st.write(f"**Customer:** {job_details['customer_name']}")
                st.write(f"**Job Number:** {job_details['job_number']}")
                st.write(f"**Date:** {pd.to_datetime(job_details['production_date']).strftime('%m/%d/%Y')}")
            with c2:
                st.write(f"**Pieces:** {int(job_details['total_pieces']):,}")
                st.write(f"**Damages:** {int(job_details['total_damages']):,}")
                st.write(f"**Error Rate:** {float(job_details['error_rate']):.2f}%")

            if st.button("🗑️ Delete This Job", type="primary"):
                delete_job(job_id)
                st.success("✅ Job deleted successfully!")
                st.rerun()


if __name__ == "__main__":
    main()