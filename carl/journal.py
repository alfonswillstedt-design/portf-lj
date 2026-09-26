"""Tradedagbok, lärdomsfil och sessioner."""
from __future__ import annotations

from pathlib import Path

from .engine import Ctx, TradeError, active_session, days_left, snapshot, today_se, active_round

LARDOMAR_MALL = """# Carl-Gustafs lärdomar

Läs detta före varje beslut. Var femte session sammanfattas och rensas filen:
kärnlärdomarna uppdateras, gamla loggposter tas bort. Haveri-analyser (💥) raderas ALDRIG.

## Kärnlärdomar (sammanfattat)

- (inga än – Carl har inte handlat)

## Logg
"""


def ensure_file(path: Path) -> Path:
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(LARDOMAR_MALL, encoding="utf-8")
    return path


def add_lesson(ctx: Ctx, trade_id: int, text: str) -> None:
    t = ctx.conn.execute("SELECT * FROM trades WHERE id=? AND agent_id=?", (trade_id, ctx.agent_id)).fetchone()
    if not t:
        raise TradeError(f"Ingen affär #{trade_id}.")
    if t["resultat_sek"] is None:
        raise TradeError(f"Affär #{trade_id} är ingen avslutad affär (inget resultat). Lärdomar skrivs efter stängning.")
    if len(text.strip()) < 15:
        raise TradeError("Lärdomen är för kort – vad gick bra/dåligt och vad lär du dig?")
    ctx.conn.execute("UPDATE trades SET lardom=? WHERE id=?", (text.strip(), trade_id))
    path = ensure_file(ctx.lardomar_path)
    tecken = "✅" if t["resultat_sek"] > 0 else "❌"
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n### {tecken} #{trade_id} {t['ticker']} {t['handling']} {t['havstang']:g}x "
                f"({t['tid'][:10]}, {t['resultat_sek']:+,.0f} kr, strategi: {t['strategi'] or '-'})\n{text.strip()}\n")


def read_lessons(ctx: Ctx) -> str:
    return ensure_file(ctx.lardomar_path).read_text(encoding="utf-8")


# ---------------------------------------------------------------- sessioner

def start_session(ctx: Ctx) -> tuple:
    """Startar en session (eller återupptar en som inte avslutats). Returnerar (session, nummer, ny)."""
    s = active_session(ctx)
    ny = s is None
    if ny:
        ctx.conn.execute("INSERT INTO sessions(agent_id, start, startvarde_sek) VALUES (?,?,?)",
                         (ctx.agent_id, ctx.now.isoformat(), snapshot(ctx).totalt_sek))
        s = active_session(ctx)
    nr = ctx.conn.execute("SELECT COUNT(*) FROM sessions WHERE agent_id=? AND id<=?", (ctx.agent_id, s["id"])).fetchone()[0]
    return s, nr, ny


def previous_session(ctx: Ctx, before_id: int | None = None):
    q = "SELECT * FROM sessions WHERE agent_id=? AND slut IS NOT NULL"
    args = [ctx.agent_id]
    if before_id:
        q += " AND id<?"
        args.append(before_id)
    return ctx.conn.execute(q + " ORDER BY id DESC LIMIT 1", args).fetchone()


def sv(x: float, d: int = 2) -> str:
    """Svensk talformatering: 32 500,00"""
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


_NAMN = {"buy": "KÖP", "sell": "SÄLJ", "short": "BLANKA", "cover": "KÖP TILLBAKA (täck blankning)",
         "liquidation": "STÄNG (likviderad)"}


def copy_list(ctx: Ctx, session_id: int) -> list[str]:
    rows = ctx.conn.execute("SELECT * FROM trades WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
    out = []
    for t in rows:
        s = (f"{_NAMN[t['handling']]} {t['antal']:g} st {t['ticker']} à ca {sv(t['pris'])} {t['valuta']}"
             f" (≈ {sv(t['varde_sek'], 0)} kr)")
        if t["havstang"] > 1:
            s += f", hävstång {t['havstang']:g}x"
        if t["handling"] in ("short", "cover") or (t["havstang"] > 1 and t["handling"] in ("buy", "sell")):
            s += "  → görs i tävlingen via certifikat, se Carls anvisning nedan"
        out.append(s)
    return out


def end_session(ctx: Ctx, sammanfattning: str, kopiera_anvisning: str | None, tankar: str | None) -> dict:
    s = active_session(ctx)
    if not s:
        raise TradeError("Ingen aktiv session. Starta med: python session.py start")
    snap = snapshot(ctx)
    lista = copy_list(ctx, s["id"])
    kopiera = "\n".join(f"{i}. {x}" for i, x in enumerate(lista, 1)) or "Inga affärer denna session – gör ingenting."
    if kopiera_anvisning:
        kopiera += "\n\nAnvisning från Carl:\n" + kopiera_anvisning.strip()
    ctx.conn.execute("UPDATE sessions SET slut=?, slutvarde_sek=?, sammanfattning=?, att_kopiera=?, tankar=? WHERE id=?",
                     (ctx.now.isoformat(), snap.totalt_sek, sammanfattning, kopiera, tankar, s["id"]))
    prev = previous_session(ctx, s["id"])
    rnd = active_round(ctx)
    bas = (rnd["startvarde_sek"] + rnd["tillskott_sek"]) if rnd else None
    return {
        "session_id": s["id"],
        "varde": snap.totalt_sek,
        "kassa": snap.kassa_sek,
        "sedan_forra": snap.totalt_sek - (prev["slutvarde_sek"] if prev else s["startvarde_sek"]),
        "sedan_omgangsstart": (snap.totalt_sek - bas) if bas else None,
        "omgangsstart_procent": (100 * (snap.totalt_sek / bas - 1)) if bas else None,
        "dagar_kvar": days_left(ctx),
        "att_kopiera": kopiera,
        "tankar": tankar,
        "sammanfattning": sammanfattning,
        "datum": str(today_se(ctx)),
    }
