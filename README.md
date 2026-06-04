# 📈 Equity GEX Terminal — NSE Stock Monthly Options

A professional **Gamma Exposure (GEX)** analysis terminal for **NSE-listed F&O equities**,
built with Streamlit and Kite Connect v3.

> **Completely separate from the Index GEX Terminal** — different exchange logic,
> different expiry rules, different GEX normalisation, different charts.

---

## 🗂 Project Structure

```
equity_gex/
├── equity_app.py                  ← Main Streamlit application
├── config.py                      ← API credentials & tunable defaults
├── requirements.txt               ← Python dependencies
├── README.md                      ← This file
│
└── modules/
    ├── __init__.py                ← Package exports
    ├── equity_data_fetcher.py     ← Kite Connect wrapper + F&O universe
    ├── equity_gex_calculator.py   ← Black-Scholes Greeks + GEX engine
    ├── equity_utils.py            ← TTE, filters, formatters, labels
    └── equity_visualizations.py  ← All Plotly charts
```

---

## ⚡ Quick Start

```bash
# 1. Clone / copy the equity_gex/ folder
# 2. Install dependencies
pip install -r requirements.txt

# 3. Add Kite credentials in config.py
#    KITE_API_KEY    = "your_api_key"
#    KITE_API_SECRET = "your_api_secret"

# 4. Launch
streamlit run equity_app.py
```

Then in the browser:
1. Enter API Key + Secret in the sidebar
2. Click **Login to Kite** → authorise in Zerodha
3. Paste the request token from the redirect URL
4. Select a stock (NIFTY50 / NIFTY100 / Custom)
5. Pick the monthly expiry
6. Click **📥 Fetch Chain**
7. Click **🟢 GO LIVE**

---

## 🏗 Architecture

### Why Equity GEX is Different from Index GEX

| Dimension | Index GEX | Equity GEX |
|:---|:---|:---|
| **Exchange** | NFO (NSE) + BFO (BSE) | NFO only |
| **Expiry** | Weekly + Monthly | **Monthly only** (last Thursday) |
| **Spot key** | `NSE:NIFTY 50`, `BSE:SENSEX` | `NSE:RELIANCE` |
| **Instruments filter** | by index name (`NIFTY`, `SENSEX`) | by stock symbol (`RELIANCE`) |
| **Lot size** | Fixed per index | **Varies per stock** (auto-fetched) |
| **Strike step** | Fixed (50, 100, 25 pts) | **Varies per stock** (auto-detected) |
| **GEX scale** | ₹Cr (large notional) | ₹Cr or ₹L (smaller notional) |
| **GEX per ₹1** | Not typically tracked | **Key metric** for stocks |
| **Max Pain** | Moderate pull | **Strong gravitational pull** |
| **IV skew** | Relatively flat | **Strong put skew** typical |
| **Pin risk** | Low | **High** in final week |

---

## 📦 Module Reference

### `modules/equity_data_fetcher.py`

Core data access layer.

```python
from modules.equity_data_fetcher import EquityKiteManager, get_equity_expiries

km = EquityKiteManager(api_key, api_secret)
ok, msg = km.set_access_token(request_token)

# Get option chain
raw_df, spot = km.get_option_chain("RELIANCE", "26-JUN-2025", risk_free_rate=0.07)

# Metadata (auto-detected from NFO instruments)
lot  = km.get_lot_size("RELIANCE")        # e.g. 250
si   = km.get_strike_interval("RELIANCE") # e.g. 20.0
exps = km.get_available_expiries("RELIANCE")

# Multi-stock ATM snapshot (for scanner tab)
snap_df = km.get_atm_snapshot(["RELIANCE", "TCS", "INFY"], "26-JUN-2025")
```

**F&O Universe constants:**
```python
NIFTY50_STOCKS    # 50 NIFTY50 constituents with active options
NIFTY100_STOCKS   # 100 stocks (NIFTY50 + extra 50)
POPULAR_STOCKS    # 20 most actively traded
```

**Expiry helpers:**
```python
get_equity_expiries(6)          # Next 6 monthly expiries (last Thursday)
get_next_equity_expiry()        # Nearest upcoming expiry
```

---

### `modules/equity_gex_calculator.py`

Greeks engine and GEX calculations.

#### GEX Formula (Equity)
```
Call GEX = −gamma × call_OI × lot_size × spot² × 0.01
Put  GEX = +gamma × put_OI  × lot_size × spot² × 0.01
```

The `lot_size` factor is **critical** — without it, GEX across different stocks
is not comparable. RELIANCE lot=250, HDFC lot=550, TCS lot=150 — all very different
share-level exposures.

#### GEX per ₹1 Move
```
call_gex_pr = −gamma × call_OI × lot × spot   (₹ dealers sell per ₹1 rally)
put_gex_pr  = +gamma × put_OI  × lot × spot   (₹ dealers buy per ₹1 dip)
```
This is the most intuitive equity GEX metric:
> *"If RELIANCE moves ₹1 up, dealers must sell ₹X of RELIANCE to rehedge."*

#### Key Functions

```python
from modules.equity_gex_calculator import (
    calculate_equity_gex,       # Full GEX + Greeks for all strikes
    find_equity_gamma_levels,   # Key levels dict (walls, flip, max pain, PCR)
    recalculate_gex_delta,      # Fast spot-move update (reuses cached IV)
    calculate_oi_change_analysis, # Fresh money flow, IV skew type
)

gex_df = calculate_equity_gex(filtered_df, spot, expiry, rfr, lot_size)
levels = find_equity_gamma_levels(gex_df, spot, lot_size)
```

#### `find_equity_gamma_levels()` returns:
```python
{
    # OI-based walls
    "call_wall":          float,   # strike with highest call OI
    "put_wall":           float,   # strike with highest put OI

    # Gamma-based walls
    "call_gex_wall":      float,   # strike with most negative call GEX
    "put_gex_wall":       float,   # strike with most positive put GEX

    # Regime
    "gamma_flip":         float,   # zero-crossing of cumulative GEX
    "max_pain":           float,   # strike minimising buyer profits

    # Aggregate OI / Volume
    "total_call_oi":      float,
    "total_put_oi":       float,
    "total_call_volume":  float,
    "total_put_volume":   float,

    # Ratios
    "pcr":                float,   # OI put/call ratio
    "volume_pcr":         float,   # Volume put/call ratio

    # ATM
    "atm_strike":         float,
    "atm_straddle":       float,   # call_ltp + put_ltp at ATM
    "atm_call_iv":        float,
    "atm_put_iv":         float,
    "iv_skew":            float,   # put_iv − call_iv at ATM

    # Net exposures
    "total_gex":          float,
    "total_dex":          float,

    # Equity-specific
    "pin_risk":           float,   # 0–1 score (1 = spot exactly at max pain)
    "net_oi_change_calls":float,   # net fresh call OI (positive = new longs)
    "net_oi_change_puts": float,
}
```

---

### `modules/equity_utils.py`

Helper functions for formatting, filtering, and labelling.

```python
from modules.equity_utils import (
    calculate_tte,          # Time to expiry in years
    filter_strikes_pct,     # Keep strikes within ±N% of spot
    filter_strikes_n,       # Keep N strikes above/below ATM
    get_atm_strike,         # Round spot to nearest interval
    fmt_number,             # ₹1.23Cr, ₹45.6L, ₹12,345
    fmt_oi,                 # 1.23L, 45.6K
    days_to_expiry,         # Integer DTE
    expiry_tag,             # "🔴 3D (PIN RISK!)" or "🟢 22D"
    gex_regime,             # ("🟢 +GEX", "#22c55e") tuple
    iv_percentile_label,    # "🟠 High IV" etc.
    pcr_signal,             # ("🟢 Extreme Put Buying...", "#22c55e")
    straddle_breakeven,     # (lower_BE, upper_BE)
)
```

---

### `modules/equity_visualizations.py`

Eight Plotly charts, all accepting `(gex_df, spot_price, ..., symbol)`:

| Function | Chart | Key Feature |
|:---|:---|:---|
| `plot_equity_gex_profile()` | Horizontal GEX bars | Both OI and gamma walls, cumulative GEX line |
| `plot_equity_oi_chart()` | 3-row: OI / OI Change / Volume | OI change overlay shows fresh money |
| `plot_iv_skew_surface()` | 2-row: IV smile + spread | Put-call IV differential highlighted |
| `plot_equity_greeks_profile()` | Side-by-side call/put bars | Selectable greek |
| `plot_pin_risk_gauge()` | Gauge + indicator | Pin score, DTE-weighted, gamma flip status |
| `plot_gex_per_rupee()` | Bar chart | ₹ dealer hedge per ₹1 move |
| `build_equity_matrix()` | DataFrame | Styled pivot table across all strikes |

---

## 🖥 Application Tabs

### Tab 1 — 📊 GEX Profile
Horizontal bar chart of net GEX per strike (MenthorQ-style).
- Green bars = positive GEX (put-dominated, dealers buy dips)
- Red bars = negative GEX (call-dominated, dealers sell rallies)
- Cumulative GEX line (dotted orange) — zero crossing = Gamma Flip
- Four level lines: Call Wall (solid red), Put Wall (solid green), Gamma Flip (yellow), Max Pain (purple)
- Right panel: key levels table, regime badge, PCR signal, IV label

### Tab 2 — 📐 IV Skew
Volatility smile with put-call IV spread analysis.
- Call IV vs Put IV curves with fill between
- Skew bar chart: positive = put premium (normal for stocks)
- Skew type label: Put Skew / Call Skew / Symmetric
- Daily expected move calculation (ATM IV / √252 × spot)

### Tab 3 — 📋 OI & Volume
Three-panel chart: Open Interest, OI Change (fresh money), Volume.
- OI Change bars: bright = adding positions, dim = closing
- Fresh money flow summary table
- Volume PCR alongside OI PCR

### Tab 4 — ⚡ GEX / ₹1 Move
Bar chart of dealer rehedging pressure per ₹1 stock move.
- Most equity-specific view — not available in index terminals
- Green = dealers buy on up move (resistance), Red = dealers sell on down move (amplifies)
- Peak strike = highest dealer activity zone

### Tab 5 — 🎯 Pin Risk
Gauge chart for max pain proximity and gamma regime.
- Pin Score 0–100, DTE-weighted (multiplied near expiry)
- Gamma flip position indicator (% above/below)
- Full max pain theory explanation with trading ideas

### Tab 6 — 🔬 Matrix
Full strike-by-strike positioning grid.
- Rows: Call GEX, Put GEX, Net GEX, Call OI, Put OI, PCR, IV, LTP, Greeks
- ATM column highlighted in gold
- TOTAL column with chain-wide aggregates

### Tab 7 — 📊 Greeks
Greek profile charts (selectable: gamma, delta, vega, theta, rho).
- ATM greeks panel: call vs put comparison
- Portfolio-level exposure totals (DEX, GEX, VEX, TEX)

### Tab 8 — 🔍 Scanner
Multi-stock ATM straddle scanner.
- Scans NIFTY50 / NIFTY100 / Custom symbol list
- Fetches ATM call + put LTP, OI, straddle cost, PCR per stock
- Sortable by straddle %, cost, PCR, OI
- Download as CSV
- Use case: find cheapest/richest straddles across the F&O universe

---

## 🔌 Kite Connect Notes

### Authentication (daily)
Token expires at **6:00 AM IST** every day. Re-authenticate each morning.

```
Step 1: Enter API Key + Secret → Click "Login to Kite"
Step 2: Zerodha login page → Authorise → redirected to 127.0.0.1
Step 3: Copy request_token from URL → Paste → "Generate Session"
```

### Rate Limits
- `ltp()` — lightweight, safe to call every 5 seconds
- `quote()` — heavier, batched in 450-key chunks; call every 5+ minutes
- `instruments("NFO")` — ~3MB download, cached in memory until invalidated

### Permissions Required
Your Kite API app needs: **Historical Data** + **Market Quotes** enabled in the Kite developer console.

---

## 📊 GEX Interpretation for Equity Stocks

### Regime Logic
```
Net GEX > 0  →  Positive Gamma Regime
               Dealers long gamma → buy dips, sell rallies
               Price oscillates between Call Wall and Put Wall
               Low volatility, mean-reverting

Net GEX < 0  →  Negative Gamma Regime
               Dealers short gamma → sell dips, buy rallies
               Price trends strongly past walls
               Higher volatility, breakout regime
```

### Wall Mechanics
```
Call OI Wall  →  Resistance
  Large call OI = writers heavily short calls here
  As spot approaches, dealers sell futures to hedge
  Creates ceiling effect

Put OI Wall   →  Support
  Large put OI = writers heavily short puts here
  As spot approaches, dealers buy futures to hedge
  Creates floor effect

Gamma Flip    →  Regime Boundary
  Above = stable, dips bought back quickly
  Below = volatile, moves extend further
  Crossing triggers regime switch
```

### Max Pain (Equity-Specific)
Stocks show much stronger max pain pinning than indices because:
1. Floating supply is thinner (fewer participants)
2. Option writers often hedge with the underlying stock directly
3. Near expiry, writers actively defend their short strikes

Typical max pain gravity kicks in:
- **> 14 DTE**: negligible
- **7–14 DTE**: moderate pull
- **< 7 DTE**: strong pull
- **< 3 DTE**: dominant force

---

## ⚠️ Risk Warnings

- This tool is **educational only** and does **not** constitute financial advice
- Options trading involves substantial risk of loss
- GEX analysis is probabilistic, not deterministic
- Data may be delayed or incomplete outside market hours (9:15 AM – 3:30 PM IST)
- Kite session tokens expire at 6 AM daily — always re-authenticate
- The scanner fetches live OI which requires F&O data permission on your API key

---

## 🔄 Changelog

| Version | Change |
|:--------|:-------|
| 1.0.0 | Initial release — 8-tab equity GEX terminal |
| | Monthly-only expiry logic (last Thursday) |
| | Full Greek engine with lot-size normalisation |
| | GEX per ₹1 move (equity-specific metric) |
| | Pin risk gauge with DTE-weighted scoring |
| | Multi-stock ATM straddle scanner |
| | Live engine: 5s spot ticks + configurable chain refresh |
