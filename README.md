# Silverscreen Order Calculator

# DelSol MRP Tool 📊

A powerful Material Requirements Planning (MRP) tool built with Streamlit for inventory management, order recommendations, and production planning.

![Version](https://img.shields.io/badge/version-v109-blue)
![Python](https://img.shields.io/badge/python-3.10+-green)
![Streamlit](https://img.shields.io/badge/streamlit-latest-red)

## 🎯 Overview

The DelSol MRP Tool helps businesses optimize their inventory ordering by analyzing:
- Current inventory levels
- Open purchase orders
- Allocated/committed inventory
- Sales projections and velocity
- Custom ordering rules (order multiples, safety stock, lead times)

**Key Features:**
- 📈 Automated order quantity recommendations based on MRP calculations
- 📊 Support for multiple data sources (Inventory, POs, Projections, Item Master)
- 🎨 Clean, intuitive web interface
- 💾 Export results to CSV or Excel
- 🔧 Configurable parameters (Lead Time, Replenishment Cycle, Safety Stock)
- 🎯 Special handling for custom items (on-demand ordering)

## 🚀 Quick Start

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/DS_MRP.git
cd DS_MRP
```

2. **Create a virtual environment** (recommended)
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Run the app**
```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`

## 📁 Data Requirements

### Required Files

Upload the following files through the web interface:

1. **Inventory** (CSV/Excel)
   - Required columns: `SKU`, `OnHand`
   - Optional: `ProductName`, `WarehouseName`

2. **Open Orders / PO Report** (CSV/Excel)
   - Required columns: `SKU` or `ItemNumber`, `Qty` or `Quantity Ordered`

3. **Allocated / Shortages** (CSV/Excel)
   - Required columns: `SKU`, `Qty` or `AllocatedQty`
   - Note: Duplicate SKUs will be automatically summed

### Optional Files

4. **Item Master** (CSV/Excel) - Enriches data with product details
   - Columns: `SKU`, `DelSolSku`, `ProductName`, `Primary Vendor`, `Primary Vendor Sku`, `Status`, `Primary Vendor Color`, `UnitCost`, `OrderMultiple`
   - Falls back to bundled default if not provided

5. **Projections** (CSV/Excel) - Sales forecast data
   - Must include columns like `Item Number` or `DelSolSku` and month columns like `Jan 2025 Qty`, `Feb 2025 Qty`, etc.
   - Falls back to bundled default if not provided

## ⚙️ Configuration

### MRP Parameters

- **Lead Time (days)**: Time from order placement to receipt (default: 7)
- **Replenishment Cycle (days)**: How often you order (default: 7)
- **Safety Stock (days)**: Buffer stock days (default: 21)

### MRP Calculation Logic

**For Regular Items:**
```
Target Level = (Replen Cycle + Safety Stock + Lead Time) × Daily Velocity
Recommended Qty = Target Level - (On Hand - Allocated + Open Orders)
```

**For Custom Items (Status = "CUSTOM"):**
```
Recommended Qty = Max(0, Allocated - (On Hand + Open Orders))
```
*Custom items only order what's needed to fulfill allocations*

**Order Multiples:**
- Recommendations are automatically rounded up to the nearest order multiple (case pack size)
- Example: If recommendation is 87 and order multiple is 24, system recommends 96 (4 cases)

## 📊 Output

The tool generates a prioritized list of recommended orders with:
- SKU and product details
- Current on-hand quantity
- Allocated quantity (commitments)
- Open order quantity (incoming stock)
- Unit cost and estimated total cost
- **Recommended order quantity** (rounded to order multiples)

Results can be downloaded as:
- 📄 CSV for data processing
- 📊 Excel for reporting and analysis

## 🏗️ Project Structure

```
DS_MRP/
├── app.py                          # Main Streamlit application
├── requirements.txt                # Python dependencies
├── README.md                       # This file
└── data/                          # Default data files (optional)
    ├── silverscreen_logo.png
    ├── projections_default.csv
    └── item_master_default_v2.csv
```

## 🛠️ Development

### Tech Stack
- **Python 3.10+**
- **Streamlit** - Web interface
- **Pandas** - Data manipulation
- **NumPy** - Numerical calculations
- **OpenPyXL** - Excel file handling

### Key Functions

- `slim_inventory()` - Normalizes inventory data
- `slim_open_orders()` - Processes PO data
- `slim_allocations()` - Aggregates allocated quantities
- `build_master_sku()` - Creates master dataset with enrichment
- `calculate_recommendation()` - Core MRP calculation logic
- `round_up_to_multiple()` - Rounds to order multiples

## 📝 Notes

- The app automatically detects headers in uploaded files
- SKU matching is case-insensitive and handles various dash types (–, —, -)
- Item Master can map both Inventory SKUs and DelSol SKUs
- Velocity is calculated as: Monthly Projection ÷ 30 days
- Negative recommendations are set to 0 (no ordering needed)

## 🐛 Troubleshooting

**Issue: "Missing required columns"**
- Check your file headers match expected column names
- The app is flexible with column names (e.g., "SKU", "Sku", "Item Number" all work)

**Issue: "No data showing in results"**
- Ensure you've uploaded at least Inventory and one other file
- Check that SKUs match between files
- Verify allocations or open orders exist

**Issue: "Excel file won't open"**
- Make sure you have Excel 2007+ (.xlsx) or use the CSV download

## 📧 Support

Built and maintained by Brandon Bell for SilverScreen Printing & Fulfillment

For questions or issues, please open an issue on GitHub.

## 📄 License

Proprietary - Internal use only for Silverscreen Printing & Fulfillment, Reno NV

---

**Version History**
- v108.1 - Most recent public release

