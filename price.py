"""Hämta priser.

  python price.py VOLV-B.ST AAPL BITCOIN-XBT.ST    # ett eller flera priser, även i SEK
  python price.py fx USD EUR             # valutakurser mot SEK
  python price.py test                   # testar alla datakällor
"""
import sys

from carl import db, prices


def show(ticker: str, conn=None) -> bool:
    try:
        q, fx = prices.get_quote_sek(ticker)
    except prices.PriceError as e:
        print(f"{ticker:<12} FEL: {e}")
        return False
    sek = q.pris * fx.pris
    extra = f"  = {sek:,.2f} SEK (kurs {fx.pris:.4f})" if q.valuta != "SEK" else ""
    print(f"{q.ticker:<12} {q.pris:>14,.4f} {q.valuta}{extra}   [{q.kalla}, {q.alder_text()} gammalt]")
    if conn is not None:
        prices.save_quote(conn, q)
    return True


def main(args: list[str]) -> int:
    if not args:
        print(__doc__)
        return 1
    if args[0] == "fx":
        ok = True
        for v in args[1:] or ["USD", "EUR"]:
            try:
                q = prices.fx_rate(v)
                print(f"{v}/SEK  {q.pris:.4f}   [{q.kalla}, {q.alder_text()} gammalt]")
            except prices.PriceError as e:
                print(f"{v}/SEK  FEL: {e}")
                ok = False
        return 0 if ok else 2
    if args[0] == "test":
        args = ["VOLV-B.ST", "ERIC-B.ST", "NOKIA.HE", "AAPL", "NVDA", "BITCOIN-XBT.ST"]
        print("Testar datakällor (Yahoo Finance):")
    with db.session() as conn:
        db.init(conn)
        results = [show(t, conn) for t in args]
    return 0 if all(results) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
