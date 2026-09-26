"""Lägg en (simulerad) order. Allt går till priser hämtade via prisskripten.

  python trade.py buy   VOLV-B.ST 50 -m "motivering"               # köp 50 st
  python trade.py buy   VOLV-B.ST --belopp 10000 -m "..."           # köp för 10 000 kr egen insats
  python trade.py buy   NVDA 20 --havstang 2 -m "..."               # köp med 2x hävstång
  python trade.py sell  VOLV-B.ST 20 -m "..."                       # sälj 20 st (eller 'all')
  python trade.py short ERIC-B.ST 100 --havstang 2 -m "..."         # blanka
  python trade.py cover ERIC-B.ST all -m "..."                      # köp tillbaka blankade

Tillval: --strategi NAMN (t.ex. momentum, nyhet, rapport, mean-reversion), --session ID
"""
import argparse
import sys

from carl import db, engine
from carl.prices import PriceError


def fmt(r: engine.TradeResult) -> str:
    namn = {"buy": "KÖPT", "sell": "SÅLT", "short": "BLANKAT", "cover": "TÄCKT", "liquidation": "LIKVIDERAT"}
    s = (f"{namn[r.handling]}: {r.antal:g} st {r.ticker} à {r.pris:,.4f} {r.valuta}"
         + (f" (kurs {r.valutakurs:.4f})" if r.valuta != "SEK" else "")
         + f" = {r.varde_sek:,.2f} kr, avgift {r.avgift_sek:,.2f} kr, hävstång {r.havstang:g}x")
    if r.resultat_sek is not None:
        s += f", resultat {r.resultat_sek:+,.2f} kr"
    s += f". Kassa nu {r.kassa_efter:,.2f} kr."
    for w in r.varningar:
        s += f"\n  ! {w}"
    return s


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("handling", choices=["buy", "sell", "short", "cover"])
    ap.add_argument("ticker")
    ap.add_argument("antal", nargs="?", help="antal aktier, eller 'all' vid sell/cover")
    ap.add_argument("--belopp", type=float, help="egen insats i SEK i stället för antal (buy/short)")
    ap.add_argument("--havstang", type=float, default=1.0)
    ap.add_argument("-m", "--motivering", required=True, help="VARFÖR – obligatoriskt")
    ap.add_argument("--strategi")
    ap.add_argument("--session", type=int)
    a = ap.parse_args(argv)

    with db.session() as conn:
        ctx = engine.Ctx(conn)
        rep = engine.update(ctx)
        for liq in rep.likvidationer:
            print("⚠ " + fmt(liq))
        if rep.konkurs:
            print("💥 KONKURS! Skriv haveri-analysen: python portfolio.py haveri \"...\"")
            return 3
        conn.commit()
        try:
            if a.handling in ("buy", "short"):
                if a.belopp:
                    antal = engine.shares_for_amount(ctx, a.ticker, a.belopp, a.havstang)
                    if antal < 1:
                        raise engine.TradeError("Beloppet räcker inte till en enda aktie.")
                elif a.antal:
                    antal = float(a.antal)
                else:
                    raise engine.TradeError("Ange antal eller --belopp.")
                r = engine.open_position(ctx, a.ticker, antal, "lång" if a.handling == "buy" else "blankad",
                                         a.havstang, a.motivering, a.strategi, a.session)
            else:
                pos = engine._position(ctx, a.ticker)
                if pos and ((a.handling == "sell") != (pos["antal"] > 0)):
                    raise engine.TradeError(
                        f"{a.ticker} är en {'lång' if pos['antal'] > 0 else 'blankad'} position – använd "
                        f"'{'sell' if pos['antal'] > 0 else 'cover'}'.")
                antal = None if (a.antal in (None, "all")) else float(a.antal)
                r = engine.close_position(ctx, a.ticker, antal, a.motivering, a.strategi, a.session)
        except (engine.TradeError, PriceError) as e:
            print(f"AVVISAD: {e}")
            return 2
        print(fmt(r))
        if engine.check_bankruptcy(ctx):
            print("💥 KONKURS! Skriv haveri-analysen: python portfolio.py haveri \"...\"")
        engine.record_equity(ctx)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
