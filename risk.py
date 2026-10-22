"""Riskplan före ett köp: var stoppet bör ligga, var likvidationen ligger och hur stor insatsen kan vara.

  python risk.py MYCR.ST                 # vanlig affär utan hävstång
  python risk.py MYCR.ST --havstang 15   # med hävstång
  python risk.py ERIC-B.ST --blanka --havstang 3
"""
import sys

from carl import db, engine, prices, risk


def main(a: list[str]) -> int:
    if not a:
        print(__doc__)
        return 1
    hav = float(a[a.index("--havstang") + 1]) if "--havstang" in a else 1.0
    blank = "--blanka" in a
    try:
        h = prices.history(a[0])
    except prices.PriceError as e:
        print(f"FEL: {e}")
        return 2
    with db.session() as conn:
        konto = engine.snapshot(engine.Ctx(conn)).totalt_sek
    p = risk.plan(a[0], h, konto, hav, blank)
    rikt = "BLANKNING" if blank else "KÖP"
    print(f"=== RISKPLAN {rikt} {p.ticker} à {p.pris:,.2f}, {p.havstang:g}x hävstång ===")
    print(f"Normal dagsrörelse (ATR):  {p.atr_procent:.1f} %")
    if p.likvidation_procent is not None:
        print(f"Likvidation vid:           {p.likvidation_pris:,.2f}  ({p.likvidation_procent:.1f} % bort, "
              f"≈ {p.likvidation_dagar:.1f} normala dagsrörelser)")
    else:
        print("Likvidation:               ingen (ingen hävstång)")
    print(f"Föreslaget stopp:          {p.stopp_pris:,.2f}  ({p.stopp_procent:.1f} % bort)")
    print(f"Nivå:                      {p.niva['namn']} – horisont {p.niva['horisont']}")
    print(f"Föreslagen egen insats:    {p.insats_kr[0]:,.0f}–{p.insats_kr[1]:,.0f} kr "
          f"({p.niva['insats_procent'][0]}–{p.niva['insats_procent'][1]} % av {konto:,.0f} kr)")
    print(f"Förlust om stoppet går:    ca {p.max_forlust_kr[0]:,.0f}–{p.max_forlust_kr[1]:,.0f} kr (+ courtage)")
    for w in p.varningar:
        print(f"⚠ {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
