"""Carls sessioner.

  python session.py start                                   # briefing: marknader, portfölj, statistik, lärdomar
  python session.py slut --sammanfattning "..." [--kopiera "..."] [--tankar "..."]
  python session.py senaste                                 # visa senaste sessionens sammanfattning
"""
import argparse
import sys

from carl import db, engine, journal, markets, stats
from portfolio import print_status


def start() -> int:
    with db.session() as conn:
        ctx = engine.Ctx(conn)
        s, nr, ny = journal.start_session(ctx)
        print(f"################ SESSION {nr} {'startad' if ny else 'ÅTERUPPTAGEN (förra avslutades inte)'} ################")
        print("\n--- MARKNADER ---")
        for m in markets.all_status(ctx.now):
            print(f"{m.namn:<20} " + (f"ÖPPEN (stänger {m.stanger:%H:%M})" if m.oppen
                                      else f"stängd – öppnar {m.nasta_oppning:%a %d/%m %H:%M}"))
        print("\n--- PORTFÖLJ (priser uppdaterade, räntor dragna, likvidationer kontrollerade) ---")
        rep = engine.update(ctx)
        print_status(ctx, rep)
        prev = journal.previous_session(ctx, s["id"])
        if prev:
            print(f"\nFörra sessionen ({prev['slut'][:16]}): {prev['slutvarde_sek']:,.2f} kr -> nu "
                  f"{rep.snapshot.totalt_sek - prev['slutvarde_sek']:+,.2f} kr")
            if prev["tankar"]:
                print(f"Dina tankar då: {prev['tankar']}")
        print("\n--- STATISTIK ---")
        print(stats.format_stats(stats.compute(conn)))
        print("\n--- LÄRDOMAR (data/lardomar.md) ---")
        print(journal.read_lessons(ctx))
        if nr % 5 == 0 and ny:
            print("🧹 DAGS ATT STÄDA: detta är session nr", nr, "– sammanfatta och rensa data/lardomar.md "
                  "(uppdatera kärnlärdomarna, ta bort gamla loggposter, behåll ALLA haveri-analyser).")
        if engine._pending_crash(ctx):
            print("💥 HAVERI-ANALYS SAKNAS – skriv den först: python portfolio.py haveri \"...\"")
    return 0


def slut(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sammanfattning", required=True)
    ap.add_argument("--kopiera", help="anvisning för hur affärerna görs i tävlingen (t.ex. vilket certifikat)")
    ap.add_argument("--tankar", help="tankar inför nästa session")
    a = ap.parse_args(argv)
    with db.session() as conn:
        ctx = engine.Ctx(conn)
        engine.update(ctx)
        try:
            r = journal.end_session(ctx, a.sammanfattning, a.kopiera, a.tankar)
        except engine.TradeError as e:
            print(f"AVVISAD: {e}")
            return 2
    print_summary(r)
    return 0


def print_summary(r: dict) -> None:
    print(f"=============== SESSION #{r['session_id']} KLAR ({r['datum']}) ===============")
    print(f"Portföljvärde:        {r['varde']:,.2f} kr   (kassa {r['kassa']:,.2f} kr)")
    print(f"Sedan förra sessionen: {r['sedan_forra']:+,.2f} kr")
    if r["sedan_omgangsstart"] is not None:
        print(f"Sedan omgångens start: {r['sedan_omgangsstart']:+,.2f} kr ({r['omgangsstart_procent']:+.2f} %), "
              f"{r['dagar_kvar']} dagar kvar")
    print("\n>>> ATT KOPIERA TILL TÄVLINGEN <<<")
    print(r["att_kopiera"])
    if r.get("tankar"):
        print(f"\nInför nästa session: {r['tankar']}")


def senaste() -> int:
    with db.session() as conn:
        ctx = engine.Ctx(conn)
        s = journal.previous_session(ctx)
        if not s:
            print("Ingen avslutad session än.")
            return 0
        print(f"Session #{s['id']} ({s['slut'][:16]}), värde {s['slutvarde_sek']:,.2f} kr")
        print(f"\n{s['sammanfattning']}\n\n>>> ATT KOPIERA TILL TÄVLINGEN <<<\n{s['att_kopiera']}")
        if s["tankar"]:
            print(f"\nInför nästa session: {s['tankar']}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "start":
        sys.exit(start())
    if cmd == "slut":
        sys.exit(slut(args[1:]))
    if cmd == "senaste":
        sys.exit(senaste())
    print(__doc__)
    sys.exit(1)
