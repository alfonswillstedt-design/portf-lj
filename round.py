"""Omgångar (3 månader, slutar 31 mars / 30 juni / 30 sep / 31 dec).
Portföljen följer med mellan omgångarna – bara ett mellanresultat sparas.

  python round.py start [--slut ÅÅÅÅ-MM-DD]   # starta en omgång (standard: nästa kvartalsslut)
  python round.py status                       # aktiv omgång och dagar kvar
  python round.py historik                     # alla omgångar och resultat
"""
import sys
from datetime import date

from carl import db, engine


def main(args: list[str]) -> int:
    cmd = args[0] if args else "status"
    with db.session() as conn:
        ctx = engine.Ctx(conn)
        if cmd == "start":
            slut = date.fromisoformat(args[args.index("--slut") + 1]) if "--slut" in args else None
            try:
                r = engine.start_round(ctx, slut)
            except engine.TradeError as e:
                print(f"AVVISAD: {e}")
                return 2
            print(f"Omgång {r['id']} startad: {r['startdatum']} – {r['slutdatum']}, startvärde {r['startvarde_sek']:,.2f} kr")
        elif cmd == "status":
            r = engine.active_round(ctx)
            if not r:
                print("Ingen aktiv omgång.")
            else:
                print(f"Omgång {r['id']}: {r['startdatum']} – {r['slutdatum']}, {engine.days_left(ctx)} dagar kvar. "
                      f"Startvärde {r['startvarde_sek']:,.2f} kr.")
        elif cmd == "historik":
            for r in conn.execute("SELECT * FROM rounds WHERE agent_id='carl' ORDER BY id"):
                bas = r["startvarde_sek"] + r["tillskott_sek"]
                slut = f"{r['slutvarde_sek']:,.2f} kr ({100 * (r['slutvarde_sek'] / bas - 1):+.2f} %)" if r["slutvarde_sek"] else "pågår"
                print(f"Omgång {r['id']}: {r['startdatum']} – {r['slutdatum']}  start {r['startvarde_sek']:,.2f} kr  slut {slut}")
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
