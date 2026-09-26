"""Tekniska indikatorer från kurshistorik. Rena beräkningar – ingen nätverkskod här."""
from dataclasses import asdict, dataclass

import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """Wilders RSI."""
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / down.replace(0, float("nan"))
    return (100 - 100 / (1 + rs)).fillna(100.0)


def macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    line = ema(s, fast) - ema(s, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


@dataclass
class Summary:
    ticker: str
    pris: float
    datum: str
    sma20: float | None
    sma50: float | None
    sma200: float | None
    rsi14: float
    macd: float
    macd_signal: float
    macd_hist: float
    volym: float | None
    volym_snitt20: float | None
    volym_ratio: float | None       # dagens volym / snitt 20 dagar
    volatilitet_ar: float | None     # årlig volatilitet (20 dagar), %
    atr14_procent: float | None      # genomsnittlig daglig rörelse, % av priset
    avk_1v: float | None
    avk_1m: float | None
    avk_3m: float | None
    avk_1a: float | None
    hogsta_52v: float
    lagsta_52v: float
    fran_hogsta_procent: float
    signaler: list[str]

    def dict(self):
        return asdict(self)


def _last(s: pd.Series):
    v = s.iloc[-1] if len(s) else float("nan")
    return None if pd.isna(v) else float(v)


def _ret(c: pd.Series, n: int):
    return None if len(c) <= n else float(100 * (c.iloc[-1] / c.iloc[-1 - n] - 1))


def summarize(ticker: str, h: pd.DataFrame) -> Summary:
    c = h["Close"].astype(float)
    if len(c) < 30:
        raise ValueError(f"För kort historik för {ticker} ({len(c)} dagar)")
    v = h["Volume"].astype(float) if "Volume" in h else pd.Series(dtype=float)
    m_line, m_sig, m_hist = macd(c)
    r = rsi(c)
    s20, s50, s200 = _last(sma(c, 20)), _last(sma(c, 50)), _last(sma(c, 200))
    vol20 = _last(c.pct_change().rolling(20).std() * (252 ** 0.5) * 100)
    atr = None
    if {"High", "Low"} <= set(h.columns):
        tr = pd.concat([h["High"] - h["Low"], (h["High"] - c.shift()).abs(), (h["Low"] - c.shift()).abs()], axis=1).max(axis=1)
        atr = _last(tr.rolling(14).mean() / c * 100)
    vs = _last(v.rolling(20).mean()) if len(v) else None
    vl = _last(v) if len(v) else None
    last = float(c.iloc[-1])
    y = c.iloc[-252:]
    hi, lo = float(y.max()), float(y.min())

    sig = []
    rv = float(r.iloc[-1])
    if rv >= 70:
        sig.append(f"RSI {rv:.0f}: överköpt")
    elif rv <= 30:
        sig.append(f"RSI {rv:.0f}: översåld")
    if len(m_hist) > 1:
        if m_hist.iloc[-1] > 0 >= m_hist.iloc[-2]:
            sig.append("MACD korsade UPP genom signallinjen (köpsignal)")
        elif m_hist.iloc[-1] < 0 <= m_hist.iloc[-2]:
            sig.append("MACD korsade NER genom signallinjen (säljsignal)")
    if s50 and s200:
        prev50, prev200 = sma(c, 50).iloc[-2], sma(c, 200).iloc[-2]
        if s50 > s200 and prev50 <= prev200:
            sig.append("Golden cross (SMA50 över SMA200)")
        elif s50 < s200 and prev50 >= prev200:
            sig.append("Death cross (SMA50 under SMA200)")
        sig.append("Långsiktig upptrend (pris > SMA200)" if last > s200 else "Långsiktig nedtrend (pris < SMA200)")
    if vs and vl and vl > 2 * vs:
        sig.append(f"Ovanligt hög volym ({vl / vs:.1f}x snittet)")
    if last >= hi * 0.99:
        sig.append("Nära 52-veckorshögsta")
    if last <= lo * 1.01:
        sig.append("Nära 52-veckorslägsta")

    return Summary(
        ticker.upper(), last, str(c.index[-1].date()), s20, s50, s200, rv,
        float(m_line.iloc[-1]), float(m_sig.iloc[-1]), float(m_hist.iloc[-1]),
        vl, vs, (vl / vs) if (vl and vs) else None, vol20, atr,
        _ret(c, 5), _ret(c, 21), _ret(c, 63), _ret(c, 252), hi, lo, 100 * (last / hi - 1), sig)
