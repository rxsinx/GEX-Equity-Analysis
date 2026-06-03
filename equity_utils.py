"""
modules/equity_utils.py
========================
Utility helpers specific to equity (stock) option analysis.

Key difference from index utils:
• Equity options are MONTHLY only — last Thursday of month.
• Strike intervals vary per stock price range.
• Lot sizes are stock-specific and change each F&O revision cycle.
• Filter logic: equity chains are typically ±10-15% from ATM
  but we also offer a "±N strikes" mode for thinly-traded stocks.
"""

from __future__ import annotations

from datetime import datetime, timedelta
import calendar
from typing import Optional

import pandas as pd


# ─── Time to Expiry ─────────────────────────────────────────────────────────

def calculate_tte(expiry_str: str) -> float:
    """Time to expiry in years. Minimum 1 day."""
    try:
        exp = datetime.strptime(expiry_str, "%d-%b-%Y")
        secs = (exp - datetime.now()).total_seconds()
        return max(secs / (365 * 86_400), 1 / 365)
    except Exception:
        return 1 / 365


# ─── Strike filtering ───────────────────────────────────────────────────────

def filter_strikes_pct(
    df: pd.DataFrame,
    spot: float,
    range_pct: float = 15.0,
) -> pd.DataFrame:
    """Keep strikes within ±range_pct % of spot."""
    lo = spot * (1 - range_pct / 100)
    hi = spot * (1 + range_pct / 100)
    return df[(df["strike"] >= lo) & (df["strike"] <= hi)].copy()


def filter_strikes_n(
    df: pd.DataFrame,
    spot: float,
    n_strikes: int = 10,
) -> pd.DataFrame:
    """
    Keep N strikes above and N strikes below ATM.
    Better for thinly-traded stocks where ±15% includes empty strikes.
    """
    strikes = sorted(df["strike"].unique())
    if not strikes:
        return df
    atm_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - spot))
    lo_idx  = max(0, atm_idx - n_strikes)
    hi_idx  = min(len(strikes) - 1, atm_idx + n_strikes)
    keep    = set(strikes[lo_idx:hi_idx + 1])
    return df[df["strike"].isin(keep)].copy()


# ─── ATM strike ─────────────────────────────────────────────────────────────

def get_atm_strike(spot: float, interval: float) -> float:
    """Nearest strike to spot given interval."""
    return round(spot / interval) * interval


# ─── Straddle analytics ──────────────────────────────────────────────────────

def straddle_breakeven(
    spot: float,
    atm_call: float,
    atm_put: float,
) -> tuple[float, float]:
    """Return (lower_breakeven, upper_breakeven)."""
    straddle = atm_call + atm_put
    atm_approx = spot  # approximate
    return atm_approx - straddle, atm_approx + straddle


# ─── Number formatting ───────────────────────────────────────────────────────

def fmt_number(val: float) -> str:
    """Format large numbers with ₹ and Cr/L suffixes."""
    a = abs(val)
    if a >= 1e9:
        return f"₹{val/1e9:.2f}B"
    if a >= 1e7:
        return f"₹{val/1e7:.2f}Cr"
    if a >= 1e5:
        return f"₹{val/1e5:.2f}L"
    return f"₹{val:,.0f}"


def fmt_oi(oi: float) -> str:
    """Format OI in lacs."""
    if oi >= 1e7:
        return f"{oi/1e7:.2f}Cr"
    if oi >= 1e5:
        return f"{oi/1e5:.2f}L"
    return f"{int(oi):,}"


# ─── Moneyness label ────────────────────────────────────────────────────────

def moneyness_label(strike: float, spot: float) -> str:
    dist = (strike - spot) / spot * 100
    if abs(dist) < 1.0:
        return "ATM"
    elif dist > 0:
        return f"OTM +{dist:.1f}%"
    else:
        return f"ITM {dist:.1f}%"


# ─── Expiry countdown ───────────────────────────────────────────────────────

def days_to_expiry(expiry_str: str) -> int:
    try:
        exp = datetime.strptime(expiry_str, "%d-%b-%Y")
        return max(0, (exp - datetime.now()).days)
    except Exception:
        return 0


def expiry_tag(expiry_str: str) -> str:
    dte = days_to_expiry(expiry_str)
    if dte <= 3:
        return f"🔴 {dte}D (PIN RISK!)"
    elif dte <= 7:
        return f"🟠 {dte}D (Near expiry)"
    elif dte <= 14:
        return f"🟡 {dte}D"
    else:
        return f"🟢 {dte}D"


# ─── GEX regime label ────────────────────────────────────────────────────────

def gex_regime(net_gex: float) -> tuple[str, str]:
    """Return (label, color_hex)."""
    if net_gex > 5e7:
        return "🟢 Strong +GEX", "#22c55e"
    elif net_gex > 0:
        return "🟢 +GEX", "#86efac"
    elif net_gex > -5e7:
        return "🔴 -GEX", "#fca5a5"
    else:
        return "🔴 Strong -GEX", "#ef4444"


# ─── IV percentile ───────────────────────────────────────────────────────────

def iv_percentile_label(current_iv: float) -> str:
    """
    Rough IV context label.
    For stocks, typical ATM IV ranges:
      Low: <25%, Moderate: 25-40%, High: 40-60%, Extreme: >60%
    """
    if current_iv < 20:
        return "🟢 Very Low IV"
    elif current_iv < 30:
        return "🟢 Low IV"
    elif current_iv < 40:
        return "🟡 Moderate IV"
    elif current_iv < 55:
        return "🟠 High IV"
    else:
        return "🔴 Extreme IV"


# ─── PCR interpretation ─────────────────────────────────────────────────────

def pcr_signal(pcr: float) -> tuple[str, str]:
    """Return (signal_label, color)."""
    if pcr > 1.5:
        return "🟢 Extreme Put Buying — Contrarian BULLISH", "#22c55e"
    elif pcr > 1.2:
        return "🟢 Bearish Bias — Bull at dips", "#86efac"
    elif pcr > 0.8:
        return "🟡 Neutral / Balanced", "#fbbf24"
    elif pcr > 0.5:
        return "🔴 Bullish Bias — Put at rallies", "#fca5a5"
    else:
        return "🔴 Extreme Call Buying — Contrarian BEARISH", "#ef4444"
