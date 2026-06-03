"""
modules/equity_gex_calculator.py
==================================
Equity (Stock) GEX & Greeks Calculator

WHY EQUITY GEX IS DIFFERENT FROM INDEX GEX:
────────────────────────────────────────────────────────────────────────────
1.  Lot sizes are HUGE per-stock relative to price.
    Index: NIFTY lot=65 × ₹24,500 = ₹15.9L notional
    Stock: RELIANCE lot=250 × ₹1,400 = ₹3.5L notional
    → Absolute GEX numbers are not comparable across stocks.

2.  GEX normalisation: We express GEX in 3 forms:
    (a) Raw GEX (₹): gamma × OI × spot² × lot_size × 0.01
    (b) GEX per ₹1 move: how much dealers must trade per ₹1 spot move
    (c) GEX as % ADV: GEX / 30-day avg daily volume (impact measure)

3.  Stock option OI is in CONTRACTS (not lots). Multiply by lot_size for shares.

4.  Dealer positioning interpretation:
    +GEX: Dealers long gamma → they BUY on dips, SELL on rallies (dampening)
    -GEX: Dealers short gamma → they SELL on dips, BUY on rallies (amplifying)
    For stocks, -GEX is more common (stocks trend more than indices).

5.  Max Pain for stocks is more "magnetic" — stock pinning at expiry is
    well-documented because the floating supply is thinner than index.

6.  Gamma-weighted strikes called "charm" are more important for weekly
    (which don't exist for stocks), so for monthly equity options we track
    time-decay (theta) and vega more carefully.

Public API:
───────────
    from modules.equity_gex_calculator import (
        calculate_all_greeks_equity,
        calculate_equity_gex,
        find_equity_gamma_levels,
        calculate_max_pain_equity,
        calculate_oi_change_analysis,
    )
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm


# ─── Core Greek engine ──────────────────────────────────────────────────────

def calculate_all_greeks_equity(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "call",
) -> dict:
    """
    Full Black-Scholes Greeks for equity options.
    Same math as index but returns additional per-share metrics.
    """
    if T <= 0 or sigma <= 0:
        itm = max((S - K) if option_type == "call" else (K - S), 0.0)
        return dict(
            delta=1.0 if (option_type == "call" and S > K) else 0.0,
            gamma=0.0, vega=0.0, theta=0.0, rho=0.0,
            theo_price=itm, iv=sigma * 100,
            moneyness_pct=round((S - K) / S * 100, 3),
        )
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)

        gamma = float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))
        vega  = float(S * norm.pdf(d1) * np.sqrt(T) / 100)

        if option_type == "call":
            delta = float(norm.cdf(d1))
            price = float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
            theta = float((-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
                          - r * K * np.exp(-r * T) * norm.cdf(d2)) / 365)
            rho   = float(K * T * np.exp(-r * T) * norm.cdf(d2) / 100)
        else:
            delta = float(norm.cdf(d1) - 1)
            price = float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))
            theta = float((-S * norm.pdf(d1) * sigma / (2 * np.sqrt(T))
                          + r * K * np.exp(-r * T) * norm.cdf(-d2)) / 365)
            rho   = float(-K * T * np.exp(-r * T) * norm.cdf(-d2) / 100)

        return dict(
            delta=round(delta, 5),
            gamma=round(gamma, 7),
            vega=round(vega, 5),
            theta=round(theta, 4),
            rho=round(rho, 5),
            theo_price=round(price, 2),
            iv=round(sigma * 100, 3),
            moneyness_pct=round((S - K) / S * 100, 3),
        )
    except Exception:
        return dict(delta=0, gamma=0, vega=0, theta=0, rho=0,
                    theo_price=0, iv=0, moneyness_pct=0)


# ─── Main GEX calculator ─────────────────────────────────────────────────────

def calculate_equity_gex(
    df: pd.DataFrame,
    spot_price: float,
    expiry_date_str: str,
    risk_free_rate: float = 0.07,
    lot_size: int = 1,
) -> pd.DataFrame:
    """
    Calculate GEX with full Greeks for each strike.

    GEX formula (equity):
        Call GEX = -gamma × call_OI × lot_size × spot² × 0.01
        Put  GEX = +gamma × put_OI  × lot_size × spot² × 0.01

    The lot_size factor makes GEX correctly represent total share-equivalent
    exposure that dealers must hedge.

    Args:
        df            : Raw option chain DataFrame (CE + PE rows)
        spot_price    : Current stock price
        expiry_date_str: "DD-MMM-YYYY"
        risk_free_rate: Risk-free rate (default 7%)
        lot_size      : Stock lot size (contracts × lot_size = shares)

    Returns:
        DataFrame indexed by strike with all GEX, DEX, Greeks columns.
    """
    from modules.equity_utils import calculate_tte

    T = calculate_tte(expiry_date_str)
    records: list[dict] = []

    for strike in sorted(df["strike"].unique()):
        sub  = df[df["strike"] == strike]
        call = sub[sub["type"] == "CE"]
        put  = sub[sub["type"] == "PE"]

        def _sum(part, col):
            return float(part[col].sum()) if not part.empty else 0.0

        call_oi  = _sum(call, "oi")
        put_oi   = _sum(put,  "oi")
        call_vol = _sum(call, "volume")
        put_vol  = _sum(put,  "volume")
        call_ltp = float(call["ltp"].mean()) if not call.empty else 0.0
        put_ltp  = float(put["ltp"].mean())  if not put.empty  else 0.0
        call_oi_chg = _sum(call, "oi_change")
        put_oi_chg  = _sum(put,  "oi_change")

        # IV: use raw chain IV if available, else compute
        raw_c_iv = float(call["iv"].mean()) / 100 if not call.empty and call["iv"].mean() > 0 else 0.20
        raw_p_iv = float(put["iv"].mean())  / 100 if not put.empty  and put["iv"].mean()  > 0 else 0.20

        cg = calculate_all_greeks_equity(spot_price, strike, T, risk_free_rate, raw_c_iv, "call")
        pg = calculate_all_greeks_equity(spot_price, strike, T, risk_free_rate, raw_p_iv, "put")

        # ── GEX (₹ exposure per 1% spot move) ────────────────────────────────
        call_gex = -cg["gamma"] * call_oi * lot_size * spot_price * spot_price * 0.01
        put_gex  =  pg["gamma"] * put_oi  * lot_size * spot_price * spot_price * 0.01
        total_gex = call_gex + put_gex

        # ── GEX per ₹1 move (simpler: gamma × OI × lot × spot) ──────────────
        call_gex_per_rupee = -cg["gamma"] * call_oi * lot_size * spot_price
        put_gex_per_rupee  =  pg["gamma"] * put_oi  * lot_size * spot_price

        # ── DEX (delta exposure: shares worth of delta) ────────────────────
        call_dex = -cg["delta"] * call_oi * lot_size * spot_price
        put_dex  = -pg["delta"] * put_oi  * lot_size * spot_price

        # ── Vega/Theta exposure ────────────────────────────────────────────
        call_vex  = cg["vega"] * call_oi * lot_size
        put_vex   = pg["vega"] * put_oi  * lot_size
        call_tex  = cg["theta"] * call_oi * lot_size
        put_tex   = pg["theta"] * put_oi  * lot_size

        # ── Strike character ───────────────────────────────────────────────
        dist_pct = (strike - spot_price) / spot_price * 100
        if abs(dist_pct) < 1.5:
            moneyness = "ATM"
        elif dist_pct > 0:
            moneyness = f"OTM Call +{dist_pct:.1f}%"
        else:
            moneyness = f"ITM Call {dist_pct:.1f}%"

        records.append({
            "strike":         strike,
            "moneyness":      moneyness,
            "dist_pct":       round(dist_pct, 2),
            # OI & Volume
            "call_oi":        call_oi,
            "put_oi":         put_oi,
            "call_volume":    call_vol,
            "put_volume":     put_vol,
            "call_oi_change": call_oi_chg,
            "put_oi_change":  put_oi_chg,
            # Premiums
            "call_ltp":       call_ltp,
            "put_ltp":        put_ltp,
            # IV
            "call_iv":        cg["iv"],
            "put_iv":         pg["iv"],
            # Greeks
            "call_delta":     cg["delta"],   "put_delta":     pg["delta"],
            "call_gamma":     cg["gamma"],   "put_gamma":     pg["gamma"],
            "call_vega":      cg["vega"],    "put_vega":      pg["vega"],
            "call_theta":     cg["theta"],   "put_theta":     pg["theta"],
            "call_rho":       cg["rho"],     "put_rho":       pg["rho"],
            "call_theo":      cg["theo_price"], "put_theo":   pg["theo_price"],
            # GEX
            "call_gex":       call_gex,
            "put_gex":        put_gex,
            "total_gex":      total_gex,
            "call_gex_pr":    call_gex_per_rupee,
            "put_gex_pr":     put_gex_per_rupee,
            # DEX / VEX / TEX
            "call_dex":       call_dex,
            "put_dex":        put_dex,
            "total_dex":      call_dex + put_dex,
            "call_vex":       call_vex,
            "put_vex":        put_vex,
            "total_vex":      call_vex + put_vex,
            "call_tex":       call_tex,
            "put_tex":        put_tex,
            "total_tex":      call_tex + put_tex,
        })

    gex_df = pd.DataFrame(records).sort_values("strike").reset_index(drop=True)

    # Cumulative GEX (low → high strike sweep)
    gex_df["cumul_gex"] = gex_df["total_gex"].cumsum()

    return gex_df


# ─── Delta recalc on spot move (fast path) ──────────────────────────────────

def recalculate_gex_delta(
    cached_df: pd.DataFrame,
    new_spot: float,
    expiry_date_str: str,
    risk_free_rate: float,
    lot_size: int,
) -> pd.DataFrame:
    """
    Fast GEX update on spot change — reuses cached IV, only recalculates
    spot-sensitive Greeks (delta, gamma, theo).
    """
    from modules.equity_utils import calculate_tte
    T = calculate_tte(expiry_date_str)
    df = cached_df.copy()

    c_ivs = (df["call_iv"] / 100).values
    p_ivs = (df["put_iv"] / 100).values

    for i, (c_iv, p_iv) in enumerate(zip(c_ivs, p_ivs)):
        strike = float(df.loc[i, "strike"])
        cg = calculate_all_greeks_equity(new_spot, strike, T, risk_free_rate, c_iv, "call")
        pg = calculate_all_greeks_equity(new_spot, strike, T, risk_free_rate, p_iv, "put")

        c_oi = float(df.loc[i, "call_oi"])
        p_oi = float(df.loc[i, "put_oi"])

        call_gex = -cg["gamma"] * c_oi * lot_size * new_spot * new_spot * 0.01
        put_gex  =  pg["gamma"] * p_oi * lot_size * new_spot * new_spot * 0.01

        df.loc[i, "call_delta"] = cg["delta"]
        df.loc[i, "put_delta"]  = pg["delta"]
        df.loc[i, "call_gamma"] = cg["gamma"]
        df.loc[i, "put_gamma"]  = pg["gamma"]
        df.loc[i, "call_theo"]  = cg["theo_price"]
        df.loc[i, "put_theo"]   = pg["theo_price"]
        df.loc[i, "call_gex"]   = call_gex
        df.loc[i, "put_gex"]    = put_gex
        df.loc[i, "total_gex"]  = call_gex + put_gex
        df.loc[i, "call_dex"]   = -cg["delta"] * c_oi * lot_size * new_spot
        df.loc[i, "put_dex"]    = -pg["delta"] * p_oi * lot_size * new_spot
        df.loc[i, "total_dex"]  = df.loc[i, "call_dex"] + df.loc[i, "put_dex"]

    df["cumul_gex"] = df["total_gex"].cumsum()
    return df.sort_values("strike")


# ─── Gamma level detection ───────────────────────────────────────────────────

def find_equity_gamma_levels(
    gex_df: pd.DataFrame,
    spot_price: float,
    lot_size: int = 1,
) -> dict:
    """
    Extract key levels from the GEX DataFrame.
    Returns a richer dict than the index version — includes equity-specific
    metrics like pin risk, put-call skew, and lot-adjusted exposure.
    """
    if gex_df.empty:
        return {}

    # ── OI walls ──────────────────────────────────────────────────────────
    max_call_oi_idx = gex_df["call_oi"].idxmax()
    max_put_oi_idx  = gex_df["put_oi"].idxmax()
    call_wall = float(gex_df.loc[max_call_oi_idx, "strike"])
    put_wall  = float(gex_df.loc[max_put_oi_idx,  "strike"])

    # ── Gamma walls (by GEX magnitude) ─────────────────────────────────
    call_gex_wall = float(gex_df.loc[gex_df["call_gex"].idxmin(), "strike"])
    put_gex_wall  = float(gex_df.loc[gex_df["put_gex"].idxmax(),  "strike"])

    # ── Gamma flip (zero crossing of cumulative GEX) ───────────────────
    cum = gex_df["cumul_gex"].values
    strikes = gex_df["strike"].values
    flip_idx = int(np.argmin(np.abs(cum)))
    gamma_flip = float(strikes[flip_idx])

    # More precise zero-crossing interpolation
    for i in range(len(cum) - 1):
        if cum[i] * cum[i + 1] < 0:
            w = abs(cum[i]) / (abs(cum[i]) + abs(cum[i + 1]) + 1e-9)
            gamma_flip = float(strikes[i]) + (float(strikes[i+1]) - float(strikes[i])) * w
            break

    # ── Max Pain ──────────────────────────────────────────────────────
    max_pain = _calculate_max_pain(gex_df)

    # ── PCR ────────────────────────────────────────────────────────────
    total_call_oi = float(gex_df["call_oi"].sum())
    total_put_oi  = float(gex_df["put_oi"].sum())
    pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 1.0

    total_call_vol = float(gex_df["call_volume"].sum())
    total_put_vol  = float(gex_df["put_volume"].sum())
    volume_pcr = total_put_vol / total_call_vol if total_call_vol > 0 else 1.0

    # ── ATM metrics ────────────────────────────────────────────────────
    atm_idx = (gex_df["strike"] - spot_price).abs().idxmin()
    atm     = gex_df.loc[atm_idx]
    atm_straddle = float(atm["call_ltp"]) + float(atm["put_ltp"])
    iv_skew = float(atm["put_iv"]) - float(atm["call_iv"])

    # ── Pin risk score (how strongly spot is attracted to max pain) ────
    pain_dist = abs(max_pain - spot_price) / spot_price
    pin_risk  = max(0, round(1.0 - pain_dist * 20, 2))  # 1.0 = exact pin

    # ── Net regime ────────────────────────────────────────────────────
    net_gex   = float(gex_df["total_gex"].sum())
    net_dex   = float(gex_df["total_dex"].sum())

    # ── OI change direction (fresh money flow) ─────────────────────────
    net_oi_change_calls = float(gex_df["call_oi_change"].sum()) if "call_oi_change" in gex_df.columns else 0.0
    net_oi_change_puts  = float(gex_df["put_oi_change"].sum())  if "put_oi_change"  in gex_df.columns else 0.0

    return {
        # OI-based walls
        "call_wall":          call_wall,
        "put_wall":           put_wall,
        "max_call_oi_strike": call_wall,   # alias for compatibility
        "max_put_oi_strike":  put_wall,
        # Gamma-based walls
        "call_gex_wall":      call_gex_wall,
        "put_gex_wall":       put_gex_wall,
        # Regime levels
        "gamma_flip":         round(gamma_flip, 2),
        "max_pain":           max_pain,
        # Aggregate OI
        "total_call_oi":      total_call_oi,
        "total_put_oi":       total_put_oi,
        "total_call_volume":  total_call_vol,
        "total_put_volume":   total_put_vol,
        # PCR
        "pcr":                round(pcr, 4),
        "volume_pcr":         round(volume_pcr, 4),
        # ATM metrics
        "atm_strike":         float(atm["strike"]),
        "atm_straddle":       round(atm_straddle, 2),
        "atm_call_iv":        float(atm["call_iv"]),
        "atm_put_iv":         float(atm["put_iv"]),
        "iv_skew":            round(iv_skew, 2),
        # GEX totals
        "total_gex":          net_gex,
        "total_dex":          net_dex,
        # Pin risk
        "pin_risk":           pin_risk,
        # OI flow
        "net_oi_change_calls": net_oi_change_calls,
        "net_oi_change_puts":  net_oi_change_puts,
    }


# ─── Max Pain ───────────────────────────────────────────────────────────────

def _calculate_max_pain(gex_df: pd.DataFrame) -> float:
    """
    Max Pain = strike where total option writer loss is MINIMUM.
    For stocks, this is often a very strong gravitational pull near expiry.
    """
    strikes = gex_df["strike"].values
    if len(strikes) == 0:
        return 0.0

    min_pain = float("inf")
    max_pain_strike = float(strikes[len(strikes) // 2])

    for test_strike in strikes:
        pain = 0.0
        for _, row in gex_df.iterrows():
            s = row["strike"]
            # Call holders lose when test_strike < strike (calls expire worthless)
            if test_strike > s:
                pain += float(row["call_oi"]) * (test_strike - s)
            # Put holders lose when test_strike > strike
            if test_strike < s:
                pain += float(row["put_oi"]) * (s - test_strike)
        if pain < min_pain:
            min_pain = pain
            max_pain_strike = float(test_strike)

    return max_pain_strike


# ─── OI Change analysis ──────────────────────────────────────────────────────

def calculate_oi_change_analysis(gex_df: pd.DataFrame, spot_price: float) -> dict:
    """
    Analyse OI change patterns to determine FRESH vs SHORT COVERING.

    Logic:
    • Call OI UP + price UP   = Fresh LONG CALL buildup (bullish)
    • Call OI UP + price DOWN = Short CALL writing (bearish hedge)
    • Put OI UP + price DOWN  = Fresh LONG PUT (bearish)
    • Put OI UP + price UP    = Short PUT writing (bullish hedge)
    """
    if "call_oi_change" not in gex_df.columns:
        return {}

    # Strikes gaining OI fastest
    top_call_oi_gainers = (gex_df.nlargest(3, "call_oi_change")
                           [["strike", "call_oi_change", "call_ltp"]].to_dict("records"))
    top_put_oi_gainers  = (gex_df.nlargest(3, "put_oi_change")
                           [["strike", "put_oi_change", "put_ltp"]].to_dict("records"))

    # IV term structure: check if ATM IV > OTM IV (normal skew)
    atm_mask = (gex_df["strike"] - spot_price).abs() <= gex_df["strike"].std() * 0.1
    otm_call_mask = gex_df["strike"] > spot_price * 1.05
    otm_put_mask  = gex_df["strike"] < spot_price * 0.95

    atm_iv   = float(gex_df[atm_mask]["call_iv"].mean()) if atm_mask.any() else 20.0
    otm_c_iv = float(gex_df[otm_call_mask]["call_iv"].mean()) if otm_call_mask.any() else 20.0
    otm_p_iv = float(gex_df[otm_put_mask]["put_iv"].mean())  if otm_put_mask.any()  else 20.0

    call_skew_pct = round((otm_c_iv - atm_iv) / atm_iv * 100, 2) if atm_iv > 0 else 0
    put_skew_pct  = round((otm_p_iv - atm_iv) / atm_iv * 100, 2) if atm_iv > 0 else 0

    return {
        "top_call_oi_gainers":  top_call_oi_gainers,
        "top_put_oi_gainers":   top_put_oi_gainers,
        "atm_iv":               round(atm_iv, 2),
        "otm_call_iv":          round(otm_c_iv, 2),
        "otm_put_iv":           round(otm_p_iv, 2),
        "call_skew_pct":        call_skew_pct,
        "put_skew_pct":         put_skew_pct,
        "skew_type": (
            "Put Skew (bearish)" if put_skew_pct > call_skew_pct + 2
            else "Call Skew (bullish)" if call_skew_pct > put_skew_pct + 2
            else "Symmetric (neutral)"
        ),
    }


# ─── GEX normalisation helpers ───────────────────────────────────────────────

def format_gex_equity(value: float) -> str:
    """Format equity GEX value with appropriate scale."""
    a = abs(value)
    if a >= 1e9:
        return f"₹{value/1e9:.2f}B"
    if a >= 1e7:
        return f"₹{value/1e7:.2f}Cr"
    if a >= 1e5:
        return f"₹{value/1e5:.2f}L"
    return f"₹{value:,.0f}"


def gex_per_rupee(gex_df: pd.DataFrame) -> pd.DataFrame:
    """
    Return GEX normalised as ₹ dealer hedge per ₹1 spot move.
    This is the most intuitive measure: 'if stock moves ₹1, dealers
    must buy/sell THIS MANY RUPEES worth of stock to rehedge.'
    """
    df = gex_df.copy()
    df["gex_per_re"] = (df["call_gex_pr"] + df["put_gex_pr"]) if "call_gex_pr" in df.columns else df["total_gex"]
    return df
