"""Riskplan för en affär: stopp, likvidationsnivå och storlek. Rena beräkningar, inga spärrar."""
from dataclasses import dataclass

from . import config
from .indicators import summarize


def liquidation_move(havstang: float, blankad: bool = False) -> float | None:
    """Hur stor kursrörelse (andel, t.ex. 0.063 = 6,3 %) mot positionen som ger likvidation."""
    m = config.load()["likvidation"]["underhallsmarginal_procent"] / 100
    if blankad:
        return (1 / havstang + 1) / (1 + m) - 1          # kursen stiger så här mycket
    if havstang <= 1:
        return None
    return 1 - (1 - 1 / havstang) / (1 - m)              # kursen faller så här mycket


@dataclass
class Plan:
    ticker: str
    pris: float
    havstang: float
    blankad: bool
    atr_procent: float           # normal daglig rörelse i %
    likvidation_procent: float | None
    likvidation_pris: float | None
    likvidation_dagar: float | None   # hur många "normala dagar" bort likvidationen ligger
    stopp_procent: float
    stopp_pris: float
    niva: dict
    insats_kr: tuple[float, float]
    max_forlust_kr: tuple[float, float]
    varningar: list[str]


def plan(ticker: str, history, kontovarde: float, havstang: float = 1.0, blankad: bool = False) -> Plan:
    cfg = config.load()["handelsstil"]
    s = summarize(ticker, history)
    atr = s.atr14_procent or (s.volatilitet_ar or 30) / 16      # fallback: årsvol / sqrt(252)
    liq = liquidation_move(havstang, blankad)
    stopp = cfg["stopp_atr_multipel"] * atr / 100
    if liq is not None:
        stopp = min(stopp, cfg["stopp_fore_likvidation"] * liq)
    sign = 1 if blankad else -1
    niva = next((n for n in cfg["nivaer"] if n["havstang"][0] <= havstang <= n["havstang"][1]), cfg["nivaer"][-1])
    lo, hi = (kontovarde * p / 100 for p in niva["insats_procent"])
    warn = []
    liq_dagar = (liq * 100 / atr) if liq is not None and atr else None
    if liq_dagar is not None and liq_dagar < 2:
        warn.append(f"Likvidationen ligger bara {liq_dagar:.1f} normala dagsrörelser bort – kan slå till på en "
                    "helt vanlig dag. Kräver LIVE-bevakning och snabbt stopp.")
    if havstang > 1:
        warn.append("Hävstång: bara i LIVE-session, och stängs innan sessionen slutar.")
    if stopp * 100 < atr:
        warn.append(f"Stoppet ({stopp:.1%}) är mindre än en normal dagsrörelse ({atr:.1f} %) – stor risk att "
                    "det slår till av rent brus.")
    return Plan(s.ticker, s.pris, havstang, blankad, atr, liq * 100 if liq is not None else None,
                s.pris * (1 + sign * liq) if liq is not None else None, liq_dagar, stopp * 100,
                s.pris * (1 + sign * stopp), niva, (lo, hi),
                (lo * havstang * stopp, hi * havstang * stopp), warn)
