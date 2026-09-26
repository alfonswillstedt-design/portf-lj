"""Hämtar riktiga priser. Carl får ALDRIG hitta på priser: går priset inte att
hämta kastas PriceError och då blir det ingen affär."""
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from . import config
from .markets import crypto_symbol


class PriceError(Exception):
    pass


@dataclass
class Quote:
    ticker: str
    pris: float
    valuta: str
    pristid: datetime   # när priset gällde (UTC)
    kalla: str

    @property
    def alder_sekunder(self) -> float:
        return (datetime.now(timezone.utc) - self.pristid).total_seconds()

    def alder_text(self) -> str:
        s = self.alder_sekunder
        if s < 120:
            return f"{int(s)} s"
        if s < 7200:
            return f"{int(s // 60)} min"
        if s < 172800:
            return f"{s / 3600:.1f} h"
        return f"{s / 86400:.1f} dagar"


def _timeout() -> float:
    return float(config.load()["priser"]["timeout_sekunder"])


# ---------- Aktier och valuta via yfinance ----------

def fetch_yahoo(ticker: str) -> Quote:
    import yfinance as yf  # importeras här så att tester kan köras utan nät

    try:
        t = yf.Ticker(ticker)
        h = t.history(period="5d", interval="1m")
        if h is None or h.empty:
            h = t.history(period="1mo", interval="1d")
        if h is None or h.empty:
            raise PriceError(f"Inget pris från Yahoo för {ticker}")
        last = h.dropna(subset=["Close"]).iloc[-1]
        pris = float(last["Close"])
        pristid = h.dropna(subset=["Close"]).index[-1].to_pydatetime().astimezone(timezone.utc)
        try:
            valuta = t.fast_info["currency"] or ""
        except Exception:
            valuta = ""
    except PriceError:
        raise
    except Exception as e:
        raise PriceError(f"Kunde inte hämta {ticker} från Yahoo: {e}") from e

    if not valuta:
        if ticker.endswith("=X"):
            valuta = "SEK"
        else:
            raise PriceError(f"Okänd valuta för {ticker}")
    if valuta in ("GBp", "GBX"):  # London noteras i pence
        pris, valuta = pris / 100, "GBP"
    if pris <= 0:
        raise PriceError(f"Ogiltigt pris för {ticker}: {pris}")
    return Quote(ticker.upper(), pris, valuta.upper(), pristid, "yahoo")


# ---------- Krypto via Binance, reserv CoinGecko ----------

def fetch_binance(sym: str) -> Quote:
    r = requests.get("https://api.binance.com/api/v3/ticker/24hr",
                     params={"symbol": f"{sym}USDT"}, timeout=_timeout())
    r.raise_for_status()
    d = r.json()
    pris = float(d["lastPrice"])
    pristid = datetime.fromtimestamp(int(d["closeTime"]) / 1000, timezone.utc)
    return Quote(sym, pris, "USD", pristid, "binance")


def fetch_coingecko(sym: str) -> Quote:
    cg_id = config.load()["krypto"][sym]
    r = requests.get("https://api.coingecko.com/api/v3/simple/price",
                     params={"ids": cg_id, "vs_currencies": "usd", "include_last_updated_at": "true"},
                     timeout=_timeout())
    r.raise_for_status()
    d = r.json()[cg_id]
    return Quote(sym, float(d["usd"]), "USD",
                 datetime.fromtimestamp(int(d["last_updated_at"]), timezone.utc), "coingecko")


def fetch_crypto(sym: str) -> Quote:
    fel = []
    for f in (fetch_binance, fetch_coingecko):
        try:
            q = f(sym)
            if q.pris > 0:
                return q
        except Exception as e:
            fel.append(f"{f.__name__}: {e}")
    raise PriceError(f"Kunde inte hämta krypto {sym}: " + " | ".join(fel))


# ---------- Publikt API ----------

def get_quote(ticker: str) -> Quote:
    """Pris i instrumentets egen valuta."""
    sym = crypto_symbol(ticker)
    if sym:
        return fetch_crypto(sym)
    return fetch_yahoo(ticker.upper())


def fx_rate(valuta: str) -> Quote:
    """SEK per 1 enhet av valutan, t.ex. USD -> ~10.5."""
    valuta = valuta.upper()
    if valuta == "SEK":
        return Quote("SEK", 1.0, "SEK", datetime.now(timezone.utc), "fast")
    q = fetch_yahoo(f"{valuta}SEK=X")
    q.valuta = "SEK"
    return q


def get_quote_sek(ticker: str) -> tuple[Quote, Quote]:
    """(pris, valutakurs). Pris i SEK = pris.pris * valutakurs.pris."""
    q = get_quote(ticker)
    return q, fx_rate(q.valuta)


def save_quote(conn, q: Quote) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO prices(ticker, pris, valuta, pristid, hamtad, kalla) VALUES (?,?,?,?,?,?)",
        (q.ticker, q.pris, q.valuta, q.pristid.isoformat(), datetime.now(timezone.utc).isoformat(), q.kalla),
    )
