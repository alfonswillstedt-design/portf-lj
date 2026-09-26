"""Tradedagbok och lärdomar.

  python journal.py lardom 12 "Köpte på rapportsläpp men..."   # lärdom för avslutad affär #12
  python journal.py lardomar                                   # läs hela lärdomsfilen
  python journal.py affar 12                                   # all info om affär #12
  python journal.py saknas                                     # avslutade affärer utan lärdom
"""
import sys

from carl import db, engine, journal, stats


def main(a: list[str]) -> int:
    if not a:
        print(__doc__)
        return 1
    with db.session() as conn:
        ctx = engine.Ctx(conn)
        if a[0] == "lardom" and len(a) >= 3:
            try:
                journal.add_lesson(ctx, int(a[1]), " ".join(a[2:]))
            except engine.TradeError as e:
                print(f"AVVISAD: {e}")
                return 2
            print(f"Lärdom sparad för affär #{a[1]} (databas + data/lardomar.md).")
        elif a[0] == "lardomar":
            print(journal.read_lessons(ctx))
        elif a[0] == "affar" and len(a) == 2:
            t = conn.execute("SELECT * FROM trades WHERE id=?", (int(a[1]),)).fetchone()
            if not t:
                print("Ingen sådan affär.")
                return 2
            for k in t.keys():
                if t[k] is not None:
                    print(f"{k:<15} {t[k]}")
        elif a[0] == "saknas":
            st = stats.compute(conn)
            if not st.saknar_lardom:
                print("Alla avslutade affärer har en lärdom. 👍")
            for t in st.saknar_lardom:
                print(f"#{t['id']} {t['tid'][:10]} {t['handling']} {t['ticker']} {t['resultat_sek']:+,.0f} kr  "
                      f"motivering: {t['motivering'] or '-'}")
        else:
            print(__doc__)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
