"""
modules/equity_data_fetcher.py
================================
NSE Equity (Stock) Option Chain Fetcher — Kite Connect v3

KEY DIFFERENCES FROM INDEX GEX:
─────────────────────────────────────────────────────────────────────
1.  Exchange   : Index options → NFO.  Equity options → NFO (same exchange,
                 but instrument name = stock symbol e.g. "RELIANCE")
2.  Expiry     : All equity options are MONTHLY only (last Thursday of month).
                 No weekly expiries for stocks.
3.  Lot sizes  : Vary wildly per stock (e.g. RELIANCE=250, HDFC=550, TCS=150).
                 Fetched live from Kite instruments.
4.  Strike step: Varies per stock price range (e.g. ₹10, ₹20, ₹50, ₹100).
5.  GEX        : Equity dealers hold much smaller absolute positions, so GEX
                 must be normalised per-share (not per crore like index).
6.  Market cap  : Stock GEX should be expressed as % of market cap / ADV for
                 meaningful interpretation (unlike index which uses notional ₹Cr).
7.  Underlying : Kite LTP key = "NSE:<SYMBOL>" for equities.
8.  Symbol list: Curated universe — F&O eligible stocks only.
                 Provided as NIFTY-50, NIFTY-100, NIFTY-200 presets.

Public API:
───────────
    from modules.equity_data_fetcher import (
        EquityKiteManager,
        get_fo_universe,
        NIFTY50_STOCKS, NIFTY100_STOCKS,
    )
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Optional
import calendar

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm

try:
    from kiteconnect import KiteConnect
    _KITE_AVAILABLE = True
except ImportError:
    _KITE_AVAILABLE = False


# ─── F&O Universe (NSE stocks with active options) ─────────────────────────

NIFTY50_STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "BHARTIARTL", "ICICIBANK",
    "INFY", "SBIN", "HINDUNILVR", "ITC", "KOTAKBANK",
    "LT", "AXISBANK", "WIPRO", "HCLTECH", "BAJFINANCE",
    "ASIANPAINT", "MARUTI", "NTPC", "ULTRACEMCO", "POWERGRID",
    "TITAN", "SUNPHARMA", "ADANIENT", "ONGC", "JSWSTEEL",
    "TATAMOTORS", "M&M", "TATASTEEL", "TECHM", "NESTLEIND",
    "BAJAJFINSV", "HINDALCO", "COALINDIA", "DIVISLAB", "DRREDDY",
    "CIPLA", "INDUSINDBK", "GRASIM", "BPCL", "ADANIPORTS",
    "EICHERMOT", "BRITANNIA", "TATACONSUM", "HEROMOTOCO", "APOLLOHOSP",
    "HDFCLIFE", "SBILIFE", "BAJAJ-AUTO", "SHRIRAMFIN", "BEL"
]

NIFTY100_EXTRA = [
    "360ONE", "ABB", "APLAPOLLO", "AUBANK", "ADANIENSOL", "ADANIENT", "ADANIGREEN", 
    "ADANIPORTS", "ADANIPOWER", "ABCAPITAL", "ALKEM", "AMBER", "AMBUJACEM", "ANGELONE", 
    "APOLLOHOSP", "ASHOKLEY", "ASIANPAINT", "ASTRAL", "AUROPHARMA", "DMART", "AXISBANK", 
    "BSE", "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BAJAJHLDNG", "BANDHANBNK", 
    "BANKBARODA", "BANKINDIA", "BDL", "BEL", "BHARATFORG", "BHEL", "BPCL", "BHARTIARTL", 
    "BIOCON", "BLUESTARCO", "BOSCHLTD", "BRITANNIA", "CGPOWER", "CANBK", "CDSL", 
    "CHOLAFIN", "CIPLA", "COALINDIA", "COCHINSHIP", "COFORGE", "COLPAL", "CAMS", "CONCOR", 
    "CROMPTON", "CUMMINSIND", "DLF", "DABUR", "DALBHARAT", "DELHIVERY", "DIVISLAB", 
    "DIXON", "DRREDDY", "ETERNAL", "EICHERMOT", "EXIDEIND", "FORCEMOT", "NYKAA", "FORTIS", 
    "GAIL", "GVT&D", "GMRAIRPORT", "GLENMARK", "GODFRYPHLP", "GODREJCP", "GODREJPROP", 
    "GRASIM", "HCLTECH", "HDFCAMC", "HDFCBANK", "HDFCLIFE", "HAVELLS", "HEROMOTOCO", 
    "HINDALCO", "HAL", "HINDPETRO", "HINDUNILVR", "HINDZINC", "POWERINDIA", "HYUNDAI", 
    "ICICIBANK", "ICICIGI", "ICICIPRULI", "IDFCFIRSTB", "ITC", "INDIANB", "IEX", "IOC", 
    "IRFC", "IREDA", "INDUSTOWER", "INDUSINDBK", "NAUKRI", "INFY", "INOXWIND", "INDIGO", 
    "JINDALSTEL", "JSWENERGY", "JSWSTEEL", "JIOFIN", "JUBLFOOD", "KEI", "KPITTECH", 
    "KALYANKJIL", "KAYNES", "KFINTECH", "KOTAKBANK", "LTF", "LICHSGFIN", "LTM", "LT", 
    "LAURUSLABS", "LICI", "LODHA", "LUPIN", "M&M", "MANAPPURAM", "MANKIND", "MARICO", 
    "MARUTI", "MFSL", "MAXHEALTH", "MAZDOCK", "MOTILALOFS", "MPHASIS", "MCX", "MUTHOOTFIN", 
    "NBCC", "NHPC", "NMDC", "NTPC", "NATIONALUM", "NESTLEIND", "NAM-INDIA", "NUVAMA", 
    "OBEROIRLTY", "ONGC", "OIL", "PAYTM", "OFSS", "POLICYBZR", "PGEL", "PIIND", 
    "PNBHOUSING", "PAGEIND", "PATANJALI", "PERSISTENT", "PETRONET", "PIDILITIND", 
    "POLYCAB", "PFC", "POWERGRID", "PREMIERENE", "PRESTIGE", "PNB", "RBLBANK", "RECLTD", 
    "RADICO", "RVNL", "RELIANCE", "SBICARD", "SBILIFE", "SHREECEM", "SRF", "SAMMAANCAP", 
    "MOTHERSON", "SHRIRAMFIN", "SIEMENS", "SOLARINDS", "SONACOMS", "SBIN", "SAIL", 
    "SUNPHARMA", "SUPREMEIND", "SUZLON", "SWIGGY", "TATACONSUM", "TVSMOTOR", "TCS", 
    "TATAELXSI", "TMPV", "TATAPOWER", "TATASTEEL", "TECHM", "FEDERALBNK", "INDHOTEL", 
    "PHOENIXLTD", "TITAN", "TORNTPHARM", "TRENT", "TIINDIA", "UNOMINDA", "UPL", 
    "ULTRACEMCO", "UNIONBANK", "UNITDSPR", "VBL", "VEDL", "VMM", "IDEA", "VOLTAS", 
    "WAAREEENER", "WIPRO", "YESBANK", "ZYDUSLIFE"
]

NIFTY100_STOCKS = NIFTY100_EXTRA

# Popular standalone picks
POPULAR_STOCKS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY",
    "SBIN", "AXISBANK", "WIPRO", "BHARTIARTL", "TATAMOTORS",
    "BAJFINANCE", "KOTAKBANK", "LT", "SUNPHARMA", "MARUTI",
    "NTPC", "ONGC", "TATASTEEL", "JSWSTEEL", "HINDALCO",
]


# ─── Black-Scholes helpers ──────────────────────────────────────────────────

def _bs_price(S: float, K: float, T: float, r: float,
               sigma: float, opt: str = "call") -> float:
    if T <= 0 or sigma <= 0:
        return max((S - K) if opt == "call" else (K - S), 0.0)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    if opt == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def _iv_from_ltp(S: float, K: float, T: float, r: float,
                  ltp: float, opt: str = "call") -> float:
    """Back-solve IV. Returns 0.25 (25%) as safe default on failure."""
    if T <= 0 or ltp <= 0:
        return 0.25
    intrinsic = max((S - K) if opt == "call" else (K - S), 0.0)
    if ltp <= intrinsic + 1e-4:
        return 0.001
    try:
        return max(brentq(
            lambda s: _bs_price(S, K, T, r, s, opt) - ltp,
            1e-4, 6.0, xtol=1e-6, maxiter=300
        ), 0.001)
    except Exception:
        return 0.25


# ─── Exception classes ──────────────────────────────────────────────────────

class EquityKiteError(Exception):
    pass

class EquityAuthError(EquityKiteError):
    pass

class EquityDataError(EquityKiteError):
    pass


# ─── Expiry helpers (equity = last Thursday of month, monthly only) ─────────

def get_equity_expiries(num: int = 6, from_date: Optional[datetime] = None) -> list[str]:
    """
    Return upcoming NSE equity option expiry dates.
    All equity options expire on the LAST THURSDAY of each calendar month.
    No weekly expiries exist for stocks.
    """
    today = from_date or datetime.now()
    result: list[str] = []
    yr, mo = today.year, today.month

    while len(result) < num:
        # Last Thursday of yr/mo
        last_day = calendar.monthrange(yr, mo)[1]
        candidate = datetime(yr, mo, last_day)
        while candidate.weekday() != 3:  # 3 = Thursday
            candidate -= timedelta(days=1)

        if candidate.date() > today.date():
            result.append(candidate.strftime("%d-%b-%Y").upper())

        mo += 1
        if mo > 12:
            mo, yr = 1, yr + 1

    return result


def get_next_equity_expiry() -> str:
    return get_equity_expiries(1)[0]


# ─── EquityKiteManager ──────────────────────────────────────────────────────

class EquityKiteManager:
    """
    Kite Connect wrapper specifically for NSE equity (stock) options.

    Architecture differences vs index KiteManager:
    • Instruments lookup uses stock name (e.g. "RELIANCE"), not index name
    • All options live in NFO exchange regardless of stock
    • Underlying spot fetched from NSE: prefix (e.g. "NSE:RELIANCE")
    • Lot sizes and strike intervals fetched per-stock from instruments
    • No BSE/BFO complexity — equity options are NSE-only
    """

    def __init__(self, api_key: str, api_secret: str):
        if not _KITE_AVAILABLE:
            raise EquityKiteError("kiteconnect not installed. Run: pip install kiteconnect")
        self.api_key    = api_key
        self.api_secret = api_secret
        self.kite       = KiteConnect(api_key=api_key)
        self.access_token: Optional[str] = None
        self._nfo_cache: Optional[list[dict]] = None   # full NFO instruments

    # ── auth ────────────────────────────────────────────────────────────────

    def get_login_url(self) -> str:
        return self.kite.login_url()

    def set_access_token(self, request_token: str) -> tuple[bool, str]:
        try:
            data = self.kite.generate_session(
                request_token, api_secret=self.api_secret)
            self.access_token = data["access_token"]
            self.kite.set_access_token(self.access_token)
            profile = self.kite.profile()
            return True, f"Logged in as {profile.get('user_name', 'Unknown')}"
        except Exception as exc:
            return False, str(exc)

    # ── instruments cache ────────────────────────────────────────────────────

    def _nfo_instruments(self) -> list[dict]:
        """Load and cache full NFO instrument list."""
        if self._nfo_cache is None:
            try:
                self._nfo_cache = self.kite.instruments("NFO")
            except Exception as exc:
                raise EquityDataError(f"Could not load NFO instruments: {exc}") from exc
        return self._nfo_cache

    def invalidate_cache(self):
        self._nfo_cache = None

    def _stock_instruments(self, symbol: str) -> list[dict]:
        """
        Return all CE/PE rows for a stock symbol.
        IMPORTANT: Stock name in NFO instruments is the SYMBOL (e.g. "RELIANCE"),
        not a display name. Filter by name field.
        """
        sym = symbol.upper().strip()
        all_insts = self._nfo_instruments()
        return [
            i for i in all_insts
            if i.get("name", "").upper() == sym
            and i.get("instrument_type") in ("CE", "PE")
        ]

    # ── metadata ─────────────────────────────────────────────────────────────

    def get_lot_size(self, symbol: str) -> int:
        rows = self._stock_instruments(symbol)
        sizes = {int(r["lot_size"]) for r in rows if int(r.get("lot_size", 0)) > 0}
        return min(sizes) if sizes else 1

    def get_strike_interval(self, symbol: str, expiry: Optional[str] = None) -> float:
        rows = self._stock_instruments(symbol)
        if expiry:
            try:
                tgt = datetime.strptime(expiry, "%d-%b-%Y").date()
                filtered = [r for r in rows if r.get("expiry") == tgt]
                rows = filtered if filtered else rows
            except Exception:
                pass
        strikes = sorted({float(r["strike"]) for r in rows if float(r.get("strike", 0)) > 0})
        if len(strikes) < 2:
            return 10.0
        diffs = [b - a for a, b in zip(strikes, strikes[1:]) if b > a]
        return float(min(diffs)) if diffs else 10.0

    def get_available_expiries(self, symbol: str) -> list[str]:
        today = date.today()
        rows = self._stock_instruments(symbol)
        exp_set: set[date] = set()
        for r in rows:
            exp = r.get("expiry")
            if isinstance(exp, date) and exp >= today:
                exp_set.add(exp)
        return [d.strftime("%d-%b-%Y").upper() for d in sorted(exp_set)]

    # ── spot price ──────────────────────────────────────────────────────────

    def get_spot_ltp(self, symbol: str) -> float:
        """Fetch stock LTP from NSE: prefix."""
        key = f"NSE:{symbol.upper()}"
        try:
            resp = self.kite.ltp([key])
            data = resp.get(key, {})
            ltp = data.get("last_price")
            if ltp is not None:
                return float(ltp)
            raise EquityDataError(f"No LTP for {key}")
        except Exception as exc:
            err = str(exc).lower()
            if any(w in err for w in ("token", "session", "login", "403")):
                raise EquityAuthError(f"Session error for {symbol}: {exc}") from exc
            raise EquityDataError(f"LTP fetch failed for {symbol}: {exc}") from exc

    def get_spot_ohlc(self, symbol: str) -> Optional[dict]:
        key = f"NSE:{symbol.upper()}"
        try:
            resp = self.kite.ohlc([key])
            data = resp.get(key, {})
            if not data:
                return None
            return {
                "last_price": float(data["last_price"]),
                "open":  float(data["ohlc"]["open"]),
                "high":  float(data["ohlc"]["high"]),
                "low":   float(data["ohlc"]["low"]),
                "close": float(data["ohlc"]["close"]),
            }
        except Exception:
            return None

    # ── batch quote ─────────────────────────────────────────────────────────

    def _quote_chunked(self, keys: list[str], chunk: int = 450) -> dict:
        merged: dict = {}
        errors: list[str] = []
        for i in range(0, len(keys), chunk):
            try:
                merged.update(self.kite.quote(keys[i:i + chunk]))
            except Exception as exc:
                errors.append(str(exc))
        if not merged and errors:
            err = "; ".join(errors)
            if any(w in err.lower() for w in ("token", "session", "403")):
                raise EquityAuthError(f"Quote auth failed: {err}")
            raise EquityDataError(f"All quote chunks failed: {err}")
        return merged

    # ── option chain ─────────────────────────────────────────────────────────

    def get_option_chain(
        self,
        symbol: str,
        expiry: str,
        risk_free_rate: float = 0.07,
    ) -> tuple[pd.DataFrame, float]:
        """
        Fetch full option chain for a stock.

        Returns (raw_df, spot_price) where raw_df has columns:
          strike, expiry, type (CE/PE), oi, oi_change, volume,
          iv, ltp, change, bid_qty, ask_qty, lot_size, tick_size
        """
        try:
            target_date = datetime.strptime(expiry, "%d-%b-%Y").date()
        except ValueError as exc:
            raise EquityDataError(f"Invalid expiry '{expiry}': {exc}") from exc

        all_rows = self._stock_instruments(symbol)
        if not all_rows:
            raise EquityDataError(
                f"No NFO contracts found for '{symbol}'. "
                f"Check if the stock has F&O segment enabled."
            )

        rows = [r for r in all_rows if r.get("expiry") == target_date]
        if not rows:
            avail = self.get_available_expiries(symbol)[:4]
            raise EquityDataError(
                f"No contracts for {symbol} expiry {expiry}. "
                f"Available: {avail}"
            )

        spot = self.get_spot_ltp(symbol)
        now = datetime.now()
        dte = max(
            (datetime.combine(target_date, datetime.min.time()) - now
             ).total_seconds() / (365 * 86_400),
            1 / 365,
        )

        ts_keys = [f"NFO:{r['tradingsymbol']}" for r in rows]
        quotes = self._quote_chunked(ts_keys)

        option_rows: list[dict] = []
        missing = 0
        for inst in rows:
            key = f"NFO:{inst['tradingsymbol']}"
            q = quotes.get(key)
            if not q:
                missing += 1
                continue

            ltp    = float(q.get("last_price", 0) or 0)
            oi     = int(q.get("oi", 0) or 0)
            vol    = int(q.get("volume", 0) or 0)
            strike = float(inst["strike"])
            itype  = inst["instrument_type"]

            oi_change = int(
                float(q.get("oi_day_high") or 0)
                - float(q.get("oi_day_low") or 0)
            )

            depth    = q.get("depth") or {}
            buy_qty  = int((depth.get("buy") or [{}])[0].get("quantity", 0))
            sell_qty = int((depth.get("sell") or [{}])[0].get("quantity", 0))

            iv_dec = _iv_from_ltp(
                spot, strike, dte, risk_free_rate,
                ltp, "call" if itype == "CE" else "put",
            )

            option_rows.append({
                "strike":    strike,
                "expiry":    expiry,
                "type":      itype,
                "oi":        oi,
                "oi_change": oi_change,
                "volume":    vol,
                "iv":        round(iv_dec * 100, 4),
                "ltp":       ltp,
                "change":    float(q.get("net_change", 0) or 0),
                "bid_qty":   buy_qty,
                "ask_qty":   sell_qty,
                "lot_size":  int(inst.get("lot_size", 1)),
                "tick_size": float(inst.get("tick_size", 0.05)),
            })

        if not option_rows:
            raise EquityDataError(
                f"All {len(rows)} contracts returned empty quotes "
                f"({missing} missing). Market may be closed."
            )

        df = (pd.DataFrame(option_rows)
              .sort_values("strike")
              .reset_index(drop=True))
        return df, spot

    # ── multi-stock snapshot (for scanner) ───────────────────────────────────

    def get_atm_snapshot(
        self,
        symbols: list[str],
        expiry: str,
        risk_free_rate: float = 0.07,
    ) -> pd.DataFrame:
        """
        For each symbol: fetch ATM call+put LTP, OI, IV.
        Returns a compact summary DataFrame — used in the scanner tab.
        """
        results: list[dict] = []
        for sym in symbols:
            try:
                spot = self.get_spot_ltp(sym)
                rows = self._stock_instruments(sym)
                try:
                    tgt = datetime.strptime(expiry, "%d-%b-%Y").date()
                    rows = [r for r in rows if r.get("expiry") == tgt] or rows
                except Exception:
                    pass

                if not rows:
                    continue

                strikes = sorted({float(r["strike"]) for r in rows})
                atm = min(strikes, key=lambda s: abs(s - spot))
                atm_rows = [r for r in rows if float(r["strike"]) == atm]
                ts_keys = [f"NFO:{r['tradingsymbol']}" for r in atm_rows]
                if not ts_keys:
                    continue

                quotes = self._quote_chunked(ts_keys)
                call_oi = put_oi = call_iv = put_iv = call_ltp = put_ltp = 0
                for inst in atm_rows:
                    key = f"NFO:{inst['tradingsymbol']}"
                    q = quotes.get(key, {})
                    ltp = float(q.get("last_price", 0) or 0)
                    oi_val = int(q.get("oi", 0) or 0)
                    if inst["instrument_type"] == "CE":
                        call_oi, call_ltp = oi_val, ltp
                    else:
                        put_oi, put_ltp = oi_val, ltp

                straddle = call_ltp + put_ltp
                pcr = put_oi / call_oi if call_oi > 0 else 0.0
                lot = self.get_lot_size(sym)
                straddle_lot_value = straddle * lot

                results.append({
                    "Symbol":      sym,
                    "Spot":        round(spot, 2),
                    "ATM":         int(atm),
                    "Call LTP":    round(call_ltp, 2),
                    "Put LTP":     round(put_ltp, 2),
                    "Straddle":    round(straddle, 2),
                    "Strd % Spot": round(straddle / spot * 100, 2) if spot > 0 else 0,
                    "Call OI":     call_oi,
                    "Put OI":      put_oi,
                    "ATM PCR":     round(pcr, 3),
                    "Lot Size":    lot,
                    "Strd Cost ₹": round(straddle_lot_value, 0),
                })
            except Exception as exc:
                results.append({
                    "Symbol": sym, "Spot": 0, "ATM": 0,
                    "Call LTP": 0, "Put LTP": 0,
                    "Straddle": 0, "Strd % Spot": 0,
                    "Call OI": 0, "Put OI": 0,
                    "ATM PCR": 0, "Lot Size": 0,
                    "Strd Cost ₹": 0,
                })

        return pd.DataFrame(results)

    # ── historical data ──────────────────────────────────────────────────────

    def get_historical_candles(
        self,
        symbol: str,
        interval: str = "day",
        days_back: int = 90,
    ) -> pd.DataFrame:
        """Fetch OHLCV for stock underlying (NSE equity segment)."""
        key = f"NSE:{symbol.upper()}"
        try:
            resp = self.kite.ltp([key])
            token = resp.get(key, {}).get("instrument_token")
            if not token:
                # Try from NSE instruments
                try:
                    nse_insts = self.kite.instruments("NSE")
                    for inst in nse_insts:
                        if inst.get("tradingsymbol", "").upper() == symbol.upper():
                            token = int(inst["instrument_token"])
                            break
                except Exception:
                    pass
        except Exception:
            token = None

        if not token:
            raise EquityDataError(f"Could not find instrument token for {symbol}")

        to_dt   = datetime.now()
        from_dt = to_dt - timedelta(days=days_back + 5)
        try:
            raw = self.kite.historical_data(
                instrument_token=token,
                from_date=from_dt,
                to_date=to_dt,
                interval=interval,
            )
        except Exception as exc:
            raise EquityDataError(f"Historical data failed for {symbol}: {exc}") from exc

        if not raw:
            raise EquityDataError(f"Empty historical data for {symbol}")

        df = pd.DataFrame(raw)
        df["date"] = pd.to_datetime(df["date"])
        return df.set_index("date").sort_index()

    # ── diagnostics ─────────────────────────────────────────────────────────

    def test_connection(self, symbol: str = "RELIANCE") -> dict:
        results = {}
        try:
            p = self.kite.profile()
            results["1_session"] = {
                "ok": True, "label": "Session",
                "msg": f"Valid — {p.get('user_name','')}",
            }
        except Exception as exc:
            results["1_session"] = {
                "ok": False, "label": "Session",
                "msg": f"FAILED — {exc}",
            }
            return results

        try:
            spot = self.get_spot_ltp(symbol)
            results["2_spot_ltp"] = {
                "ok": True, "label": f"NSE:{symbol} LTP",
                "msg": f"₹{spot:,.2f}",
            }
        except Exception as exc:
            results["2_spot_ltp"] = {
                "ok": False, "label": f"NSE:{symbol} LTP", "msg": str(exc)}

        try:
            insts = self._nfo_instruments()
            results["3_nfo_instruments"] = {
                "ok": len(insts) > 0,
                "label": "NFO Instruments",
                "msg": f"{len(insts):,} rows loaded",
            }
        except Exception as exc:
            results["3_nfo_instruments"] = {
                "ok": False, "label": "NFO Instruments", "msg": str(exc)}

        try:
            rows = self._stock_instruments(symbol)
            expiries = sorted({str(r.get("expiry")) for r in rows if r.get("expiry")})
            results["4_stock_contracts"] = {
                "ok": len(rows) > 0,
                "label": f"{symbol} Contracts",
                "msg": (f"{len(rows):,} CE+PE across {len(expiries)} expiries"
                        f" (nearest: {expiries[0] if expiries else 'none'})"),
            }
        except Exception as exc:
            results["4_stock_contracts"] = {
                "ok": False, "label": f"{symbol} Contracts", "msg": str(exc)}

        return results


# ─── F&O universe loader ────────────────────────────────────────────────────

def get_fo_universe(preset: str = "NIFTY50") -> list[str]:
    """Return sorted list of F&O-eligible stocks for a preset."""
    if preset == "NIFTY50":
        return sorted(NIFTY50_STOCKS)
    elif preset == "NIFTY100":
        return sorted(NIFTY100_STOCKS)
    elif preset == "POPULAR":
        return sorted(POPULAR_STOCKS)
    return sorted(NIFTY50_STOCKS)
