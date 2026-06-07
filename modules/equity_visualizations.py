"""
modules/equity_visualizations.py
===================================
Plotly charts tailored for equity (stock) GEX analysis.

Charts provided:
1.  plot_equity_gex_profile()     — Horizontal bar GEX (MenthorQ-style for stocks)
2.  plot_equity_oi_chart()        — OI + volume side-by-side with OI change overlay
3.  plot_iv_skew_surface()        — IV smile with call/put skew + term structure
4.  plot_equity_greeks()          — Delta/gamma/theta profile across strikes
5.  plot_pin_risk_gauge()         — Max pain proximity gauge + pin risk score
6.  plot_oi_change_heatmap()      — OI change (fresh money) heatmap
7.  plot_gex_per_rupee()          — Dealer hedging pressure per ₹1 move
"""

from __future__ import annotations

from typing import Optional, Dict

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


_DARK_BG  = "#0A0F1E"
_PANEL_BG = "#111827"
_GREEN    = "#22c55e"
_RED      = "#ef4444"
_YELLOW   = "#eab308"
_BLUE     = "#60a5fa"
_PURPLE   = "#a78bfa"
_GRAY     = "#94a3b8"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Equity GEX Profile (horizontal bars, MenthorQ style)
# ─────────────────────────────────────────────────────────────────────────────

def plot_equity_gex_profile(
    gex_df: pd.DataFrame,
    spot_price: float,
    gamma_levels: dict,
    symbol: str,
    lot_size: int = 1,
) -> go.Figure:
    """
    Horizontal GEX bar chart for stock options.
    
    Key visual differences from index chart:
    • Bars labelled in ₹Cr or ₹L (normalized by lot size)
    • Four level lines: OI Call Wall, OI Put Wall, Gamma Flip, Max Pain
    • Moneyness column overlaid on y-axis
    • Cumulative GEX line uses secondary x-axis
    """
    df = gex_df.sort_values("strike").copy()
    strikes  = df["strike"].values.astype(float)
    net_gex  = df["total_gex"].values.astype(float)

    # Scale
    max_abs = max(abs(net_gex).max(), 1.0)
    if max_abs >= 1e7:
        divisor, unit = 1e7, "Cr"
    elif max_abs >= 1e5:
        divisor, unit = 1e5, "L"
    else:
        divisor, unit = 1.0, "₹"

    gex_sc  = net_gex / divisor
    cum_gex = np.cumsum(gex_sc)
    si       = float(np.median(np.diff(np.sort(strikes)))) if len(strikes) > 1 else 10.0

    # Bar colours
    bar_cols = []
    g_max = max(abs(gex_sc).max(), 0.01)
    for v in gex_sc:
        intensity = min(abs(v) / g_max, 1.0)
        if v >= 0:
            bar_cols.append(f"rgba(34,197,94,{0.35 + intensity*0.55:.2f})")
        else:
            r = int(200 + intensity * 45)
            g = int(50 * (1 - intensity * 0.8))
            bar_cols.append(f"rgba({r},{g},30,0.90)")

    fig = go.Figure()

    # Bars
    fig.add_trace(go.Bar(
        y=strikes, x=gex_sc, orientation="h",
        width=si * 0.75,
        marker=dict(color=bar_cols, line=dict(width=0)),
        name="Net GEX",
        hovertemplate=f"<b>₹%{{y:,.0f}}</b><br>Net GEX: %{{x:.3f}} {unit}<extra></extra>",
    ))

    # GEX profile line
    fig.add_trace(go.Scatter(
        y=strikes, x=gex_sc, mode="lines",
        line=dict(color="#fbbf24", width=2.2, shape="spline", smoothing=0.4),
        name="GEX Profile", hoverinfo="skip",
    ))

    # Cumulative GEX line
    c_max = max(abs(cum_gex).max(), 0.01)
    fig.add_trace(go.Scatter(
        y=strikes, x=cum_gex * (g_max / c_max),   # scale to same axis
        mode="lines",
        line=dict(color="#f97316", width=2.0, shape="spline", smoothing=0.4, dash="dot"),
        name="Cumul. GEX (scaled)",
        hovertemplate=f"Cumul. GEX: %{{x:.2f}} {unit}<extra></extra>",
    ))

    # Key levels
    kv = gamma_levels
    levels = [
        (kv.get("call_wall",      spot_price), _RED,    "solid", 2.2, "Call OI Wall"),
        (kv.get("put_wall",       spot_price), _GREEN,  "solid", 2.2, "Put OI Wall"),
        (kv.get("call_gex_wall",  spot_price), _RED,    "dash",  1.8, "Call Gamma Wall"),
        (kv.get("put_gex_wall",   spot_price), _GREEN,  "dash",  1.8, "Put Gamma Wall"),
        (kv.get("gamma_flip",     spot_price), _YELLOW, "dot",   1.5, "Gamma Flip"),
        (kv.get("max_pain",       spot_price), "#c084fc","dashdot",1.5, "Max Pain"),
        (spot_price,                           _BLUE,   "dot",   2.0, "Spot"),
    ]
    for price, color, dash, width, label in levels:
        fig.add_hline(
            y=price,
            line=dict(color=color, width=width, dash=dash),
            annotation_text=f"  ₹{price:,.0f} — {label}",
            annotation_position="top right" if price >= spot_price else "bottom right",
            annotation_font=dict(color=color, size=9, family="monospace"),
        )

    # Dot markers on left margin
    dot_x = -g_max * 1.3
    for price, color, _, _, label in levels:
        fig.add_trace(go.Scatter(
            x=[dot_x], y=[price], mode="markers",
            marker=dict(size=10, color=color, line=dict(width=1.5, color="#000")),
            name=label, showlegend=False,
            hovertemplate=f"<b>{label}</b><br>₹{price:,.2f}<extra></extra>",
        ))

    # Net regime text
    net_gex_total = float(gex_df["total_gex"].sum())
    regime = "Positive GEX ▲ (Dealers Stabilising)" if net_gex_total > 0 else "Negative GEX ▼ (Dealers Amplifying)"
    regime_col = _GREEN if net_gex_total > 0 else _RED

    fig.update_layout(
        title=dict(
            text=(
                f"<b>{symbol} — Equity GEX Profile</b><br>"
                f"<span style='font-size:11px;color:{_GRAY};'>"
                f"Spot ₹{spot_price:,.2f}  ·  Lot: {lot_size}  ·  "
                f"<span style='color:{regime_col};'>{regime}</span>"
                f"</span>"
            ),
            font=dict(size=14, color="white"), x=0.3,
        ),
        plot_bgcolor=_DARK_BG, paper_bgcolor=_PANEL_BG,
        template="plotly_dark", height=680,
        hovermode="y unified",
        xaxis=dict(
            title=f"Net GEX ({unit})",
            gridcolor="rgba(255,255,255,0.05)",
            zerolinecolor="rgba(255,255,255,0.3)",
            zerolinewidth=1.8,
            tickfont=dict(size=9.5, color=_GRAY),
        ),
        yaxis=dict(
            title="Strike Price (₹)",
            gridcolor="rgba(255,255,255,0.05)",
            tickfont=dict(size=9.5, color=_GRAY),
            dtick=si * 2,
        ),
        margin=dict(l=70, r=40, t=90, b=60),
        legend=dict(orientation="h", y=1.03, x=0.3,
                    bgcolor="rgba(0,0,0,0.4)",
                    font=dict(size=9.5, color=_GRAY)),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 2. OI + Volume Chart with OI Change overlay
# ─────────────────────────────────────────────────────────────────────────────

def plot_equity_oi_chart(
    gex_df: pd.DataFrame,
    spot_price: float,
    symbol: str,
) -> go.Figure:
    """
    3-panel chart:
    Row 1: Call OI (red) and Put OI (green) bars — shows walls
    Row 2: OI Change bars — shows where fresh money is flowing
    Row 3: Volume bars — call vs put activity
    """
    fig = make_subplots(
        rows=3, cols=1,
        subplot_titles=[
            "Open Interest by Strike",
            "OI Change (Fresh Money Flow)",
            "Volume (Call vs Put)"
        ],
        vertical_spacing=0.10,
        row_heights=[0.45, 0.28, 0.27],
    )

    strikes = gex_df["strike"].values

    # Row 1: OI
    for col_name, data, color, label in [
        ("call_oi", gex_df["call_oi"], "rgba(239,68,68,0.70)",  "Call OI"),
        ("put_oi",  gex_df["put_oi"],  "rgba(34,197,94,0.70)",  "Put OI"),
    ]:
        fig.add_trace(go.Bar(
            x=strikes, y=data, name=label,
            marker_color=color,
            hovertemplate=f"<b>Strike ₹%{{x}}</b><br>{label}: %{{y:,.0f}}<extra></extra>",
        ), row=1, col=1)

    # Row 2: OI Change
    if "call_oi_change" in gex_df.columns:
        c_chg = gex_df["call_oi_change"].fillna(0)
        p_chg = gex_df["put_oi_change"].fillna(0)
        c_cols = ["rgba(239,68,68,0.85)" if v > 0 else "rgba(239,68,68,0.30)" for v in c_chg]
        p_cols = ["rgba(34,197,94,0.85)"  if v > 0 else "rgba(34,197,94,0.30)"  for v in p_chg]
        fig.add_trace(go.Bar(
            x=strikes, y=c_chg, name="Call OI Δ",
            marker_color=c_cols,
            hovertemplate="<b>Strike ₹%{x}</b><br>Call OI Chg: %{y:,.0f}<extra></extra>",
        ), row=2, col=1)
        fig.add_trace(go.Bar(
            x=strikes, y=p_chg, name="Put OI Δ",
            marker_color=p_cols,
            hovertemplate="<b>Strike ₹%{x}</b><br>Put OI Chg: %{y:,.0f}<extra></extra>",
        ), row=2, col=1)

    # Row 3: Volume
    for data, color, label in [
        (gex_df["call_volume"], "rgba(239,68,68,0.55)", "Call Vol"),
        (gex_df["put_volume"],  "rgba(34,197,94,0.55)", "Put Vol"),
    ]:
        fig.add_trace(go.Bar(
            x=strikes, y=data, name=label, marker_color=color,
        ), row=3, col=1)

    # Spot line on all rows
    for row in [1, 2, 3]:
        fig.add_vline(
            x=spot_price, row=row, col=1,
            line=dict(color=_BLUE, width=1.5, dash="dash"),
        )

    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor=_DARK_BG, paper_bgcolor=_PANEL_BG,
        height=680, barmode="group", hovermode="x unified",
        title=dict(
            text=f"<b>{symbol} — OI & Volume Analysis</b>",
            font=dict(size=13, color="white"), x=0.5,
        ),
        margin=dict(l=60, r=40, t=60, b=40),
        legend=dict(orientation="h", y=1.02, bgcolor="rgba(0,0,0,0.3)",
                    font=dict(size=9.5, color=_GRAY)),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 3. IV Skew Surface
# ─────────────────────────────────────────────────────────────────────────────

def plot_iv_skew_surface(
    gex_df: pd.DataFrame,
    spot_price: float,
    symbol: str,
) -> go.Figure:
    """
    IV smile with put-call spread highlighted.
    Equity stocks tend to have strong left-tail put skew.
    Displays: call IV, put IV, IV spread (put - call).
    """
    fig = make_subplots(
        rows=2, cols=1,
        subplot_titles=["IV Smile", "Put-Call IV Spread (Skew)"],
        vertical_spacing=0.15, row_heights=[0.65, 0.35],
    )

    strikes  = gex_df["strike"].values
    call_ivs = gex_df["call_iv"].values
    put_ivs  = gex_df["put_iv"].values
    spread   = put_ivs - call_ivs

    fig.add_trace(go.Scatter(
        x=strikes, y=call_ivs,
        mode="lines+markers",
        name="Call IV",
        line=dict(color=_RED, width=2.2),
        marker=dict(size=5),
        hovertemplate="Strike ₹%{x}<br>Call IV: %{y:.2f}%<extra></extra>",
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=strikes, y=put_ivs,
        mode="lines+markers",
        name="Put IV",
        line=dict(color=_GREEN, width=2.2),
        marker=dict(size=5),
        hovertemplate="Strike ₹%{x}<br>Put IV: %{y:.2f}%<extra></extra>",
    ), row=1, col=1)

    # Fill between
    fig.add_trace(go.Scatter(
        x=np.concatenate([strikes, strikes[::-1]]),
        y=np.concatenate([call_ivs, put_ivs[::-1]]),
        fill="toself",
        fillcolor="rgba(148,163,184,0.08)",
        line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    ), row=1, col=1)

    # Spread bars
    spread_cols = [_GREEN if v > 0 else _RED for v in spread]
    fig.add_trace(go.Bar(
        x=strikes, y=spread,
        name="Put-Call IV Spread",
        marker_color=spread_cols,
        hovertemplate="Strike ₹%{x}<br>IV Spread: %{y:.2f}%<extra></extra>",
    ), row=2, col=1)
    fig.add_hline(y=0, row=2, col=1, line=dict(color=_GRAY, width=1, dash="dash"))

    for row in [1, 2]:
        fig.add_vline(
            x=spot_price, row=row, col=1,
            line=dict(color=_BLUE, width=1.5, dash="dot"),
            annotation_text=f"  Spot ₹{spot_price:,.0f}",
            annotation_position="top right",
            annotation_font=dict(color=_BLUE, size=9),
        )

    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor=_DARK_BG, paper_bgcolor=_PANEL_BG,
        height=520,
        title=dict(text=f"<b>{symbol} — IV Skew Surface</b>",
                   font=dict(size=13, color="white"), x=0.5),
        hovermode="x unified",
        margin=dict(l=60, r=40, t=60, b=40),
        legend=dict(orientation="h", y=1.02,
                    bgcolor="rgba(0,0,0,0.3)", font=dict(size=9.5, color=_GRAY)),
    )
    fig.update_yaxes(title_text="IV (%)", row=1, col=1)
    fig.update_yaxes(title_text="Put IV − Call IV (%)", row=2, col=1)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 4. Greeks profile
# ─────────────────────────────────────────────────────────────────────────────

def plot_equity_greeks_profile(
    gex_df: pd.DataFrame,
    spot_price: float,
    symbol: str,
    greek: str = "gamma",
) -> go.Figure:
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=[f"Call {greek.title()}", f"Put {greek.title()}"],
        horizontal_spacing=0.12,
    )
    strikes   = gex_df["strike"].values
    c_col_key = f"call_{greek}"
    p_col_key = f"put_{greek}"

    for col_idx, (key, color, label) in enumerate([
        (c_col_key, _RED,   f"Call {greek.title()}"),
        (p_col_key, _GREEN, f"Put {greek.title()}"),
    ], start=1):
        if key not in gex_df.columns:
            continue
        data = gex_df[key].values
        fig.add_trace(go.Bar(
            x=strikes, y=data,
            name=label, marker_color=color,
            hovertemplate=f"Strike ₹%{{x}}<br>{label}: %{{y:.6f}}<extra></extra>",
        ), row=1, col=col_idx)
        fig.add_vline(
            x=spot_price, row=1, col=col_idx,
            line=dict(color=_BLUE, width=1.5, dash="dash"),
        )

    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor=_DARK_BG, paper_bgcolor=_PANEL_BG,
        height=380, showlegend=False,
        title=dict(text=f"<b>{symbol} — {greek.title()} Profile</b>",
                   font=dict(size=13, color="white"), x=0.5),
        margin=dict(l=50, r=30, t=60, b=40),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 5. Pin Risk Gauge (Max Pain proximity)
# ─────────────────────────────────────────────────────────────────────────────

def plot_pin_risk_gauge(
    spot_price: float,
    max_pain: float,
    gamma_flip: float,
    symbol: str,
    days_to_expiry: int,
) -> go.Figure:
    """
    Gauge chart showing:
    • How close spot is to max pain (pin risk)
    • Whether we are above/below gamma flip
    Equity stocks have strong pin risk in final 5 days.
    """
    pain_dist_pct = abs(spot_price - max_pain) / spot_price * 100
    flip_dist_pct = (spot_price - gamma_flip) / spot_price * 100

    # Pin risk score: 0-100 (100 = spot exactly at max pain)
    pin_score = max(0, 100 - pain_dist_pct * 10)

    # Pin risk urgency depends on DTE
    dte_multiplier = max(0, 1 - days_to_expiry / 30) * 0.5 + 0.5
    effective_pin  = min(100, pin_score * dte_multiplier * 1.5)

    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{"type": "indicator"}, {"type": "indicator"}]],
        subplot_titles=["Pin Risk (Max Pain Proximity)", "Gamma Flip Position"],
    )

    # Pin risk gauge
    pin_color = "green" if effective_pin < 30 else "orange" if effective_pin < 65 else "red"
    fig.add_trace(go.Indicator(
        mode="gauge+number+delta",
        value=round(effective_pin, 1),
        title=dict(text=f"Pin Score<br><span style='font-size:11px;color:#94a3b8;'>"
                        f"Spot ₹{spot_price:,.0f} → MaxPain ₹{max_pain:,.0f}</span>"),
        delta=dict(reference=50, increasing=dict(color="red"), decreasing=dict(color="green")),
        gauge=dict(
            axis=dict(range=[0, 100], tickwidth=1, tickcolor="white"),
            bar=dict(color=pin_color, thickness=0.25),
            bgcolor="rgba(30,41,59,0.8)",
            borderwidth=1, bordercolor=_GRAY,
            steps=[
                dict(range=[0, 30],  color="rgba(34,197,94,0.15)"),
                dict(range=[30, 65], color="rgba(234,179,8,0.15)"),
                dict(range=[65, 100],color="rgba(239,68,68,0.15)"),
            ],
            threshold=dict(line=dict(color="white", width=2), thickness=0.7, value=effective_pin),
        ),
        number=dict(font=dict(size=40), suffix="%"),
    ), row=1, col=1)

    # Gamma flip indicator
    flip_val  = round(flip_dist_pct, 2)
    flip_mode = "Spot ABOVE Flip (Stable)" if flip_val > 0 else "Spot BELOW Flip (Volatile)"
    flip_col  = "#22c55e" if flip_val > 0 else "#ef4444"
    fig.add_trace(go.Indicator(
        mode="number+delta",
        value=flip_val,
        number=dict(suffix="%", font=dict(size=42, color=flip_col)),
        title=dict(text=f"{flip_mode}<br><span style='font-size:11px;color:#94a3b8;'>"
                        f"Flip ₹{gamma_flip:,.0f} | DTE: {days_to_expiry}d</span>"),
        delta=dict(reference=0),
    ), row=1, col=2)

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=_PANEL_BG,
        height=300,
        title=dict(text=f"<b>{symbol} — Pin Risk & Gamma Regime</b>",
                   font=dict(size=13, color="white"), x=0.5),
        margin=dict(l=30, r=30, t=80, b=20),
        font=dict(color="white"),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 6. GEX per ₹1 move (dealer rehedging pressure)
# ─────────────────────────────────────────────────────────────────────────────

def plot_gex_per_rupee(
    gex_df: pd.DataFrame,
    spot_price: float,
    symbol: str,
) -> go.Figure:
    """
    Shows how many ₹ worth of stock dealers must buy/sell per ₹1 move.
    This is the most operationally intuitive GEX metric for stocks.
    
    Formula: gex_pr = (call_gex_pr + put_gex_pr) where
        call_gex_pr = -gamma × call_OI × lot × spot
        put_gex_pr  = +gamma × put_OI  × lot × spot
    """
    if "call_gex_pr" not in gex_df.columns:
        # fallback: use total_gex normalized
        gex_df = gex_df.copy()
        gex_df["gex_pr_combined"] = gex_df["total_gex"] / (spot_price * 0.01)
    else:
        gex_df = gex_df.copy()
        gex_df["gex_pr_combined"] = gex_df["call_gex_pr"] + gex_df["put_gex_pr"]

    strikes = gex_df["strike"].values
    vals    = gex_df["gex_pr_combined"].values

    # Scale
    max_abs = max(abs(vals).max(), 1.0)
    if max_abs >= 1e7:
        div, unit = 1e7, "Cr"
    elif max_abs >= 1e5:
        div, unit = 1e5, "L"
    else:
        div, unit = 1.0, "₹"

    scaled  = vals / div
    colors  = [_GREEN if v >= 0 else _RED for v in scaled]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=strikes, y=scaled,
        name=f"GEX per ₹1 move ({unit})",
        marker_color=colors,
        hovertemplate=f"Strike ₹%{{x}}<br>Dealer hedge/₹1: %{{y:.3f}} {unit}<extra></extra>",
    ))

    fig.add_vline(
        x=spot_price,
        line=dict(color=_BLUE, width=2, dash="dash"),
        annotation_text=f"  Spot ₹{spot_price:,.0f}",
        annotation_font=dict(color=_BLUE, size=10),
    )
    fig.add_hline(y=0, line=dict(color=_GRAY, width=1))

    # Zero-GEX label
    abs_max_idx = int(np.argmax(np.abs(scaled)))
    peak_strike = float(strikes[abs_max_idx])
    fig.add_vline(
        x=peak_strike,
        line=dict(color=_YELLOW, width=1.5, dash="dot"),
        annotation_text=f"  Peak: ₹{peak_strike:,.0f}",
        annotation_font=dict(color=_YELLOW, size=9),
    )

    fig.update_layout(
        title=dict(
            text=f"<b>{symbol} — Dealer Rehedge Pressure per ₹1 Move</b><br>"
                 f"<span style='font-size:10px;color:{_GRAY};'>"
                 f"Green = Dealers BUY ₹1 up (stabilising) | "
                 f"Red = Dealers SELL ₹1 down (amplifying)</span>",
            font=dict(size=13, color="white"), x=0.4,
        ),
        template="plotly_dark",
        plot_bgcolor=_DARK_BG, paper_bgcolor=_PANEL_BG,
        height=380,
        hovermode="x unified",
        xaxis=dict(title="Strike (₹)", gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(title=f"Dealer Hedge ({unit} / ₹1 move)",
                   gridcolor="rgba(255,255,255,0.05)",
                   zerolinecolor="rgba(255,255,255,0.3)"),
        margin=dict(l=60, r=40, t=80, b=40),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 7. Positioning matrix (like index tab1 grid but for equity)
# ─────────────────────────────────────────────────────────────────────────────

def build_equity_matrix(
    gex_df: pd.DataFrame,
    spot_price: float,
    gamma_levels: dict,
    si: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build formatted + styled positioning matrix for equity options.

    Returns (display_matrix_fmt, display_matrix_numeric)
    """
    from .equity_utils import get_atm_strike

    matrix = gex_df.sort_values("strike").copy()
    matrix["strike"] = matrix["strike"].astype(int)
    matrix["pcr"] = matrix.apply(
        lambda r: r["put_oi"] / r["call_oi"] if r["call_oi"] > 0 else 0.0, axis=1
    )

    net_gex_total = float(gex_df["total_gex"].sum())
    total_call_oi = float(gamma_levels.get("total_call_oi", 0))
    total_put_oi  = float(gamma_levels.get("total_put_oi", 0))
    total_pcr     = total_put_oi / total_call_oi if total_call_oi > 0 else 0.0

    # ── GEX scale: abs() across full column (call_gex values are negative) ────
    gex_max_abs = max(
        gex_df["call_gex"].abs().max(),
        gex_df["put_gex"].abs().max(),
    )
    div_gex  = 1e7 if gex_max_abs >= 1e7 else 1e5
    gex_unit = "Cr" if div_gex == 1e7 else "L"
    oi_unit  = "L" if total_call_oi > 1e5 else ""
    oi_div   = 1e5 if total_call_oi > 1e5 else 1

    # ── Put Δ probability row ────────────────────────────────────────────────
    # Put delta is negative (0 to -1). abs(put_delta) × 100 = market-implied
    # probability that the stock closes BELOW that strike at expiry.
    # e.g. put_delta = -0.28  →  28% chance of expiring below this strike.
    # Lower probability = price very unlikely to breach that level = strong OTM floor.
    put_prob = (matrix["put_delta"].abs() * 100).round(1)

    def _prob_label(p: float) -> str:
        if p >= 60:
            return f"{p:.1f}%  ← ITM / very likely below"
        elif p >= 45:
            return f"{p:.1f}%  ← near ATM"
        elif p >= 30:
            return f"{p:.1f}%  ← moderate, possible"
        elif p >= 15:
            return f"{p:.1f}%  ← low, unlikely below"
        else:
            return f"{p:.1f}%  ← very low, strong OTM floor"

    _PROB_ROW = "Put Δ Prob% ↓ expiry"

    grid = {
        "Strike Price":           matrix["strike"].tolist(),
        f"Call GEX ({gex_unit})": (matrix["call_gex"] / div_gex).tolist(),
        f"Put GEX ({gex_unit})":  (matrix["put_gex"]  / div_gex).tolist(),
        f"Net GEX ({gex_unit})":  ((matrix["call_gex"] + matrix["put_gex"]) / div_gex).tolist(),
        f"Call OI ({oi_unit})":   (matrix["call_oi"] / oi_div).tolist(),
        f"Put OI ({oi_unit})":    (matrix["put_oi"]  / oi_div).tolist(),
        "PCR":                    matrix["pcr"].tolist(),
        "Call IV%":               matrix["call_iv"].tolist(),
        "Put IV%":                matrix["put_iv"].tolist(),
        "Call LTP":               matrix["call_ltp"].tolist(),
        "Put LTP":                matrix["put_ltp"].tolist(),
        "Call Δ":                 matrix["call_delta"].tolist(),
        "Put Δ":                  matrix["put_delta"].tolist(),
        _PROB_ROW:                put_prob.tolist(),   # raw floats for ranking
    }

    dm = pd.DataFrame(grid).set_index("Strike Price").T

    totals = [
        gex_df["call_gex"].sum() / div_gex,   # Call GEX
        gex_df["put_gex"].sum()  / div_gex,   # Put GEX
        net_gex_total / div_gex,              # Net GEX
        total_call_oi / oi_div,               # Call OI
        total_put_oi  / oi_div,               # Put OI
        total_pcr,                            # PCR
        pd.NA, pd.NA,                         # Call IV%, Put IV%
        pd.NA, pd.NA,                         # Call LTP, Put LTP
        pd.NA, pd.NA,                         # Call Δ, Put Δ
        pd.NA,                                # Put Δ Prob% — no chain total
    ]
    dm["TOTAL"] = totals

    # ── Format: probability row gets descriptive label, rest get 2dp ─────────
    def _fmt_cell(row_label, x):
        if pd.isna(x):
            return "—"
        if row_label == _PROB_ROW:
            return _prob_label(float(x))
        return f"{x:.2f}"

    dm_fmt = pd.DataFrame(
        {col: {row: _fmt_cell(row, dm.loc[row, col]) for row in dm.index}
         for col in dm.columns}
    )

    return dm_fmt, dm
