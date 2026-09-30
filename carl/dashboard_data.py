"""Samlar allt dashboarden visar. Läser BARA databasen (senast hämtade priser) – hämtar inget från nätet."""
from datetime import date, datetime, timezone

from . import config, markets
from .engine import equity_sek, liquidation_price


def _latest_price(conn, ticker: str):
    return conn.execute("SELECT * FROM prices WHERE ticker=? ORDER BY hamtad DESC LIMIT 1", (ticker,)).fetchone()


def instrument_type(ticker: str, cfg: dict, havstang: float = 1.0, antal: float = 1.0) -> str:
    """Grupp på dashboarden: Aktier, Fonder & ETF:er, Krypto eller Hävstång & blankning."""
    if havstang > 1 or antal < 0:
        return "Hävstång & blankning"
    if ticker in (cfg.get("krypto_etp") or {}):
        return "Krypto"
    if ticker in (cfg.get("fonder_etf") or {}):
        return "Fonder & ETF:er"
    return "Aktier"


def build(conn, agent_id: str = "carl") -> dict:
    now = datetime.now(timezone.utc)
    acc = conn.execute("SELECT * FROM accounts WHERE agent_id=?", (agent_id,)).fetchone()
    cfg = config.load()
    start_kap = float(cfg["startkapital_sek"])
    kassa = acc["kassa_sek"] if acc else start_kap

    pos_out, total = [], kassa
    for p in conn.execute("SELECT * FROM positions WHERE agent_id=? ORDER BY id", (agent_id,)):
        pr = _latest_price(conn, p["ticker"])
        fx = 1.0
        if p["valuta"] != "SEK":
            fxr = _latest_price(conn, f"{p['valuta']}SEK=X")
            fx = fxr["pris"] if fxr else p["kostnad_sek"] / (abs(p["antal"]) * p["snittpris"])
        pris = pr["pris"] if pr else p["snittpris"]
        eq = equity_sek(p, pris, fx)
        total += eq
        res = eq - p["insats_sek"]
        pos_out.append({
            "ticker": p["ticker"], "antal": p["antal"], "riktning": "lång" if p["antal"] > 0 else "blankad",
            "snittpris": p["snittpris"], "pris": pris, "valuta": p["valuta"], "havstang": p["havstang"],
            "varde_sek": abs(p["antal"]) * pris * fx, "eget_kapital_sek": eq, "resultat_sek": res,
            "resultat_procent": 100 * res / p["insats_sek"] if p["insats_sek"] else 0,
            "likvidationspris": liquidation_price(p, fx),
            "pristid": pr["pristid"] if pr else None, "strategi": p["strategi"],
            "typ": instrument_type(p["ticker"], cfg, p["havstang"], p["antal"]),
        })

    rnd = conn.execute("SELECT * FROM rounds WHERE agent_id=? AND status='aktiv' ORDER BY id DESC LIMIT 1",
                       (agent_id,)).fetchone()
    omg = None
    if rnd:
        bas = rnd["startvarde_sek"] + rnd["tillskott_sek"]
        idag = now.astimezone(markets.SE_TZ).date()
        omg = {"id": rnd["id"], "start": rnd["startdatum"], "slut": rnd["slutdatum"], "startvarde": rnd["startvarde_sek"],
               "dagar_kvar": (date.fromisoformat(rnd["slutdatum"]) - idag).days,
               "avkastning_sek": total - bas, "avkastning_procent": 100 * (total / bas - 1) if bas else 0}

    equity = [{"t": r["tid"], "v": r["totalt_sek"]} for r in
              conn.execute("SELECT tid, totalt_sek FROM equity WHERE agent_id=? ORDER BY tid", (agent_id,))]
    trades = [dict(r) for r in conn.execute(
        """SELECT id, tid, handling, ticker, antal, pris, valuta, varde_sek, avgift_sek, havstang, resultat_sek,
                  strategi, motivering, lardom FROM trades WHERE agent_id=? ORDER BY id DESC LIMIT 300""", (agent_id,))]
    for t in trades:
        t["typ"] = instrument_type(t["ticker"], cfg, t["havstang"] or 1.0,
                                   -1 if t["handling"] in ("short", "cover") else 1)
    last = conn.execute("SELECT * FROM sessions WHERE agent_id=? AND slut IS NOT NULL ORDER BY id DESC LIMIT 1",
                        (agent_id,)).fetchone()
    pagar = conn.execute("SELECT id, start FROM sessions WHERE agent_id=? AND slut IS NULL ORDER BY id DESC LIMIT 1",
                         (agent_id,)).fetchone()
    rounds = [dict(r) for r in conn.execute("SELECT * FROM rounds WHERE agent_id=? ORDER BY id", (agent_id,))]
    crashes = [dict(r) for r in conn.execute("SELECT * FROM bankruptcies WHERE agent_id=? ORDER BY id", (agent_id,))]
    closed = conn.execute("SELECT COUNT(*) n, SUM(resultat_sek > 0) w FROM trades WHERE agent_id=? AND resultat_sek IS NOT NULL",
                          (agent_id,)).fetchone()

    return {
        "genererad": now.isoformat(),
        "startkapital": start_kap,
        "totalt": total,
        "kassa": kassa,
        "konkurser": acc["konkurser"] if acc else 0,
        "avgifter": acc["avgifter_sek"] if acc else 0,
        "omgang": omg,
        "equity": equity,
        "positioner": pos_out,
        "affarer": trades,
        "avslutade": closed["n"] or 0,
        "traffsakerhet": (100 * closed["w"] / closed["n"]) if closed["n"] else None,
        "senaste_session": dict(last) if last else None,
        "pagaende_session": dict(pagar) if pagar else None,
        "omgangar": rounds,
        "haverier": crashes,
    }
