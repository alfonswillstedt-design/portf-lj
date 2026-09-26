"""Carl-Gustafs portfölj.

  python portfolio.py status             # uppdaterar priser, räntor, likvidationer och visar allt
  python portfolio.py trades [N]         # de senaste N affärerna med motivering (standard 20)
  python portfolio.py haveri "text"      # obligatorisk haveri-analys efter konkurs
"""
import sys

from carl import db, engine
from trade import fmt


def status() -> int:
    with db.session() as conn:
        ctx = engine.Ctx(conn)
        rep = engine.update(ctx)
        s, acc, rnd = rep.snapshot, engine.account(ctx), engine.active_round(ctx)
        for liq in rep.likvidationer:
            print("⚠ " + fmt(liq))
        if rep.konkurs:
            print("💥 KONKURS! Kontot är nollställt. Skriv haveri-analysen: python portfolio.py haveri \"...\"")
        elif engine._pending_crash(ctx):
            print("💥 Haveri-analys saknas! Ingen handel förrän den är skriven: python portfolio.py haveri \"...\"")
        for r in rep.avslutade_omgangar:
            print(f"🏁 Omgång {r['id']} avslutad ({r['startdatum']}–{r['slutdatum']}): {r['slutvarde_sek']:,.2f} kr")
        print(f"\n=== CARL-GUSTAF  ({ctx.now.astimezone(engine.markets.SE_TZ):%Y-%m-%d %H:%M} svensk tid) ===")
        print(f"Totalt värde:  {s.totalt_sek:>14,.2f} kr")
        print(f"Kassa:         {s.kassa_sek:>14,.2f} kr")
        if rnd:
            bas = rnd["startvarde_sek"] + rnd["tillskott_sek"]
            print(f"Omgång {rnd['id']}:      {rnd['startdatum']} – {rnd['slutdatum']}  ({engine.days_left(ctx)} dagar kvar)")
            print(f"Sedan start:   {s.totalt_sek - bas:>+14,.2f} kr  ({100 * (s.totalt_sek / bas - 1):+.2f} %)")
        else:
            print("Ingen aktiv omgång – starta med: python round.py start")
        print(f"Konkurser:     {acc['konkurser']:>14}")
        print(f"Avgifter tot:  {acc['avgifter_sek']:>14,.2f} kr" + (f"  (varav räntor denna körning {rep.kostnader_sek:.2f})" if rep.kostnader_sek else ""))
        if s.positioner:
            print(f"\n{'Ticker':<16}{'Antal':>8}{'Snitt':>12}{'Nu':>12}{'Värde kr':>13}{'Res kr':>12}{'Res %':>8}{'Häv':>6}{'Likv.pris':>11}  Prisålder")
            for p in s.positioner:
                print(f"{p.ticker:<16}{p.antal:>8g}{p.snittpris:>12,.2f}{p.pris:>12,.2f}{p.eget_kapital_sek:>13,.0f}"
                      f"{p.resultat_sek:>+12,.0f}{p.resultat_procent:>+8.1f}{p.havstang:>5.1f}x"
                      f"{(f'{p.likvidationspris:,.2f}' if p.likvidationspris else '-'):>11}  {p.prisalder}"
                      + ("  (BLANKAD)" if p.antal < 0 else ""))
        else:
            print("\nInga innehav.")
        for w in s.varningar:
            print("! " + w)
    return 0


def trades(n: int) -> int:
    with db.session() as conn:
        engine.Ctx(conn)
        rows = conn.execute("SELECT * FROM trades WHERE agent_id='carl' ORDER BY id DESC LIMIT ?", (n,)).fetchall()
        if not rows:
            print("Inga affärer än.")
        for t in rows:
            res = f"  resultat {t['resultat_sek']:+,.2f} kr" if t["resultat_sek"] is not None else ""
            print(f"#{t['id']} {t['tid'][:16]}  {t['handling'].upper():<11} {t['antal']:g} {t['ticker']} à "
                  f"{t['pris']:,.2f} {t['valuta']}  {t['havstang']:g}x  avg {t['avgift_sek']:.2f}{res}")
            if t["motivering"]:
                print(f"     ↳ {t['motivering']}")
    return 0


def haveri(text: str) -> int:
    with db.session() as conn:
        try:
            n = engine.write_crash_analysis(engine.Ctx(conn), text)
        except engine.TradeError as e:
            print(f"AVVISAD: {e}")
            return 2
        print(f"Haveri-analys för konkurs #{n} sparad i databasen och i data/lardomar.md. Carl får handla igen.")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "status":
        sys.exit(status())
    if args[0] == "trades":
        sys.exit(trades(int(args[1]) if len(args) > 1 else 20))
    if args[0] == "haveri" and len(args) > 1:
        sys.exit(haveri(" ".join(args[1:])))
    print(__doc__)
    sys.exit(1)
