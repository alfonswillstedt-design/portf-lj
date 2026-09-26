"""Carls statistik: träffsäkerhet, snittvinst/-förlust, per strategi, hävstång och positionsstorlek.

  python stats.py
"""
from carl import db, stats

with db.session() as conn:
    db.ensure_agent(conn)
    print(stats.format_stats(stats.compute(conn)))
