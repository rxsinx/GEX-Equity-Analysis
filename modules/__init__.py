"""
Equity GEX Terminal — Modules Package
=======================================
NSE F&O equity (stock) gamma exposure analysis.

Module map:
  equity_data_fetcher    → Kite Connect wrapper, F&O universe, option chain fetch
  equity_gex_calculator  → Black-Scholes Greeks, GEX/DEX/VEX/TEX, max pain
  equity_utils           → TTE, strike filter, formatting, labels
  equity_visualizations  → All Plotly charts for the Streamlit app
"""

from .equity_data_fetcher import (
    EquityKiteManager,
    EquityKiteError,
    EquityAuthError,
    EquityDataError,
    get_equity_expiries,
    get_next_equity_expiry,
    get_fo_universe,
    NIFTY50_STOCKS,
    NIFTY100_STOCKS,
    POPULAR_STOCKS,
)

from .equity_gex_calculator import (
    calculate_all_greeks_equity,
    calculate_equity_gex,
    find_equity_gamma_levels,
    recalculate_gex_delta,
    calculate_oi_change_analysis,
    format_gex_equity,
    gex_per_rupee,
)

from .equity_utils import (
    calculate_tte,
    filter_strikes_pct,
    filter_strikes_n,
    get_atm_strike,
    fmt_number,
    fmt_oi,
    moneyness_label,
    days_to_expiry,
    expiry_tag,
    gex_regime,
    iv_percentile_label,
    pcr_signal,
    straddle_breakeven,
)

from .equity_visualizations import (
    plot_equity_gex_profile,
    plot_equity_oi_chart,
    plot_iv_skew_surface,
    plot_equity_greeks_profile,
    plot_pin_risk_gauge,
    plot_gex_per_rupee,
    build_equity_matrix,
)

__all__ = [
    # Data fetcher
    "EquityKiteManager", "EquityKiteError", "EquityAuthError", "EquityDataError",
    "get_equity_expiries", "get_next_equity_expiry", "get_fo_universe",
    "NIFTY50_STOCKS", "NIFTY100_STOCKS", "POPULAR_STOCKS",
    # GEX calculator
    "calculate_all_greeks_equity", "calculate_equity_gex",
    "find_equity_gamma_levels", "recalculate_gex_delta",
    "calculate_oi_change_analysis", "format_gex_equity", "gex_per_rupee",
    # Utils
    "calculate_tte", "filter_strikes_pct", "filter_strikes_n",
    "get_atm_strike", "fmt_number", "fmt_oi",
    "moneyness_label", "days_to_expiry", "expiry_tag",
    "gex_regime", "iv_percentile_label", "pcr_signal", "straddle_breakeven",
    # Visualizations
    "plot_equity_gex_profile", "plot_equity_oi_chart", "plot_iv_skew_surface",
    "plot_equity_greeks_profile", "plot_pin_risk_gauge",
    "plot_gex_per_rupee", "build_equity_matrix",
]
