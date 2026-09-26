"""Börsernas öppettider. (Krypto handlas bara via ETP:er på Stockholmsbörsen.)"""
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from . import config

SE_TZ = ZoneInfo("Europe/Stockholm")
def exchange_for(ticker: str) -> str:
    """Vilken börs en ticker hör till, t.ex. 'stockholm' eller 'usa'."""
    t = ticker.upper()
    borser = config.load()["borser"]
    for key, b in borser.items():
        for s in b["suffix"]:
            if s and t.endswith(s.upper()):
                return key
    if "." in t:
        raise ValueError(f"Okänd börs för {ticker}. Lägg till suffixet under 'borser' i config.yaml.")
    return "usa"


def _hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


@dataclass
class MarketStatus:
    borse: str
    namn: str
    oppen: bool
    nasta_oppning: datetime | None  # svensk tid
    stanger: datetime | None        # svensk tid, om öppen


def _is_trading_day(key: str, d) -> bool:
    if d.weekday() >= 5:
        return False
    helg = config.load().get("helgdagar", {}).get(key, [])
    return d.isoformat() not in helg


def status(key: str, now: datetime | None = None) -> MarketStatus:
    now = now or datetime.now(timezone.utc)
    b = config.load()["borser"][key]
    tz = ZoneInfo(b["tidszon"])
    local = now.astimezone(tz)
    o, c = _hm(b["oppnar"]), _hm(b["stanger"])
    today_open = datetime.combine(local.date(), o, tz)
    today_close = datetime.combine(local.date(), c, tz)
    if _is_trading_day(key, local.date()) and today_open <= local < today_close:
        return MarketStatus(key, b["namn"], True, None, today_close.astimezone(SE_TZ))
    d = local.date()
    if local >= today_open or not _is_trading_day(key, d):
        d += timedelta(days=1)
    for _ in range(15):
        if _is_trading_day(key, d):
            break
        d += timedelta(days=1)
    nxt = datetime.combine(d, o, tz).astimezone(SE_TZ)
    return MarketStatus(key, b["namn"], False, nxt, None)


def is_open(ticker: str, now: datetime | None = None) -> bool:
    return status(exchange_for(ticker), now).oppen


def all_status(now: datetime | None = None) -> list[MarketStatus]:
    return [status(k, now) for k in config.load()["borser"]]
