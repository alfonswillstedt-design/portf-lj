"""Vilka börser är öppna just nu?

  python market.py              # status för alla börser
  python market.py VOLV-B.ST    # går just den här tickern att handla nu?
"""
import sys

from carl import markets


def main(args: list[str]) -> int:
    if args:
        for t in args:
            s = markets.status(markets.exchange_for(t))
            print(f"{t}: {s.namn} – {'ÖPPEN' if s.oppen else 'STÄNGD'}"
                  + (f", öppnar {s.nasta_oppning:%a %Y-%m-%d %H:%M} svensk tid" if not s.oppen else ""))
        return 0
    for s in markets.all_status():
        if s.oppen:
            info = f"ÖPPEN" + (f" (stänger {s.stanger:%H:%M} svensk tid)" if s.stanger else "")
        else:
            info = f"stängd – öppnar {s.nasta_oppning:%a %Y-%m-%d %H:%M} svensk tid"
        print(f"{s.namn:<20} {info}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
