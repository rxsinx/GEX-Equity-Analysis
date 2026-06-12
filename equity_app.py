"""
Equity GEX Terminal — NSE Stock Monthly Options
=================================================
Standalone Streamlit app for Gamma Exposure analysis of NSE-listed
F&O equities (monthly options only).

KEY DIFFERENCES FROM INDEX GEX TERMINAL:
─────────────────────────────────────────────────────────────────────────
1.  Symbol selector  : Stock picker with NIFTY50 / NIFTY100 / Custom presets
2.  Expiry           : Monthly only (last Thursday) — no weekly for stocks
3.  GEX units        : Per-lot adjusted, expressed in ₹Cr or ₹L
4.  GEX/₹1 view      : Dealer rehedge pressure per ₹1 stock move
5.  Pin risk gauge   : Max Pain proximity score + DTE-weighted urgency
6.  IV Skew          : Put-call IV spread (equity stocks have strong put skew)
7.  OI Change        : Fresh money tracking (call writing vs put buying)
8.  Multi-stock scan : ATM straddle scanner across F&O universe
9.  Stock-specific   : Lot size, strike interval auto-detected per symbol
10. No BSE/BFO       : All equity options live in NFO — simpler routing
"""

import streamlit as st
import pandas as pd
import pytz
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

from modules.equity_data_fetcher import (
    EquityKiteManager,
    EquityKiteError, EquityAuthError, EquityDataError,
    get_fo_universe, get_equity_expiries,
    NIFTY50_STOCKS, NIFTY100_STOCKS, POPULAR_STOCKS,
)
from modules.equity_gex_calculator import (
    calculate_equity_gex,
    find_equity_gamma_levels,
    recalculate_gex_delta,
    calculate_oi_change_analysis,
    format_gex_equity,
)
from modules.equity_utils import (
    calculate_tte, filter_strikes_pct, filter_strikes_n,
    get_atm_strike, fmt_number, fmt_oi,
    moneyness_label, days_to_expiry, expiry_tag,
    gex_regime, iv_percentile_label, pcr_signal,
)
from modules.equity_visualizations import (
    plot_equity_gex_profile,
    plot_equity_oi_chart,
    plot_iv_skew_surface,
    plot_equity_greeks_profile,
    plot_pin_risk_gauge,
    plot_gex_per_rupee,
    build_equity_matrix,
    plot_gex_oi_clustered,
)

IST = pytz.timezone("Asia/Kolkata")

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Equity GEX Terminal",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container{padding-top:0.4rem !important;padding-bottom:0.2rem !important}
.eq-header{
  font-size:1.55rem;font-weight:bold;text-align:center;
  background:linear-gradient(90deg,#22c55e,#3b82f6,#a78bfa);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  margin:0;padding:0;line-height:1.2}
.eq-subheader{text-align:center;color:#64748b;font-size:0.76rem;margin:0 0 0.2rem 0}
hr{margin:0.2rem 0 !important;border-color:rgba(49,51,63,0.25)!important}
[data-testid="stMetricValue"]{font-size:1.0rem!important;line-height:1.25!important}
[data-testid="stMetricLabel"]{font-size:0.68rem!important;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
[data-testid="stMetricDelta"]{font-size:0.62rem!important}
div[data-testid="metric-container"]{padding:0.1rem 0.35rem!important}
.stAlert{padding:0.25rem 0.6rem!important;font-size:0.76rem!important}

/* live pulse */
.live-dot{display:inline-block;width:9px;height:9px;background:#22c55e;
  border-radius:50%;margin-right:5px;animation:pulse 1.4s infinite}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.25;transform:scale(0.7)}}

.live-bar{
  display:flex;align-items:center;justify-content:space-between;
  background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.25);
  border-radius:8px;padding:0.35rem 1rem;margin-bottom:0.4rem;
  font-size:0.78rem;font-family:monospace}
.live-bar-off{
  display:flex;align-items:center;justify-content:space-between;
  background:rgba(100,116,139,0.08);border:1px solid rgba(100,116,139,0.2);
  border-radius:8px;padding:0.35rem 1rem;margin-bottom:0.4rem;
  font-size:0.78rem;font-family:monospace;color:#64748b}
.ticker{font-size:1.1rem;font-weight:700;font-family:monospace;
  padding:0.15rem 0.5rem;border-radius:4px}
.tick-up{color:#22c55e}.tick-dn{color:#ef4444}.tick-flat{color:#94a3b8}

.stTabs [data-baseweb="tab"]{height:34px;background:#f0f2f6;
  border-radius:5px 5px 0 0;padding:4px 13px;font-weight:600;font-size:0.82rem}
.stTabs [aria-selected="true"]{background:linear-gradient(135deg,#22c55e,#3b82f6);color:white}

/* Equity-specific badge */
.eq-badge{
  display:inline-block;background:rgba(34,197,94,0.15);
  border:1px solid rgba(34,197,94,0.35);border-radius:4px;
  padding:2px 8px;font-size:0.72rem;font-family:monospace;color:#22c55e}
.monthly-badge{
  display:inline-block;background:rgba(96,165,250,0.15);
  border:1px solid rgba(96,165,250,0.35);border-radius:4px;
  padding:2px 8px;font-size:0.72rem;font-family:monospace;color:#60a5fa}
</style>
""", unsafe_allow_html=True)


# ── Session state init ────────────────────────────────────────────────────────
_defaults = {
    "eq_data_loaded":       False,
    "eq_options_df":        None,
    "eq_gex_df":            None,
    "eq_gamma_levels":      None,
    "eq_spot":              None,
    "eq_prev_spot":         None,
    "eq_ohlc":              None,
    "eq_symbol":            "RELIANCE",
    "eq_expiry":            None,
    "eq_lot_size":          1,
    "eq_strike_interval":   10.0,
    "eq_strike_range_pct":  15.0,
    "eq_risk_free_rate":    0.07,
    "eq_kite_mgr":          None,
    "eq_kite_auth":         False,
    "eq_live_mode":         False,
    "eq_live_error":        None,
    "eq_chain_error":       None,
    "eq_last_update":       None,
    "eq_last_spot_update":  None,
    "eq_tick_count":        0,
    "eq_chain_count":       0,
    "eq_chain_refresh_s":   300,
    "eq_scan_results":      None,
    "eq_scan_symbols":      [],
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Live engine ───────────────────────────────────────────────────────────────
def _live_engine():
    km  = st.session_state.eq_kite_mgr
    sym = st.session_state.eq_symbol
    exp = st.session_state.eq_expiry
    rfr = st.session_state.eq_risk_free_rate
    lot = st.session_state.eq_lot_size
    sr  = st.session_state.eq_strike_range_pct

    # Fast spot tick
    try:
        new_spot = km.get_spot_ltp(sym)
        ohlc     = km.get_spot_ohlc(sym)
        if new_spot and st.session_state.eq_gex_df is not None:
            old_spot = st.session_state.eq_spot
            if new_spot != old_spot:
                gdf = recalculate_gex_delta(
                    st.session_state.eq_gex_df, new_spot, exp, rfr, lot)
                gl  = find_equity_gamma_levels(gdf, new_spot, lot)
                st.session_state.update({
                    "eq_prev_spot":       old_spot,
                    "eq_spot":            new_spot,
                    "eq_ohlc":            ohlc,
                    "eq_gex_df":          gdf,
                    "eq_gamma_levels":    gl,
                    "eq_last_spot_update": datetime.now(IST),
                    "eq_tick_count":      st.session_state.eq_tick_count + 1,
                })
    except Exception as exc:
        st.session_state.eq_live_error = str(exc)

    # Slow chain refresh
    now = datetime.now(IST)
    last = st.session_state.eq_last_update
    age  = (now - last).total_seconds() if last else 9999
    ivl  = st.session_state.eq_chain_refresh_s

    if age >= ivl:
        try:
            raw_df, spot = km.get_option_chain(sym, exp, rfr)
            df_f  = filter_strikes_pct(raw_df, spot, sr)
            gdf   = calculate_equity_gex(df_f, spot, exp, rfr, lot)
            gl    = find_equity_gamma_levels(gdf, spot, lot)
            st.session_state.update({
                "eq_options_df":       raw_df,
                "eq_gex_df":           gdf,
                "eq_gamma_levels":     gl,
                "eq_spot":             spot,
                "eq_last_update":      now,
                "eq_last_spot_update": now,
                "eq_chain_error":      None,
                "eq_chain_count":      st.session_state.eq_chain_count + 1,
            })
        except EquityAuthError as e:
            st.session_state.eq_chain_error = f"Session expired: {e}"
            st.session_state.eq_live_mode   = False
        except Exception as e:
            st.session_state.eq_chain_error = str(e)


# Trigger live engine
if (st.session_state.eq_live_mode
        and st.session_state.eq_kite_auth
        and st.session_state.eq_data_loaded):
    st_autorefresh(interval=5_000, limit=None, key="eq_live_ar")
    _live_engine()


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<p class="eq-header">📈 Equity GEX Terminal — NSE Stock Options</p>',
            unsafe_allow_html=True)
st.markdown(
    '<p class="eq-subheader">'
    'Monthly F&O · Gamma Exposure · Pin Risk · IV Skew · Dealer Positioning'
    '</p>',
    unsafe_allow_html=True)
st.markdown(
    '<div style="text-align:center;margin-bottom:4px;">'
    '<span class="monthly-badge">📅 MONTHLY ONLY — All equity options expire last Tuesday</span>'
    '&nbsp;&nbsp;'
    '<span class="eq-badge">🏦 NFO Exchange</span>'
    '</div>',
    unsafe_allow_html=True,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.header("⚙️ Equity GEX Config")

    # ── Live Engine ───────────────────────────────────────────────────────────
    st.subheader("⚡ Live Engine")
    can_live = st.session_state.eq_kite_auth and st.session_state.eq_data_loaded

    if st.session_state.eq_live_mode:
        if st.button("🔴 STOP LIVE", type="primary", use_container_width=True):
            st.session_state.eq_live_mode = False
            st.rerun()
        st.caption(f"✅ {st.session_state.eq_tick_count} ticks · "
                   f"{st.session_state.eq_chain_count} chain fetches")
        c_ivl = st.slider("Chain refresh (s)", 60, 600,
                          st.session_state.eq_chain_refresh_s, 30)
        st.session_state.eq_chain_refresh_s = c_ivl
        if st.session_state.eq_live_error:
            st.error(f"⚠️ Spot: {st.session_state.eq_live_error}")
        if st.session_state.eq_chain_error:
            st.warning(f"⚠️ Chain: {st.session_state.eq_chain_error}")
    else:
        if st.button("🟢 GO LIVE", type="primary", use_container_width=True,
                     disabled=not can_live,
                     help="Fetch chain first, then go live"):
            st.session_state.update({
                "eq_live_mode":   True,
                "eq_tick_count":  0,
                "eq_chain_count": 0,
                "eq_live_error":  None,
                "eq_chain_error": None,
            })
            st.rerun()

    st.markdown("---")

    # ── Kite Auth ─────────────────────────────────────────────────────────────
    st.subheader("🔐 Kite Connect")
    if not st.session_state.eq_kite_auth:
        api_key    = st.text_input("API Key",    type="password", key="eq_api_key")
        api_secret = st.text_input("API Secret", type="password", key="eq_api_secret")
        if api_key and api_secret:
            km_tmp = EquityKiteManager(api_key, api_secret)
            st.link_button("🔗 Login to Kite", km_tmp.get_login_url(),
                           type="primary", use_container_width=True)
        req_token = st.text_input("Request Token:", key="eq_req_token")
        if req_token and st.button("✅ Generate Session", type="primary",
                                    use_container_width=True, key="eq_gen_sess"):
            if api_key and api_secret:
                km_tmp = EquityKiteManager(api_key, api_secret)
                ok, msg = km_tmp.set_access_token(req_token)
                if ok:
                    st.session_state.eq_kite_mgr  = km_tmp
                    st.session_state.eq_kite_auth = True
                    st.success(f"✅ {msg}")
                    st.rerun()
                else:
                    st.error(f"❌ {msg}")
    else:
        st.success("✅ Kite Connected")
        if st.button("Disconnect", use_container_width=True, key="eq_disconnect"):
            st.session_state.update({
                "eq_kite_auth": False, "eq_kite_mgr": None,
                "eq_live_mode": False,
            })
            st.rerun()

        with st.expander("🔍 Diagnostics", expanded=False):
            test_sym = st.text_input("Test symbol:", "RELIANCE", key="eq_test_sym")
            if st.button("▶ Run Test", key="eq_run_test"):
                km = st.session_state.eq_kite_mgr
                if km:
                    with st.spinner("Testing…"):
                        res = km.test_connection(test_sym)
                    for step, info in res.items():
                        icon = "✅" if info["ok"] else "❌"
                        (st.success if info["ok"] else st.error)(
                            f"{icon} **{info['label']}** — {info['msg']}")
            if st.button("🗑 Clear Cache", key="eq_clear_cache"):
                if st.session_state.eq_kite_mgr:
                    st.session_state.eq_kite_mgr.invalidate_cache()
                    st.success("NFO cache cleared.")

    st.markdown("---")
    km = st.session_state.eq_kite_mgr

    # ── Stock Selection ───────────────────────────────────────────────────────
    st.subheader("📈 Stock Selection")

    preset = st.radio("Universe", ["NIFTY50", "NIFTY100", "Custom"],
                      horizontal=True, key="eq_preset")

    if preset == "Custom":
        custom_sym = st.text_input(
            "Enter symbol (NSE F&O):",
            value=st.session_state.eq_symbol,
            key="eq_custom_sym",
            help="E.g. RELIANCE, HDFC, TCS, INFY"
        ).upper().strip()
        symbol = custom_sym if custom_sym else "RELIANCE"
    else:
        universe = NIFTY50_STOCKS if preset == "NIFTY50" else NIFTY100_STOCKS
        symbol   = st.selectbox(
            "Select Stock",
            sorted(universe),
            index=sorted(universe).index(st.session_state.eq_symbol)
                  if st.session_state.eq_symbol in universe else 0,
            key="eq_sym_select",
        )

    st.session_state.eq_symbol = symbol

    # Auto-detect lot size and strike interval
    if km:
        try:
            lot = km.get_lot_size(symbol)
            si  = km.get_strike_interval(symbol)
            src = "🔗 Kite"
        except Exception:
            lot = 1; si = 10.0; src = "⚠️ fallback"
    else:
        lot = 1; si = 10.0; src = "⚠️ no Kite"

    st.session_state.eq_lot_size        = lot
    st.session_state.eq_strike_interval = si
    st.caption(f"Lot: **{lot}** · Strike step: **₹{si:.0f}** · {src}")

    # ── Expiry ────────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📅 Expiry (Monthly Only)")

    if km:
        try:
            expiries = km.get_available_expiries(symbol)
        except Exception:
            expiries = get_equity_expiries(6)
    else:
        expiries = get_equity_expiries(6)

    if not expiries:
        expiries = get_equity_expiries(6)

    expiry = st.selectbox(
        "Expiry", expiries,
        help="All stock options: Last Thursday of month",
        key="eq_expiry_sel",
    )
    st.session_state.eq_expiry = expiry

    dte = days_to_expiry(expiry)
    st.caption(f"DTE: {expiry_tag(expiry)}")
    if dte <= 5:
        st.warning("⚠️ Near expiry: high pin risk! Max Pain very powerful now.")

    # ── Parameters ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📍 Analysis Parameters")

    strike_range = st.slider(
        "Strike Range (%)", 5, 25,
        int(st.session_state.eq_strike_range_pct), 1,
        key="eq_sr_slider",
        help="±% from spot to include. Wider for volatile stocks.",
    )
    st.session_state.eq_strike_range_pct = float(strike_range)

    rfr = st.number_input(
        "Risk-Free Rate (%)", 0.0, 15.0,
        round(st.session_state.eq_risk_free_rate * 100, 1), 0.1,
        key="eq_rfr_input",
    ) / 100
    st.session_state.eq_risk_free_rate = rfr

    # ── Spot refresh ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("💹 Spot Price")
    sc1, sc2 = st.columns(2)

    with sc1:
        if st.button("🔄 Refresh", use_container_width=True,
                     disabled=st.session_state.eq_live_mode, key="eq_refresh_spot"):
            if km:
                with st.spinner("Fetching LTP…"):
                    try:
                        new_spot = km.get_spot_ltp(symbol)
                        ohlc     = km.get_spot_ohlc(symbol)
                        st.session_state.update({
                            "eq_prev_spot":       st.session_state.eq_spot,
                            "eq_spot":            new_spot,
                            "eq_ohlc":            ohlc,
                            "eq_last_spot_update": datetime.now(IST),
                        })
                        if st.session_state.eq_data_loaded and st.session_state.eq_gex_df is not None:
                            gdf = recalculate_gex_delta(
                                st.session_state.eq_gex_df, new_spot,
                                expiry, rfr, lot)
                            st.session_state.update({
                                "eq_gex_df":       gdf,
                                "eq_gamma_levels": find_equity_gamma_levels(gdf, new_spot, lot),
                            })
                        st.success(f"₹{new_spot:,.2f}")
                    except Exception as e:
                        st.error(str(e))
    with sc2:
        if st.session_state.eq_live_mode:
            st.markdown("🟢 **AUTO**")
        elif st.session_state.eq_spot:
            st.metric("LTP", f"₹{st.session_state.eq_spot:,.2f}")

    # ── Fetch option chain ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔄 Option Chain")

    if st.button("📥 Fetch Chain", type="primary",
                 use_container_width=True, key="eq_fetch_chain"):
        if not km:
            st.error("Connect Kite first.")
        else:
            with st.spinner(f"Fetching {symbol} chain for {expiry}…"):
                try:
                    raw_df, spot = km.get_option_chain(symbol, expiry, rfr)
                    df_f = filter_strikes_pct(raw_df, spot, strike_range)
                    if df_f.empty:
                        df_f = filter_strikes_pct(raw_df, spot, 20)
                        st.warning("Widened to ±20%.")
                    gdf  = calculate_equity_gex(df_f, spot, expiry, rfr, lot)
                    gl   = find_equity_gamma_levels(gdf, spot, lot)
                    ohlc = km.get_spot_ohlc(symbol)
                    now  = datetime.now(IST)
                    st.session_state.update({
                        "eq_options_df":       raw_df,
                        "eq_gex_df":           gdf,
                        "eq_gamma_levels":     gl,
                        "eq_spot":             spot,
                        "eq_prev_spot":        ohlc["close"] if ohlc and ohlc.get("close") else spot,
                        "eq_ohlc":             ohlc,
                        "eq_data_loaded":      True,
                        "eq_last_update":      now,
                        "eq_last_spot_update": now,
                        "eq_lot_size":         km.get_lot_size(symbol),
                        "eq_strike_interval":  km.get_strike_interval(symbol, expiry),
                        "eq_tick_count":       0,
                        "eq_chain_count":      0,
                        "eq_live_error":       None,
                        "eq_chain_error":      None,
                    })
                    st.success(f"✅ {len(df_f['strike'].unique())} strikes · ₹{spot:,.2f}")
                except EquityAuthError as e:
                    st.error(f"🔐 Session expired: {e}")
                except EquityDataError as e:
                    st.error(f"📊 Data error: {e}")
                except Exception as e:
                    st.error(f"Error: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ═══════════════════════════════════════════════════════════════════════════════
if st.session_state.eq_data_loaded and st.session_state.eq_gex_df is not None:

    spot_price   = st.session_state.eq_spot
    prev_spot    = st.session_state.eq_prev_spot or spot_price
    gex_df       = st.session_state.eq_gex_df
    gamma_levels = st.session_state.eq_gamma_levels
    lot_size     = st.session_state.eq_lot_size
    si           = st.session_state.eq_strike_interval
    symbol       = st.session_state.eq_symbol
    expiry       = st.session_state.eq_expiry
    ohlc         = st.session_state.eq_ohlc or {}
    dte          = days_to_expiry(expiry)

    # Pull key levels
    call_wall    = gamma_levels.get("call_wall",    spot_price)
    put_wall     = gamma_levels.get("put_wall",     spot_price)
    gamma_flip   = gamma_levels.get("gamma_flip",   spot_price)
    max_pain     = gamma_levels.get("max_pain",     spot_price)
    net_gex      = gamma_levels.get("total_gex",    0)
    pcr          = gamma_levels.get("pcr",          1.0)
    vol_pcr      = gamma_levels.get("volume_pcr",   1.0)
    atm_straddle = gamma_levels.get("atm_straddle", 0)
    iv_skew      = gamma_levels.get("iv_skew",      0)
    atm_iv       = gamma_levels.get("atm_call_iv",  20.0)
    pin_risk     = gamma_levels.get("pin_risk",     0)

    # ── Live status bar ───────────────────────────────────────────────────────
    tick_delta     = spot_price - prev_spot
    day_close      = ohlc.get("close") or prev_spot
    spot_delta     = spot_price - day_close
    spot_delta_pct = (spot_delta / day_close * 100) if day_close else 0

    tick_arrow = "▲" if tick_delta > 0 else "▼" if tick_delta < 0 else "●"
    tick_class = "tick-up" if tick_delta > 0 else "tick-dn" if tick_delta < 0 else "tick-flat"

    now_ist     = datetime.now(IST)
    chain_age_s = int((now_ist - st.session_state.eq_last_update).total_seconds()) \
                  if st.session_state.eq_last_update else 0
    spot_age_s  = int((now_ist - st.session_state.eq_last_spot_update).total_seconds()) \
                  if st.session_state.eq_last_spot_update else 0

    if st.session_state.eq_live_mode:
        bar_class = "live-bar"
        mode_tag  = '<span class="live-dot"></span><b>LIVE</b>'
    else:
        bar_class = "live-bar-off"
        mode_tag  = "⏸ PAUSED"

    regime_lbl, regime_col = gex_regime(net_gex)

    st.markdown(f"""
<div class="{bar_class}">
  <span>{mode_tag}&nbsp;&nbsp;
    <span class="ticker {tick_class}">
      {symbol} &nbsp; ₹{spot_price:,.2f} &nbsp; {tick_arrow} {abs(spot_delta):,.2f}
      ({spot_delta_pct:+.2f}%)
    </span>
    &nbsp;&nbsp;
    <span style="color:{regime_col};font-size:0.80rem;font-weight:bold;">{regime_lbl}</span>
  </span>
  <span>
    Spot: <b>{spot_age_s}s</b> &nbsp;|&nbsp;
    Chain: <b>{chain_age_s}s</b> &nbsp;|&nbsp;
    DTE: <b>{expiry_tag(expiry)}</b> &nbsp;|&nbsp;
    Lot: <b>{lot_size}</b>
  </span>
</div>""", unsafe_allow_html=True)

    if st.session_state.eq_live_error:
        st.error(f"⚠️ Spot error: {st.session_state.eq_live_error}", icon="⚡")
    if st.session_state.eq_chain_error:
        st.warning(f"⚠️ Chain error: {st.session_state.eq_chain_error}")

    # ── Metric rows ───────────────────────────────────────────────────────────
    ohlc_data = st.session_state.eq_ohlc or {}
    m1,m2,m3,m4,m5,m6,m7,m8,m9,m10 = st.columns(10)

    spot_delta_disp = f"{spot_delta:+.1f}" if spot_delta != 0 else None
    m1.metric("💰 Spot",        f"₹{spot_price:,.2f}", delta=spot_delta_disp)
    m2.metric("Open",           f"₹{ohlc_data['open']:,.1f}"  if ohlc_data else "—")
    m3.metric("High",           f"₹{ohlc_data['high']:,.1f}"  if ohlc_data else "—")
    m4.metric("Low",            f"₹{ohlc_data['low']:,.1f}"   if ohlc_data else "—")
    m5.metric("Prev Close",     f"₹{ohlc_data['close']:,.1f}" if ohlc_data else "—")
    m6.metric("📊 PCR",         f"{pcr:.2f}", help="OI Put/Call ratio")
    m7.metric("🎯 Max Pain",    f"₹{max_pain:,.0f}",
              delta=f"{max_pain - spot_price:+.0f}")
    m8.metric("🔄 Gamma Flip",  f"₹{gamma_flip:,.0f}",
              delta=f"{gamma_flip - spot_price:+.0f}")
    m9.metric("📐 ATM Straddle", f"₹{atm_straddle:.1f}",
              help=f"{atm_straddle/spot_price*100:.1f}% of spot")
    m10.metric("📌 IV Skew",    f"{iv_skew:+.2f}%",
               help="Put IV − Call IV at ATM. +ve = fear premium")

    n1,n2,n3,n4,n5,n6,n7,n8 = st.columns(8)
    n1.metric("🔴 Call GEX",      fmt_number(gex_df['call_gex'].sum()))
    n2.metric("🟢 Put GEX",       fmt_number(gex_df['put_gex'].sum()))
    n3.metric("💹 Net GEX",       fmt_number(net_gex))
    n4.metric("🚧 Call OI Wall",  f"₹{call_wall:,.0f}",
              delta=f"{call_wall - spot_price:+.0f}")
    n5.metric("🛡️ Put OI Wall",   f"₹{put_wall:,.0f}",
              delta=f"{put_wall - spot_price:+.0f}")
    n6.metric("📦 Lot Size",       str(lot_size))
    n7.metric("📉 Total Call OI",  fmt_oi(gamma_levels.get("total_call_oi", 0)))
    n8.metric("📈 Total Put OI",   fmt_oi(gamma_levels.get("total_put_oi", 0)))

    # ── Tabs ──────────────────────────────────────────────────────────────────
    st.markdown("---")
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "📊GEX Profile",
        "🔬Matrix",
        "📋OI & Volume",
        "⚡GEX / ₹1 Move",
        "🎯Pin Risk",
        "📐IV Skew",
        "📊Greeks",
        "🔍Scanner",
    ])

    # ── TAB 1: GEX Profile ────────────────────────────────────────────────────
    with tab1:
        st.subheader(f"Gamma Exposure Profile — {symbol}")

        col_a, col_b = st.columns([3, 1])
        with col_a:
            st.plotly_chart(
                plot_equity_gex_profile(gex_df, spot_price, gamma_levels, symbol, lot_size),
                use_container_width=True,
            )
        with col_b:
            st.markdown("### 🔑 Key Levels")
            st.markdown(f"""
| Level | Price | Distance |
|:------|------:|---------:|
| 🔴 Call Wall  | ₹{call_wall:,.0f}  | {call_wall-spot_price:+.0f} |
| 🟢 Put Wall   | ₹{put_wall:,.0f}   | {put_wall-spot_price:+.0f}  |
| 🔄 Gamma Flip | ₹{gamma_flip:,.0f} | {gamma_flip-spot_price:+.0f}|
| 🎯 Max Pain   | ₹{max_pain:,.0f}   | {max_pain-spot_price:+.0f}  |
| 💹 Spot       | ₹{spot_price:,.2f} | — |
""")

            
        st.markdown("### 📝 GEX Interpretation Guide for Equity")
        st.markdown(f"""
**{symbol}** GEX Analysis — Understanding Dealer Positioning

**Net GEX: {fmt_number(net_gex)}**  
{'🟢 **Positive GEX** — Market makers are net long gamma. They buy on dips and sell on rallies, creating a stabilising effect. Price tends to mean-revert between the Call Wall and Put Wall.' if net_gex > 0 else '🔴 **Negative GEX** — Market makers are net short gamma. They chase moves — selling on dips and buying on rallies, which AMPLIFIES price moves. Breakouts are more likely to sustain.'}

**Key Wall Mechanics:**
- **Call OI Wall (₹{call_wall:,.0f})**: Maximum call open interest — where call writers have the most skin in the game. Dealers short calls here must sell into rallies, capping upside.
- **Put OI Wall (₹{put_wall:,.0f})**: Maximum put open interest — where put writers have maximum exposure. Dealers short puts here must buy on dips, creating a floor.
- **Gamma Flip (₹{gamma_flip:,.0f})**: The regime boundary. Above = dealers stabilise, Below = dealers amplify moves.
- **Max Pain (₹{max_pain:,.0f})**: Strike where total option buyer losses are maximum. Strong gravitational pull near expiry (DTE: {dte} days).
- **ATM Straddle Cost: ₹{atm_straddle:.1f}** — Market implies this is the expected daily/weekly move range.
""")

    # ── TAB 6: IV Skew ────────────────────────────────────────────────────────
    with tab6:
        st.subheader(f"Implied Volatility Skew — {symbol}")

        st.plotly_chart(
            plot_iv_skew_surface(gex_df, spot_price, symbol),
            use_container_width=True,
        )

        st.markdown("---")
        c1, c2, c3 = st.columns(3)

        oi_analysis = calculate_oi_change_analysis(gex_df, spot_price)
        atm_iv_val  = oi_analysis.get("atm_iv", 20.0)
        otm_c_iv    = oi_analysis.get("otm_call_iv", 20.0)
        otm_p_iv    = oi_analysis.get("otm_put_iv", 20.0)
        call_skew   = oi_analysis.get("call_skew_pct", 0)
        put_skew    = oi_analysis.get("put_skew_pct", 0)
        skew_type   = oi_analysis.get("skew_type", "Neutral")

        c1.metric("ATM IV", f"{atm_iv_val:.2f}%", help="At-The-Money implied volatility")
        c2.metric("OTM Call IV", f"{otm_c_iv:.2f}%",
                  delta=f"{call_skew:+.1f}% vs ATM")
        c3.metric("OTM Put IV", f"{otm_p_iv:.2f}%",
                  delta=f"{put_skew:+.1f}% vs ATM")

        st.info(f"**Skew Type:** {skew_type}")
        st.markdown(f"""
**Skew Interpretation for {symbol}:**

Equity stocks almost always have **put skew** (OTM puts more expensive than OTM calls) because:
1. Institutions buy protective puts (crash insurance) → puts bid up
2. Retail sells OTM calls (covered call income) → calls depressed
3. Net result: Put IV > Call IV, especially far OTM

**{symbol} ATM IV: {atm_iv_val:.1f}%** — {iv_percentile_label(atm_iv_val)}  
This implies a ±**{atm_iv_val/100 * spot_price / 16:.1f}**₹ daily expected move (IV / √252).

**Skew trading ideas:**
- If Put Skew is very high (>20% above ATM IV) → Sell put spreads (collect rich premium)
- If Call Skew is unusual (above put skew) → Bullish reversal signal (covered call territory)
- If IV is extreme (>50%) → Sell straddle / iron condor (vol will revert to mean)
""")

    # ── TAB 3: OI & Volume ────────────────────────────────────────────────────
    with tab3:
        st.subheader(f"Open Interest & Volume — {symbol}")
        st.plotly_chart(
            plot_equity_oi_chart(gex_df, spot_price, symbol),
            use_container_width=True,
        )

        st.markdown("---")
        st.markdown("### 🔍 Fresh Money Flow (OI Change)")

        oi_analysis = calculate_oi_change_analysis(gex_df, spot_price)

        if oi_analysis.get("top_call_oi_gainers"):
            fc1, fc2 = st.columns(2)
            with fc1:
                st.markdown("#### 📞 Top Call OI Gainers")
                for item in oi_analysis["top_call_oi_gainers"]:
                    st.markdown(
                        f"- Strike **₹{item['strike']:,.0f}** — "
                        f"OI Δ: `{item['call_oi_change']:+,.0f}` "
                        f"(LTP: ₹{item['call_ltp']:.2f})"
                    )
            with fc2:
                st.markdown("#### 📉 Top Put OI Gainers")
                for item in oi_analysis["top_put_oi_gainers"]:
                    st.markdown(
                        f"- Strike **₹{item['strike']:,.0f}** — "
                        f"OI Δ: `{item['put_oi_change']:+,.0f}` "
                        f"(LTP: ₹{item['put_ltp']:.2f})"
                    )
        else:
            st.info("OI Change data not available in this chain fetch.")

        st.markdown("---")
        vol1, vol2, vol3 = st.columns(3)
        total_c_vol = gamma_levels.get("total_call_volume", 0)
        total_p_vol = gamma_levels.get("total_put_volume", 0)
        vol1.metric("Total Call Volume", f"{total_c_vol:,.0f}")
        vol2.metric("Total Put Volume",  f"{total_p_vol:,.0f}")
        vol3.metric("Volume PCR",        f"{vol_pcr:.3f}")

    # ── TAB 4: GEX per ₹1 ────────────────────────────────────────────────────
    with tab4:
        st.subheader(f"Dealer Rehedge Pressure — {symbol}")

        st.info("""
**What is GEX per ₹1 Move?**  
For every ₹1 the stock moves, dealers must buy or sell shares to maintain delta neutrality.  
🟢 Green bar = dealers BUY on that move (stabilising)  
🔴 Red bar = dealers SELL on that move (amplifying)  
Peak bars show the strikes where dealer activity will be heaviest.
""")

        st.plotly_chart(
            plot_gex_per_rupee(gex_df, spot_price, symbol),
            use_container_width=True,
        )

        st.markdown("---")
        st.markdown("### 📊 Dealer Flow Summary")
        total_c_gex_pr = gex_df["call_gex_pr"].sum() if "call_gex_pr" in gex_df.columns else 0
        total_p_gex_pr = gex_df["put_gex_pr"].sum()  if "put_gex_pr"  in gex_df.columns else 0
        net_pr = total_c_gex_pr + total_p_gex_pr

        g1, g2, g3 = st.columns(3)
        g1.metric("Call Dealer Pressure/₹1",  fmt_number(total_c_gex_pr))
        g2.metric("Put Dealer Pressure/₹1",   fmt_number(total_p_gex_pr))
        g3.metric("Net Dealer Pressure/₹1",   fmt_number(net_pr),
                  help="Net ₹ of stock dealers trade per ₹1 underlying move")

        st.markdown(f"""
**Interpretation for {symbol}:**

Net dealer rehedge pressure = **{fmt_number(net_pr)} per ₹1 move**

{'🟢 Dealers are NET BUYERS on upside: Each ₹1 rally triggers ₹' + fmt_number(abs(net_pr)) + ' of buying. This dampens upside — rallies are slower.' if net_pr > 0 else '🔴 Dealers are NET SELLERS on downside: Each ₹1 drop triggers ₹' + fmt_number(abs(net_pr)) + ' of selling. This amplifies downside — drops are faster.'}

The strike with the **largest absolute bar** is where dealer activity will be maximum. This creates a "magnetic" effect — price often pauses or reverses at these levels.
""")

    # ── TAB 5: Pin Risk ───────────────────────────────────────────────────────
    with tab5:
        st.subheader(f"Max Pain & Pin Risk — {symbol}")

        st.plotly_chart(
            plot_pin_risk_gauge(spot_price, max_pain, gamma_flip, symbol, dte),
            use_container_width=True,
        )

        st.markdown("---")
        pg1, pg2, pg3, pg4 = st.columns(4)
        pg1.metric("🎯 Max Pain",     f"₹{max_pain:,.0f}",
                   delta=f"{max_pain - spot_price:+.0f}",
                   help="Strike minimizing total option buyer profit")
        pg2.metric("📏 Distance",     f"{abs(max_pain - spot_price) / spot_price * 100:.2f}%",
                   help="How far spot is from max pain")
        pg3.metric("📅 DTE",          f"{dte} days", help="Days to expiry")
        pg4.metric("🔴 Pin Risk",     f"{pin_risk:.0%}",
                   help="Probability of price pinning near max pain")

        st.markdown(f"""
### 🎯 Max Pain Theory for Equity Options

**Max Pain Strike: ₹{max_pain:,.0f}**  
Current Spot: **₹{spot_price:,.2f}** ({abs(max_pain-spot_price)/spot_price*100:.2f}% from max pain)

**How Max Pain Works for Stocks:**
Option writers (typically institutions/market makers) are short both calls and puts.  
At expiry, they profit most when spot closes at the strike where BUYER losses are maximum — the Max Pain level.

Because writers have directional hedging power (large positions), stocks tend to GRAVITATE toward Max Pain in the final week before expiry.

**{symbol} Pin Risk Assessment:**
- **DTE: {dte} days** — {'⚠️ HIGH PIN RISK: In final week, max pain gravity is strongest!' if dte <= 7 else '🟡 MODERATE: Max pain starts pulling 2 weeks out.' if dte <= 14 else '🟢 LOW: Too early for max pain gravity to dominate.'}
- **Distance from Max Pain: {abs(max_pain-spot_price)/spot_price*100:.2f}%** — {'Very close! Pin likely.' if abs(max_pain-spot_price)/spot_price < 0.01 else 'Moderate distance — still possible but less certain.' if abs(max_pain-spot_price)/spot_price < 0.03 else 'Far from max pain — pin unlikely unless large moves bring spot closer.'}

**Gamma Flip: ₹{gamma_flip:,.0f}**  
Spot is **{'ABOVE' if spot_price > gamma_flip else 'BELOW'}** the flip point.  
{'Stable regime: dealers support prices, making violent moves harder.' if spot_price > gamma_flip else 'Volatile regime: dealers amplify moves, making the journey to max pain faster (and choppier).'}

**Strategy Ideas:**
- If within ₹{int(si * 2)} of Max Pain with <5 DTE: Short Straddle at Max Pain strike
- If far from Max Pain: Directional spread in max pain direction
- Always pair with stop loss 1 strike interval away from entry
""")

    # ── TAB 2: Positioning Matrix ─────────────────────────────────────────────
    with tab2:
        st.subheader(f"Strike-by-Strike Positioning Matrix — {symbol}")
        # 1. Map and parse your dataframe columns for the clustered chart
        chart_df = gex_df.copy()
        chart_df['Strike'] = chart_df['strike']
        chart_df['Call_GEX_Cr'] = chart_df['call_gex'] / 1e7
        chart_df['Put_GEX_Cr'] = chart_df['put_gex'] / 1e7
        chart_df['Call_OI_Lacs'] = chart_df['call_oi'] / 1e5
        chart_df['Put_OI_Lacs'] = chart_df['put_oi'] / 1e5
    
        
        # 2. Render the new clustered Call/Put GEX and OI chart at the top of Tab 2            
        fig_oi_clustered = plot_gex_oi_clustered(
            df_chain=chart_df,
            selected_stock=symbol,
            spot_price=spot_price,  # <--- ADD THIS LINE HERE
            lower_bound=spot_price * (1 - st.session_state.eq_strike_range_pct / 100),
            upper_bound=spot_price * (1 + st.session_state.eq_strike_range_pct / 100)            
        )
        st.plotly_chart(fig_oi_clustered, use_container_width=True)
    
        st.markdown("---")
        dm_fmt, dm_num = build_equity_matrix(gex_df, spot_price, gamma_levels, si)
        # ── CONVERT GEX ROWS FROM LAKHS (L) TO CRORES (Cr) ────────────────────
        gex_target_rows = [idx for idx in dm_num.index if any(p in str(idx) for p in ["Call GEX", "Put GEX", "Net GEX"])]
        
        for idx in gex_target_rows:
            new_idx = str(idx).replace("(L)", "(Cr)")
            
            # 1. Update the numeric dataframe (dividing raw values by 100)
            dm_num.loc[idx] = pd.to_numeric(dm_num.loc[idx], errors='coerce') / 100.0
            dm_num = dm_num.rename(index={idx: new_idx})
            
            # 2. Re-format the display grid strings to match 2 decimal places
            for col in dm_fmt.columns:
                try:
                    clean_string_val = str(dm_fmt.loc[idx, col]).replace(",", "")
                    dm_fmt.loc[idx, col] = f"{float(clean_string_val) / 100.0:,.2f}"
                except ValueError:
                    pass
            dm_fmt = dm_fmt.rename(index={idx: new_idx})
        # ──────────────────────────────────────────────────────────────────────
        atm_strike   = int(get_atm_strike(spot_price, si))
        strikes_only = dm_fmt.columns.drop("TOTAL") if "TOTAL" in dm_fmt.columns else dm_fmt.columns

        # ── resolve dynamic row keys (contain unit suffix) ────────────────────
        def _row(prefix):
            """Return first row label whose name starts with prefix."""
            for idx in dm_num.index:
                if str(idx).startswith(prefix):
                    return idx
            return None

        row_call_gex = _row("Call GEX")
        row_put_gex  = _row("Put GEX")
        row_net_gex  = _row("Net GEX")
        row_call_oi  = _row("Call OI")
        row_put_oi   = _row("Put OI")
        row_call_iv  = "Call IV%"
        row_put_iv   = "Put IV%"
        row_call_delta = "Call Δ"
        row_put_delta  = "Put Δ"
        row_prob     = "Put Δ Prob% ↓ expiry"
        row_hedge    = "Shares (Δ hedge)"

        # ── inject hedge shares row into both dm_fmt and dm_num ──────────────
        # Formula: lot_size × call_delta, rounded to nearest integer.
        # This is the minimum shares a call seller must hold to be delta-neutral.
        if row_call_delta in dm_num.index:
            hedge_vals = {}
            for col in dm_num.columns:
                if col == "TOTAL":
                    hedge_vals[col] = pd.NA
                    continue
                raw = dm_num.loc[row_call_delta, col]
                try:
                    hedge_vals[col] = int(round(float(raw) * lot_size))
                except (TypeError, ValueError):
                    hedge_vals[col] = pd.NA
            # append to numeric df
            dm_num.loc[row_hedge] = hedge_vals
            # append formatted: plain integer string (no decimal)
            dm_fmt.loc[row_hedge] = {
                col: ("—" if pd.isna(v) else str(int(v)))
                for col, v in hedge_vals.items()
            }

        # ── helper: top-N column indices from a numeric row ───────────────────
        def _top_n(row_key, n, largest=True):
            """Return list of up to n column labels (strike ints) from strikes_only."""
            if row_key is None or row_key not in dm_num.index:
                return []
            series = dm_num.loc[row_key, strikes_only].apply(
                lambda x: float(x) if not pd.isna(x) else float("nan")
            ).dropna()
            if series.empty:
                return []
            ranked = series.nlargest(n) if largest else series.nsmallest(n)
            return list(ranked.index)

        # pre-compute rankings ─────────────────────────────────────────────────
        put_gex_top   = _top_n(row_put_gex,  2, largest=True)   # highest put GEX
        call_gex_bot  = _top_n(row_call_gex, 2, largest=False)  # most negative call GEX
        net_gex_top   = _top_n(row_net_gex,  2, largest=True)   # highest net GEX
        net_gex_bot   = _top_n(row_net_gex,  2, largest=False)  # lowest net GEX
        call_oi_top   = _top_n(row_call_oi,  2, largest=True)
        put_oi_top    = _top_n(row_put_oi,   2, largest=True)
        call_iv_top   = _top_n(row_call_iv,  2, largest=True)   # most volatile call strikes
        put_iv_top    = _top_n(row_put_iv,   2, largest=True)   # most volatile put strikes
        # Prob row: highest prob = deepest ITM, lowest prob = strongest OTM floor
        prob_high     = _top_n(row_prob,     2, largest=True)
        prob_low      = _top_n(row_prob,     2, largest=False)

        # ── colour palette ────────────────────────────────────────────────────
        # Put GEX (support) → green tones
        _PUT_GEX_1  = "background-color:rgba(34,197,94,0.70);color:white;font-weight:bold;"
        _PUT_GEX_2  = "background-color:rgba(34,197,94,0.35);color:white;"
        # Call GEX (resistance, negative) → red tones
        _CALL_GEX_1 = "background-color:rgba(239,68,68,0.70);color:white;font-weight:bold;"
        _CALL_GEX_2 = "background-color:rgba(239,68,68,0.35);color:white;"
        # Net GEX positive → emerald, negative → purple
        _NET_POS_1  = "background-color:rgba(16,185,129,0.70);color:white;font-weight:bold;"
        _NET_POS_2  = "background-color:rgba(16,185,129,0.35);color:white;"
        _NET_NEG_1  = "background-color:rgba(139,92,246,0.70);color:white;font-weight:bold;"
        _NET_NEG_2  = "background-color:rgba(139,92,246,0.35);color:white;"
        # OI walls → blue (call) and teal (put)
        _CALL_OI_1  = "background-color:rgba(245,158,11,0.70);color:white;font-weight:bold;"
        _CALL_OI_2  = "background-color:rgba(245,158,11,0.35);color:white;"
        _PUT_OI_1   = "background-color:rgba(6,182,212,0.70);color:white;font-weight:bold;"
        _PUT_OI_2   = "background-color:rgba(6,182,212,0.35);color:white;"
        # IV hottest strikes → orange
        _IV_1       = "background-color:rgba(249,115,22,0.70);color:white;font-weight:bold;"
        _IV_2       = "background-color:rgba(249,115,22,0.35);color:white;"
        # ATM column → gold border
        _ATM_COL    = "background-color:rgba(250,204,21,0.14);border:2px solid #fbbf24;"
        # TOTAL column
        _TOTAL_COL  = "background-color:rgba(148,163,184,0.10);font-weight:bold;border-left:2px solid #475569;"

        def _style_eq_matrix(df):
            styles = pd.DataFrame("", index=df.index, columns=df.columns)

            # ATM column (lowest priority — applied first, overridden below)
            if atm_strike in df.columns:
                styles.loc[:, atm_strike] = _ATM_COL

            # TOTAL column
            if "TOTAL" in df.columns:
                styles["TOTAL"] = _TOTAL_COL

            # ── Put GEX row: top-2 green ──────────────────────────────────
            if row_put_gex and row_put_gex in df.index:
                if len(put_gex_top) >= 1:
                    styles.loc[row_put_gex, put_gex_top[0]] = _PUT_GEX_1
                if len(put_gex_top) >= 2:
                    styles.loc[row_put_gex, put_gex_top[1]] = _PUT_GEX_2

            # ── Call GEX row: bottom-2 (most negative) red ────────────────
            if row_call_gex and row_call_gex in df.index:
                if len(call_gex_bot) >= 1:
                    styles.loc[row_call_gex, call_gex_bot[0]] = _CALL_GEX_1
                if len(call_gex_bot) >= 2:
                    styles.loc[row_call_gex, call_gex_bot[1]] = _CALL_GEX_2

            # ── Net GEX row: top-2 positive (emerald) + top-2 negative (purple) ─
            if row_net_gex and row_net_gex in df.index:
                if len(net_gex_top) >= 1:
                    styles.loc[row_net_gex, net_gex_top[0]] = _NET_POS_1
                if len(net_gex_top) >= 2:
                    styles.loc[row_net_gex, net_gex_top[1]] = _NET_POS_2
                if len(net_gex_bot) >= 1:
                    styles.loc[row_net_gex, net_gex_bot[0]] = _NET_NEG_1
                if len(net_gex_bot) >= 2:
                    styles.loc[row_net_gex, net_gex_bot[1]] = _NET_NEG_2

            # ── Call OI row: top-2 amber ──────────────────────────────────
            if row_call_oi and row_call_oi in df.index:
                if len(call_oi_top) >= 1:
                    styles.loc[row_call_oi, call_oi_top[0]] = _CALL_OI_1
                if len(call_oi_top) >= 2:
                    styles.loc[row_call_oi, call_oi_top[1]] = _CALL_OI_2

            # ── Put OI row: top-2 cyan ────────────────────────────────────
            if row_put_oi and row_put_oi in df.index:
                if len(put_oi_top) >= 1:
                    styles.loc[row_put_oi, put_oi_top[0]] = _PUT_OI_1
                if len(put_oi_top) >= 2:
                    styles.loc[row_put_oi, put_oi_top[1]] = _PUT_OI_2

            # ── Call IV% row: top-2 hottest orange ───────────────────────
            if row_call_iv in df.index:
                if len(call_iv_top) >= 1:
                    styles.loc[row_call_iv, call_iv_top[0]] = _IV_1
                if len(call_iv_top) >= 2:
                    styles.loc[row_call_iv, call_iv_top[1]] = _IV_2

            # ── Put IV% row: top-2 hottest orange ────────────────────────
            if row_put_iv in df.index:
                if len(put_iv_top) >= 1:
                    styles.loc[row_put_iv, put_iv_top[0]] = _IV_1
                if len(put_iv_top) >= 2:
                    styles.loc[row_put_iv, put_iv_top[1]] = _IV_2

            

            # ── Put Δ row: gradient green for -0.30 to 0 (safe OTM zone) ─
            # -0.01 to -0.10 → lightest green  (deep OTM, very safe)
            # -0.10 to -0.20 → medium green    (OTM buffer)
            # -0.20 to -0.30 → strong green    (approaching ATM boundary)
            # outside range   → no colour (ITM or beyond threshold)
            if row_put_delta in df.index:
                for col in strikes_only:
                    try:
                        pv = float(dm_num.loc[row_put_delta, col])
                    except (TypeError, ValueError, KeyError):
                        continue
                    if -0.30 <= pv <= 0:
                        intensity = abs(pv) / 0.30          # 0.0 (near 0) → 1.0 (at -0.30)
                        alpha     = round(0.20 + intensity * 0.50, 2)   # 0.20 → 0.70
                        styles.loc[row_put_delta, col] = (
                            f"background-color:rgba(34,197,94,{alpha});"
                            f"color:white;"
                            + ("font-weight:bold;" if intensity > 0.65 else "")
                        )

            # ── Shares to Buy row: teal background, bold ──────────────────
            if row_hedge in df.index:
                for col in strikes_only:
                    try:
                        hv = dm_num.loc[row_hedge, col]
                        if not pd.isna(hv):
                            styles.loc[row_hedge, col] = (
                                "background-color:rgba(20,184,166,0.22);"
                                "color:#011713;font-weight:bold;"
                            )
                    except (TypeError, ValueError, KeyError):
                        continue

            return styles
        
        
        st.dataframe(
            dm_fmt.style.apply(_style_eq_matrix, axis=None),
            use_container_width=True,
            height=min(600, 38 * (len(dm_fmt) + 0)),
        )

        # ── Colour legend ─────────────────────────────────────────────────────
        st.markdown("""
<div style="font-size:12px;color:#9ca3af;padding:6px 0 2px 0;line-height:2.2;">
<b>Highlight Legend</b> &nbsp;|&nbsp;
<span style="background:rgba(34,197,94,0.70);color:white;padding:1px 7px;border-radius:3px;">🟢 Put GEX Top-2</span>&nbsp;
<span style="background:rgba(239,68,68,0.70);color:white;padding:1px 7px;border-radius:3px;">🔴 Call GEX Top-2(–ve)</span>&nbsp;
<span style="background:rgba(16,185,129,0.70);color:white;padding:1px 7px;border-radius:3px;">🟩 Net GEX Top-2</span>&nbsp;
<span style="background:rgba(139,92,246,0.70);color:white;padding:1px 7px;border-radius:3px;">🟣 Net GEX Top-2(–ve)</span>&nbsp;
<span style="background:rgba(245,158,11,0.70);color:white;padding:1px 7px;border-radius:3px;">🟡 Call OI Top-2</span>&nbsp;
<span style="background:rgba(6,182,212,0.70);color:white;padding:1px 7px;border-radius:3px;">🔵 Put OI Top-2</span>&nbsp;
<span style="background:rgba(249,115,22,0.70);color:white;padding:1px 7px;border-radius:3px;">🟠 IV Hottest Top-2</span>&nbsp;
<span style="background:rgba(250,204,21,0.25);color:black;border:2px solid #fbbf24;padding:1px 7px;border-radius:3px;">🟡 ATM Strike</span>
<br>
<b>Put Δ row</b> &nbsp;|&nbsp;
<span style="background:rgba(34,197,94,0.20);color:white;padding:1px 7px;border-radius:3px;">Light green: −0.01 to −0.10 (deep OTM)</span>&nbsp;
<span style="background:rgba(34,197,94,0.45);color:white;padding:1px 7px;border-radius:3px;">Mid green: −0.10 to −0.20 (OTM buffer)</span>&nbsp;
<span style="background:rgba(34,197,94,0.70);color:white;padding:1px 7px;border-radius:3px;">Strong green: −0.20 to −0.30 (near boundary)</span>&nbsp;
— No colour outside −0.30 to 0 range
<br>

<b>Shares to Buy (Δ hedge) row</b> &nbsp;|&nbsp;
<span style="background:rgba(20,184,166,0.22);color:#011713;padding:1px 7px;border-radius:3px;">Teal — shares call seller must hold per lot to be delta-neutral</span>
<br>
<span style="color:#6b7280;">Darker shade = #1 rank · Lighter shade = #2 rank &nbsp;·&nbsp;
GEX in Cr (peak ≥ ₹1Cr) or L otherwise</span>
</div>
""", unsafe_allow_html=True)

        st.markdown("""
**Put Δ Probability — How to Read:**
- Each cell shows the market-implied probability that the stock closes **below that strike** at expiry
- Derived from: `abs(Put Delta) × 100`
- **Example:** Put Δ = −0.22 → **22% probability** stock expires below this strike
- 🔴 High probability strike (≥45%): price is near or already through this level — active danger zone
- 🟢 Low probability strike (<15%): deep OTM floor, market prices less than 1-in-7 chance of reaching — acts as structural support
- **Trading use:** Short puts at strikes with <20% probability for maximum premium efficiency with limited breach risk
""")

    # ── TAB 7: Greeks ─────────────────────────────────────────────────────────
    with tab7:
        st.subheader(f"Greeks Profile — {symbol}")

        greek_sel = st.selectbox(
            "Select Greek:",
            ["gamma", "delta", "vega", "theta", "rho"],
            key="eq_greek_sel",
        )

        st.plotly_chart(
            plot_equity_greeks_profile(gex_df, spot_price, symbol, greek_sel),
            use_container_width=True,
        )

        st.markdown("---")
        st.subheader("ATM Greeks Summary")

        atm_idx = (gex_df["strike"] - spot_price).abs().idxmin()
        atm_row = gex_df.loc[atm_idx]

        gc1, gc2 = st.columns(2)
        with gc1:
            st.markdown("##### 📞 Call (ATM)")
            for g_name, col_key in [
                ("Delta", "call_delta"), ("Gamma", "call_gamma"),
                ("Vega",  "call_vega"),  ("Theta", "call_theta"),
                ("Rho",   "call_rho"),
            ]:
                val = float(atm_row.get(col_key, 0))
                st.write(f"**{g_name}:** `{val:.6f}`")
            st.write(f"**Theo:** ₹{float(atm_row['call_theo']):.2f} · **LTP:** ₹{float(atm_row['call_ltp']):.2f}")
            st.write(f"**IV:** {float(atm_row['call_iv']):.2f}%")

        with gc2:
            st.markdown("##### 📉 Put (ATM)")
            for g_name, col_key in [
                ("Delta", "put_delta"), ("Gamma", "put_gamma"),
                ("Vega",  "put_vega"),  ("Theta", "put_theta"),
                ("Rho",   "put_rho"),
            ]:
                val = float(atm_row.get(col_key, 0))
                st.write(f"**{g_name}:** `{val:.6f}`")
            st.write(f"**Theo:** ₹{float(atm_row['put_theo']):.2f} · **LTP:** ₹{float(atm_row['put_ltp']):.2f}")
            st.write(f"**IV:** {float(atm_row['put_iv']):.2f}%")

        st.markdown("---")
        st.subheader("Portfolio Greeks (All Strikes)")
        pe1, pe2, pe3, pe4 = st.columns(4)
        pe1.metric("Σ DEX",   fmt_number(gex_df["total_dex"].sum()))
        pe2.metric("Σ GEX",   fmt_number(gex_df["total_gex"].sum()))
        pe3.metric("Σ VEX",   f"{gex_df['total_vex'].sum():,.0f}")
        pe4.metric("Σ TEX/d", fmt_number(gex_df["total_tex"].sum()))

    # ── TAB 8: Scanner ────────────────────────────────────────────────────────
    with tab8:
        st.subheader("🔍 Multi-Stock ATM Straddle Scanner")

        st.info("""
Scans the F&O universe and fetches ATM straddle cost, PCR, and OI for each stock.
**Use case:** Find which stocks have cheapest/richest straddles for vol plays.
""")

        scan_col1, scan_col2 = st.columns([2, 1])
        with scan_col1:
            scan_preset = st.selectbox(
                "Scan Universe",
                ["NIFTY50 (50 stocks)", "NIFTY100", "POPULAR (20 stocks)", "Custom"],
                key="eq_scan_preset",
            )
        with scan_col2:
            scan_expiry = st.selectbox(
                "Expiry for scan",
                get_equity_expiries(3),
                key="eq_scan_expiry",
            )

        if scan_preset == "Custom":
            custom_scan = st.text_area(
                "Enter symbols (comma-separated):",
                value="RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK",
                key="eq_scan_custom",
            )
            scan_symbols = [s.strip().upper() for s in custom_scan.split(",") if s.strip()]
        elif scan_preset == "POPULAR (20 stocks)":
            scan_symbols = sorted(POPULAR_STOCKS)
        
        elif scan_preset == "NIFTY100":
            scan_symbols = sorted(NIFTY100_STOCKS) # Added NIFTY100 handling
        
        else:
            scan_symbols = sorted(NIFTY50_STOCKS)

        st.caption(f"Scanning {len(scan_symbols)} stocks for expiry {scan_expiry}")

        if st.button("🔍 Run Scanner", type="primary", key="eq_run_scan",
                     disabled=not st.session_state.eq_kite_auth):
            km_scan = st.session_state.eq_kite_mgr
            if km_scan:
                progress_bar = st.progress(0, text="Scanning…")
                results_rows = []
                batch_size = 5

                for batch_start in range(0, len(scan_symbols), batch_size):
                    batch = scan_symbols[batch_start:batch_start + batch_size]
                    with st.spinner(f"Fetching {batch}…"):
                        try:
                            batch_df = km_scan.get_atm_snapshot(
                                batch, scan_expiry, rfr)
                            if not batch_df.empty:
                                results_rows.append(batch_df)
                        except Exception as exc:
                            st.warning(f"Batch {batch} failed: {exc}")
                    progress_bar.progress(
                        min((batch_start + batch_size) / len(scan_symbols), 1.0),
                        text=f"Scanned {min(batch_start + batch_size, len(scan_symbols))}/{len(scan_symbols)}"
                    )

                if results_rows:
                    scan_df = pd.concat(results_rows, ignore_index=True)
                    scan_df = scan_df[scan_df["Spot"] > 0]
                    st.session_state.eq_scan_results = scan_df
                    st.success(f"✅ Scanned {len(scan_df)} stocks")
                else:
                    st.error("No results from scanner.")
                progress_bar.empty()

        if st.session_state.eq_scan_results is not None:
            scan_df = st.session_state.eq_scan_results.copy()

            st.markdown("### 📊 Scan Results — Sorted by Straddle Cost")

            sort_col = st.radio(
                "Sort by:",
                ["Strd % Spot", "Strd Cost ₹", "ATM PCR", "Call OI", "Put OI"],
                horizontal=True, key="eq_scan_sort",
            )
            ascending = st.checkbox("Ascending", value=True, key="eq_scan_asc")
            scan_sorted = scan_df.sort_values(sort_col, ascending=ascending)

            def _color_scan_row(row):
                pcr_v = row["ATM PCR"]
                strd_v = row["Strd % Spot"]
                base  = [""] * len(row)
                if strd_v > 5:
                    base[list(scan_sorted.columns).index("Strd % Spot")] = \
                        "background-color:rgba(239,68,68,0.25);"
                elif strd_v < 2:
                    base[list(scan_sorted.columns).index("Strd % Spot")] = \
                        "background-color:rgba(34,197,94,0.25);"
                return base

            st.dataframe(
                scan_sorted.style.apply(_color_scan_row, axis=1).format({
                    "Spot":        "₹{:,.2f}",
                    "ATM":         "₹{:,.0f}",
                    "Call LTP":    "₹{:.2f}",
                    "Put LTP":     "₹{:.2f}",
                    "Straddle":    "₹{:.2f}",
                    "Strd % Spot": "{:.2f}%",
                    "Strd Cost ₹": "₹{:,.0f}",
                    "ATM PCR":     "{:.3f}",
                }),
                use_container_width=True,
                height=450,
            )

            sc_dl, sc_ref = st.columns(2)
            with sc_dl:
                st.download_button(
                    "📥 Download Scan CSV",
                    scan_df.to_csv(index=False),
                    file_name=f"eq_gex_scan_{scan_expiry}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    key="eq_dl_scan",
                )

else:
    # ── Welcome screen ────────────────────────────────────────────────────────
    st.markdown("---")
    st.info("👈 Connect Kite, select a stock, fetch the option chain, then click **🟢 GO LIVE**.")

    col1, col2, col3 = st.columns(3)
    for col, title, content, color in [
        (col1, "🔑 How to Get Started",
         "1. Enter Kite API Key + Secret\n2. Click **Login to Kite** and authorise\n3. Paste the request token\n4. Select your stock from NIFTY50/NIFTY100\n5. Pick the monthly expiry\n6. Click **Fetch Chain**\n7. Click **🟢 GO LIVE**",
         "rgba(96,165,250,0.15)"),
        (col2, "📅 Equity vs Index Options",
         "**Stock options:**\n- Monthly expiry only (last Thursday)\n- NFO exchange, NSE:SYMBOL spot\n- Lot sizes vary widely by stock\n- Strong put skew (insurance demand)\n- Max Pain pinning is stronger!\n\n**Index options:**\n- Weekly + Monthly\n- NFO/BFO exchange\n- Fixed lot sizes",
         "rgba(34,197,94,0.15)"),
        (col3, "💡 Key GEX Concepts",
         "**+GEX (Green):** Dealers long gamma → mean-reversion regime\n**-GEX (Red):** Dealers short gamma → trending/volatile regime\n**Call Wall:** Heavy call OI → resistance\n**Put Wall:** Heavy put OI → support\n**Max Pain:** Gravitational pull near expiry\n**Gamma Flip:** Regime boundary",
         "rgba(167,139,250,0.15)"),
    ]:
        with col:
            st.markdown(f"""
<div style="background:{color};border-radius:10px;padding:16px;min-height:180px;">
<h4 style="margin:0 0 8px 0;">{title}</h4>
<pre style="font-size:0.76rem;white-space:pre-wrap;color:#cbd5e1;margin:0;">{content}</pre>
</div>
""", unsafe_allow_html=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style='text-align:center;color:#6b7280;padding:0.8rem;font-size:0.76rem;'>
  <b>Equity GEX Terminal — NSE F&O Monthly Options</b><br>
  5s live spot ticks · Black-Scholes Greeks · Kite Connect NFO · Multi-stock scanner<br>
  <span style='color:#ef4444;'>⚠️ Educational only. Not financial advice. Options trading involves substantial risk.</span>
</div>
""", unsafe_allow_html=True)
