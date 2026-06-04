"""
Equity GEX Terminal — Configuration
=====================================
Edit KITE_API_KEY and KITE_API_SECRET before running.
All other values are sane defaults you can tune per your preference.
"""

# ── Kite Connect credentials ─────────────────────────────────────────────────
KITE_API_KEY    = ""      # Your Zerodha Kite API key
KITE_API_SECRET = ""      # Your Zerodha Kite API secret

# ── Options pricing defaults ─────────────────────────────────────────────────
DEFAULT_RISK_FREE_RATE   = 0.07    # 7% p.a. (RBI repo rate proxy)

# ── Strike range ─────────────────────────────────────────────────────────────
# ±% from spot to include in GEX analysis.
# Stocks: 15% is usually sufficient. Widen for very volatile stocks (e.g. 20%).
DEFAULT_STRIKE_RANGE_PCT = 15

# ── Live engine refresh intervals ────────────────────────────────────────────
SPOT_REFRESH_INTERVAL    = 5       # seconds between LTP spot ticks
CHAIN_REFRESH_INTERVAL   = 300     # seconds between full option chain re-fetches
                                   # (300s = 5 min; reduce to 60s for active trading)

# ── UI preferences ───────────────────────────────────────────────────────────
CHART_HEIGHT             = 650
TABLE_HEIGHT             = 420
THEME                    = "plotly_dark"

# ── Alert thresholds ─────────────────────────────────────────────────────────
PCR_BULLISH_THRESHOLD    = 0.7     # PCR below this → extreme bullish sentiment
PCR_BEARISH_THRESHOLD    = 1.3     # PCR above this → extreme bearish sentiment
MAX_PAIN_WARN_PCT        = 0.02    # Warn if spot within 2% of max pain
PIN_RISK_HIGH_DTE        = 5       # Days to expiry below which pin risk is HIGH
IV_HIGH_THRESHOLD        = 45.0    # IV% above which is considered "high" for stocks
IV_EXTREME_THRESHOLD     = 65.0    # IV% above which straddle selling is attractive

# ── Scanner defaults ─────────────────────────────────────────────────────────
SCAN_BATCH_SIZE          = 5       # Symbols per batch in multi-stock scanner
                                   # Keep ≤10 to avoid Kite rate limits
