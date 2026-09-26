"""Handelsmotorn: köp, sälj, blankning, hävstång, avgifter, likvidation, konkurs och omgångar.

Allt är simulerat. Motorn vet ingenting om Claude Code – den kan anropas av vilket
program som helst (t.ex. en framtida fristående Carl via Claudes API).

Modell:
- Kassan (kassa_sek) är fria pengar. Den får aldrig bli negativ.
- En position låser en säkerhet ur kassan: säkerhet = positionens värde / hävstång.
- Lång med hävstång: resten lånas (lan_sek). Eget kapital = marknadsvärde - lån.
- Blankning: eget kapital = säkerhet + ingångsvärde - marknadsvärde.
- Förlusten kan aldrig bli större än säkerheten: när eget kapital understiger
  underhållsmarginalen likvideras positionen automatiskt (margin call).
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from . import config, db, markets, prices
from .prices import PriceError, Quote

QuoteFn = Callable[[str], tuple[Quote, Quote]]
LARDOMAR = config.ROOT / "data" / "lardomar.md"


class TradeError(Exception):
    """Affären avvisades. Meddelandet förklarar varför."""


@dataclass
class Ctx:
    conn: sqlite3.Connection
    agent_id: str = db.DEFAULT_AGENT
    quote_fn: QuoteFn = prices.get_quote_sek
    now: datetime | None = None
    lardomar_path: Path = LARDOMAR
    _cache: dict = field(default_factory=dict)

    def __post_init__(self):
        self.now = self.now or datetime.now(timezone.utc)
        db.ensure_agent(self.conn, self.agent_id)

    def quote(self, ticker: str) -> tuple[Quote, Quote]:
        """Hämtar pris + valutakurs en gång per körning och sparar priset i databasen."""
        t = ticker.upper()
        if t not in self._cache:
            q, fx = self.quote_fn(t)
            prices.save_quote(self.conn, q)
            self._cache[t] = (q, fx)
        return self._cache[t]


# ---------------------------------------------------------------- hjälpfunktioner

def _cfg() -> dict:
    return config.load()


def fee_sek(value_sek: float, valuta: str) -> float:
    a = _cfg()["avgifter"]
    courtage = max(value_sek * a["courtage_procent"] / 100, a["courtage_min_sek"])
    fx = value_sek * a["valutavaxling_procent"] / 100 if valuta.upper() != "SEK" else 0.0
    return round(courtage + fx, 2)


def _maint() -> float:
    return _cfg()["likvidation"]["underhallsmarginal_procent"] / 100


def account(ctx: Ctx) -> sqlite3.Row:
    return ctx.conn.execute("SELECT * FROM accounts WHERE agent_id=?", (ctx.agent_id,)).fetchone()


def _set_cash(ctx: Ctx, kassa: float, extra_fee: float = 0.0) -> None:
    kassa = max(0.0, round(kassa, 6))  # kontot får aldrig gå i skuld
    ctx.conn.execute("UPDATE accounts SET kassa_sek=?, avgifter_sek=avgifter_sek+? WHERE agent_id=?",
                     (kassa, extra_fee, ctx.agent_id))


def positions(ctx: Ctx) -> list[sqlite3.Row]:
    return ctx.conn.execute("SELECT * FROM positions WHERE agent_id=? ORDER BY id", (ctx.agent_id,)).fetchall()


def _position(ctx: Ctx, ticker: str) -> sqlite3.Row | None:
    return ctx.conn.execute("SELECT * FROM positions WHERE agent_id=? AND ticker=?",
                            (ctx.agent_id, ticker.upper())).fetchone()


def _pending_crash(ctx: Ctx) -> sqlite3.Row | None:
    return ctx.conn.execute("SELECT * FROM bankruptcies WHERE agent_id=? AND analys IS NULL",
                            (ctx.agent_id,)).fetchone()


def active_round(ctx: Ctx) -> sqlite3.Row | None:
    return ctx.conn.execute("SELECT * FROM rounds WHERE agent_id=? AND status='aktiv' ORDER BY id DESC LIMIT 1",
                            (ctx.agent_id,)).fetchone()


def active_session(ctx: Ctx) -> sqlite3.Row | None:
    return ctx.conn.execute("SELECT * FROM sessions WHERE agent_id=? AND slut IS NULL ORDER BY id DESC LIMIT 1",
                            (ctx.agent_id,)).fetchone()


def today_se(ctx: Ctx) -> date:
    return ctx.now.astimezone(markets.SE_TZ).date()


# ---------------------------------------------------------------- värdering

@dataclass
class PosValue:
    ticker: str
    antal: float            # negativt = blankad
    riktning: str           # lång / blankad
    snittpris: float
    pris: float
    valuta: str
    valutakurs: float
    havstang: float
    marknadsvarde_sek: float
    eget_kapital_sek: float
    insats_sek: float
    resultat_sek: float     # orealiserat, inkl. avgifter
    resultat_procent: float
    likvidationspris: float | None
    prisalder: str
    kalla: str


def equity_sek(pos, pris: float, fx: float) -> float:
    mv = abs(pos["antal"]) * pris * fx
    if pos["antal"] > 0:
        return mv - pos["lan_sek"]
    return pos["sakerhet_sek"] + pos["kostnad_sek"] - mv


def liquidation_price(pos, fx: float) -> float | None:
    """Priset (i instrumentets valuta) där positionen stängs automatiskt, vid nuvarande valutakurs."""
    q, m = abs(pos["antal"]), _maint()
    if pos["antal"] > 0:
        if pos["lan_sek"] <= 0:
            return None
        return pos["lan_sek"] / (q * fx * (1 - m))
    return (pos["sakerhet_sek"] + pos["kostnad_sek"]) / (q * fx * (1 + m))


def value_position(ctx: Ctx, pos) -> PosValue:
    q, fx = ctx.quote(pos["ticker"])
    mv = abs(pos["antal"]) * q.pris * fx.pris
    eq = equity_sek(pos, q.pris, fx.pris)
    res = eq - pos["insats_sek"]
    return PosValue(pos["ticker"], pos["antal"], "lång" if pos["antal"] > 0 else "blankad", pos["snittpris"],
                    q.pris, q.valuta, fx.pris, pos["havstang"], mv, eq, pos["insats_sek"], res,
                    100 * res / pos["insats_sek"] if pos["insats_sek"] else 0.0,
                    liquidation_price(pos, fx.pris), q.alder_text(), q.kalla)


@dataclass
class Snapshot:
    kassa_sek: float
    positioner: list[PosValue]
    totalt_sek: float
    varningar: list[str]
    komplett: bool          # False om något pris saknades


def snapshot(ctx: Ctx) -> Snapshot:
    kassa = account(ctx)["kassa_sek"]
    vals, warn, total = [], [], kassa
    for p in positions(ctx):
        try:
            v = value_position(ctx, p)
            vals.append(v)
            total += v.eget_kapital_sek
        except PriceError as e:
            warn.append(f"Inget pris för {p['ticker']} – räknas till säkerheten tills vidare ({e})")
            total += p["sakerhet_sek"]
    return Snapshot(kassa, vals, total, warn, not warn)


# ---------------------------------------------------------------- räntor och avgifter över tid

def accrue_costs(ctx: Ctx) -> float:
    """Drar låneränta (hävstång) och blankningsavgift för tiden sedan förra dragningen."""
    acc = account(ctx)
    last = acc["senast_ranta"]
    ctx.conn.execute("UPDATE accounts SET senast_ranta=? WHERE agent_id=?", (ctx.now.isoformat(), ctx.agent_id))
    if not last:
        return 0.0
    days = (ctx.now - datetime.fromisoformat(last)).total_seconds() / 86400
    if days <= 0:
        return 0.0
    a = _cfg()["avgifter"]
    kassa, total = acc["kassa_sek"], 0.0
    for p in positions(ctx):
        cost = p["lan_sek"] * a["laneranta_procent_ar"] / 100 * days / 365
        if p["antal"] < 0:
            cost += p["kostnad_sek"] * a["blankningsavgift_procent_ar"] / 100 * days / 365
        if cost <= 0:
            continue
        from_cash = min(kassa, cost)
        kassa -= from_cash
        # Räcker inte kassan tas resten ur positionens säkerhet
        ctx.conn.execute("UPDATE positions SET insats_sek=insats_sek+?, sakerhet_sek=sakerhet_sek-? WHERE id=?",
                         (from_cash, cost - from_cash, p["id"]))
        total += cost
    _set_cash(ctx, kassa, total)
    return total


# ---------------------------------------------------------------- affärer

@dataclass
class TradeResult:
    handling: str
    ticker: str
    antal: float
    pris: float
    valuta: str
    valutakurs: float
    varde_sek: float
    avgift_sek: float
    havstang: float
    resultat_sek: float | None
    kassa_efter: float
    varningar: list[str]


def _check_can_trade(ctx: Ctx, ticker: str) -> list[str]:
    if _pending_crash(ctx):
        raise TradeError("Carl har gått i konkurs och måste skriva sin haveri-analys innan han får handla igen: "
                         "python portfolio.py haveri \"...\"")
    s = markets.status(markets.exchange_for(ticker), ctx.now)
    if not s.oppen:
        raise TradeError(f"{s.namn} är stängd. Nästa öppning: {s.nasta_oppning:%a %Y-%m-%d %H:%M} svensk tid. "
                         "Ingen order lagd.")
    return []


def _age_warning(q: Quote) -> list[str]:
    max_min = _cfg()["priser"]["max_alder_minuter_aktier"]
    if q.alder_sekunder > max_min * 60:
        return [f"OBS: priset för {q.ticker} är {q.alder_text()} gammalt."]
    return []


def _log_trade(ctx: Ctx, r: TradeResult, strategi: str | None, motivering: str | None,
               prisalder: float | None, session_id: int | None, andel: float | None = None) -> None:
    rnd = active_round(ctx)
    if session_id is None:
        s = active_session(ctx)
        session_id = s["id"] if s else None
    ctx.conn.execute(
        """INSERT INTO trades(agent_id, round_id, tid, handling, ticker, antal, pris, valuta, valutakurs, varde_sek,
           avgift_sek, havstang, resultat_sek, strategi, motivering, prisalder_sek, session_id, andel_procent)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ctx.agent_id, rnd["id"] if rnd else None, ctx.now.isoformat(), r.handling, r.ticker, r.antal, r.pris,
         r.valuta, r.valutakurs, r.varde_sek, r.avgift_sek, r.havstang, r.resultat_sek, strategi, motivering,
         prisalder, session_id, andel))


def shares_for_amount(ctx: Ctx, ticker: str, belopp_sek: float, havstang: float = 1.0) -> int:
    """Hur många aktier ett belopp (egen insats i SEK) räcker till, inkl. avgifter."""
    q, fx = ctx.quote(ticker)
    pris_sek = q.pris * fx.pris
    n = int(belopp_sek * havstang / pris_sek)
    while n > 0 and n * pris_sek / havstang + fee_sek(n * pris_sek, q.valuta) > belopp_sek:
        n -= 1
    return n


def open_position(ctx: Ctx, ticker: str, antal: float, riktning: str = "lång", havstang: float = 1.0,
                  motivering: str | None = None, strategi: str | None = None,
                  session_id: int | None = None) -> TradeResult:
    """Köp (riktning='lång') eller blanka (riktning='blankad')."""
    ticker = ticker.upper()
    if antal <= 0 or antal != int(antal):
        raise TradeError("Antal måste vara ett positivt heltal.")
    if havstang < 1:
        raise TradeError("Hävstång måste vara minst 1.")
    handling = "buy" if riktning == "lång" else "short"
    warn = _check_can_trade(ctx, ticker)
    q, fx = ctx.quote(ticker)  # PriceError om priset inte går att hämta -> ingen affär
    warn += _age_warning(q)

    value = antal * q.pris * fx.pris
    collateral = value / havstang
    fee = fee_sek(value, q.valuta)
    kassa = account(ctx)["kassa_sek"]
    if collateral + fee > kassa + 1e-9:
        raise TradeError(f"För lite pengar: behöver {collateral + fee:,.2f} kr (säkerhet {collateral:,.2f} + "
                         f"avgift {fee:,.2f}), kassan är {kassa:,.2f} kr.")

    total_fore = snapshot(ctx).totalt_sek
    andel = 100 * (collateral + fee) / total_fore if total_fore > 0 else None
    sign = 1 if riktning == "lång" else -1
    loan = value - collateral if sign > 0 else 0.0
    existing = _position(ctx, ticker)
    if existing:
        if (existing["antal"] > 0) != (sign > 0):
            raise TradeError(f"Carl har redan en {'lång' if existing['antal'] > 0 else 'blankad'} position i "
                             f"{ticker}. Stäng den först.")
        n_old, n_new = abs(existing["antal"]), abs(existing["antal"]) + antal
        kostnad = existing["kostnad_sek"] + value
        sakerhet = existing["sakerhet_sek"] + collateral
        ctx.conn.execute(
            """UPDATE positions SET antal=?, snittpris=?, kostnad_sek=?, sakerhet_sek=?, lan_sek=?, insats_sek=?,
               havstang=? WHERE id=?""",
            (sign * n_new, (existing["snittpris"] * n_old + q.pris * antal) / n_new, kostnad, sakerhet,
             existing["lan_sek"] + loan, existing["insats_sek"] + collateral + fee, kostnad / sakerhet,
             existing["id"]))
    else:
        ctx.conn.execute(
            """INSERT INTO positions(agent_id, ticker, valuta, antal, snittpris, havstang, kostnad_sek, sakerhet_sek,
               lan_sek, insats_sek, oppnad, strategi, andel_procent) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ctx.agent_id, ticker, q.valuta, sign * antal, q.pris, havstang, value, collateral, loan,
             collateral + fee, ctx.now.isoformat(), strategi, andel))
    _set_cash(ctx, kassa - collateral - fee, fee)
    pos = _position(ctx, ticker)
    ctx.conn.execute("UPDATE positions SET likvidationspris=? WHERE id=?",
                     (liquidation_price(pos, fx.pris), pos["id"]))
    r = TradeResult(handling, ticker, antal, q.pris, q.valuta, fx.pris, value, fee, havstang, None,
                    account(ctx)["kassa_sek"], warn)
    _log_trade(ctx, r, strategi, motivering, q.alder_sekunder, session_id, andel)
    return r


def close_position(ctx: Ctx, ticker: str, antal: float | None = None, motivering: str | None = None,
                   strategi: str | None = None, session_id: int | None = None,
                   _liquidation: bool = False) -> TradeResult:
    """Sälj en lång position eller köp tillbaka (täck) en blankad. antal=None stänger allt."""
    ticker = ticker.upper()
    pos = _position(ctx, ticker)
    if not pos:
        raise TradeError(f"Carl har ingen position i {ticker}.")
    held = abs(pos["antal"])
    antal = held if antal is None else antal
    if antal <= 0 or antal > held + 1e-9 or antal != int(antal):
        raise TradeError(f"Ogiltigt antal. Carl har {held:g} st {ticker}.")
    warn = [] if _liquidation else _check_can_trade(ctx, ticker)
    q, fx = ctx.quote(ticker)
    if not _liquidation:
        warn += _age_warning(q)

    f = antal / held
    value = antal * q.pris * fx.pris
    fee = fee_sek(value, q.valuta)
    back = f * equity_sek(pos, q.pris, fx.pris) - fee   # vad som kommer tillbaka till kassan
    result = back - f * pos["insats_sek"]
    kassa = account(ctx)["kassa_sek"]
    if back < 0:
        warn.append(f"Förlusten översteg säkerheten med {-back:,.2f} kr – dras från kassan (aldrig under 0).")
    _set_cash(ctx, kassa + back, fee)

    if abs(antal - held) < 1e-9:
        ctx.conn.execute("DELETE FROM positions WHERE id=?", (pos["id"],))
    else:
        k = 1 - f
        ctx.conn.execute(
            """UPDATE positions SET antal=?, kostnad_sek=?, sakerhet_sek=?, lan_sek=?, insats_sek=? WHERE id=?""",
            ((held - antal) * (1 if pos["antal"] > 0 else -1), pos["kostnad_sek"] * k, pos["sakerhet_sek"] * k,
             pos["lan_sek"] * k, pos["insats_sek"] * k, pos["id"]))

    if _liquidation:
        handling = "liquidation"
    else:
        handling = "sell" if pos["antal"] > 0 else "cover"
    r = TradeResult(handling, ticker, antal, q.pris, q.valuta, fx.pris, value, fee, pos["havstang"], result,
                    account(ctx)["kassa_sek"], warn)
    _log_trade(ctx, r, strategi or pos["strategi"], motivering, q.alder_sekunder, session_id,
               pos["andel_procent"])
    return r


# ---------------------------------------------------------------- likvidation och konkurs

def check_liquidations(ctx: Ctx) -> list[TradeResult]:
    """Stänger positioner vars egna kapital ätits upp ned till underhållsmarginalen."""
    out = []
    for p in positions(ctx):
        try:
            q, fx = ctx.quote(p["ticker"])
        except PriceError:
            continue  # utan pris kan vi inte bedöma – ingen gissning
        mv = abs(p["antal"]) * q.pris * fx.pris
        eq = equity_sek(p, q.pris, fx.pris)
        ctx.conn.execute("UPDATE positions SET likvidationspris=? WHERE id=?", (liquidation_price(p, fx.pris), p["id"]))
        if eq <= _maint() * mv:
            out.append(close_position(
                ctx, p["ticker"], None, _liquidation=True,
                motivering=f"MARGIN CALL: eget kapital {eq:,.2f} kr understeg {_maint():.0%} av positionens värde "
                           f"{mv:,.2f} kr vid pris {q.pris:,.4f} {q.valuta}. Automatisk likvidation."))
    return out


def check_bankruptcy(ctx: Ctx, snap: Snapshot | None = None) -> bool:
    """Om kontot är i princip tomt: konkurs. Räknaren +1, kontot nollställs till startkapitalet
    och Carl MÅSTE skriva en haveri-analys innan han får handla igen."""
    snap = snap or snapshot(ctx)
    if not snap.komplett or snap.totalt_sek >= _cfg()["konkursgrans_sek"]:
        return False
    for p in positions(ctx):
        close_position(ctx, p["ticker"], None, _liquidation=True, motivering="KONKURS: tvångsstängning.")
    varde = account(ctx)["kassa_sek"]
    start = float(_cfg()["startkapital_sek"])
    rnd = active_round(ctx)
    ctx.conn.execute("INSERT INTO bankruptcies(agent_id, tid, round_id, varde_sek) VALUES (?,?,?,?)",
                     (ctx.agent_id, ctx.now.isoformat(), rnd["id"] if rnd else None, varde))
    ctx.conn.execute("UPDATE accounts SET konkurser=konkurser+1, kassa_sek=? WHERE agent_id=?", (start, ctx.agent_id))
    if rnd:
        ctx.conn.execute("UPDATE rounds SET tillskott_sek=tillskott_sek+? WHERE id=?", (start - varde, rnd["id"]))
    return True


def write_crash_analysis(ctx: Ctx, analys: str) -> int:
    """Sparar den obligatoriska haveri-analysen permanent (databas + lärdomsfilen)."""
    crash = _pending_crash(ctx)
    if not crash:
        raise TradeError("Det finns ingen konkurs som väntar på haveri-analys.")
    if len(analys.strip()) < 50:
        raise TradeError("Haveri-analysen är för kort. Vad gick fel, vilka beslut ledde dit, vad gör du annorlunda?")
    ctx.conn.execute("UPDATE bankruptcies SET analys=? WHERE id=?", (analys.strip(), crash["id"]))
    n = account(ctx)["konkurser"]
    from .journal import ensure_file
    path = ensure_file(ctx.lardomar_path)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n## 💥 HAVERI-ANALYS – KONKURS #{n} ({today_se(ctx)})\n\n{analys.strip()}\n")
    return n


# ---------------------------------------------------------------- omgångar

def quarter_end(d: date) -> date:
    for m, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
        e = date(d.year, m, day)
        if d <= e:
            return e
    raise AssertionError


def start_round(ctx: Ctx, slutdatum: date | None = None) -> sqlite3.Row:
    if active_round(ctx):
        raise TradeError("Det finns redan en aktiv omgång.")
    start = today_se(ctx)
    slut = slutdatum or quarter_end(start)
    ctx.conn.execute("INSERT INTO rounds(agent_id, startdatum, slutdatum, startvarde_sek) VALUES (?,?,?,?)",
                     (ctx.agent_id, start.isoformat(), slut.isoformat(), snapshot(ctx).totalt_sek))
    return active_round(ctx)


def roll_rounds(ctx: Ctx, snap: Snapshot) -> list[sqlite3.Row]:
    """Avslutar omgångar vars slutdatum passerat och startar nästa. Portföljen följer med."""
    closed = []
    rnd = active_round(ctx)
    while rnd and today_se(ctx) > date.fromisoformat(rnd["slutdatum"]):
        ctx.conn.execute("UPDATE rounds SET status='avslutad', slutvarde_sek=? WHERE id=?", (snap.totalt_sek, rnd["id"]))
        closed.append(ctx.conn.execute("SELECT * FROM rounds WHERE id=?", (rnd["id"],)).fetchone())
        nstart = date.fromisoformat(rnd["slutdatum"]) + timedelta(days=1)
        ctx.conn.execute("INSERT INTO rounds(agent_id, startdatum, slutdatum, startvarde_sek) VALUES (?,?,?,?)",
                         (ctx.agent_id, nstart.isoformat(), quarter_end(nstart).isoformat(), snap.totalt_sek))
        rnd = active_round(ctx)
    return closed


def days_left(ctx: Ctx) -> int | None:
    rnd = active_round(ctx)
    return (date.fromisoformat(rnd["slutdatum"]) - today_se(ctx)).days if rnd else None


# ---------------------------------------------------------------- uppdatering

@dataclass
class UpdateReport:
    kostnader_sek: float
    likvidationer: list[TradeResult]
    konkurs: bool
    avslutade_omgangar: list
    snapshot: Snapshot


def update(ctx: Ctx) -> UpdateReport:
    """Körs vid varje sessionsstart och prisuppdatering: räntor, likvidationer, konkurs, omgångar, graf."""
    cost = accrue_costs(ctx)
    liq = check_liquidations(ctx)
    snap = snapshot(ctx)
    crashed = check_bankruptcy(ctx, snap)
    if crashed:
        snap = snapshot(ctx)
    closed = roll_rounds(ctx, snap)
    ctx.conn.execute("INSERT INTO equity(agent_id, tid, totalt_sek, kassa_sek) VALUES (?,?,?,?)",
                     (ctx.agent_id, ctx.now.isoformat(), snap.totalt_sek, snap.kassa_sek))
    return UpdateReport(cost, liq, crashed, closed, snap)


def record_equity(ctx: Ctx) -> Snapshot:
    snap = snapshot(ctx)
    ctx.conn.execute("INSERT INTO equity(agent_id, tid, totalt_sek, kassa_sek) VALUES (?,?,?,?)",
                     (ctx.agent_id, ctx.now.isoformat(), snap.totalt_sek, snap.kassa_sek))
    return snap
