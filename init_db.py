"""Skapar databasen och Carl-Gustafs konto (100 000 kr) om de inte redan finns.

  python init_db.py
"""
from carl import db

with db.session() as conn:
    db.ensure_agent(conn)
    a = conn.execute("SELECT * FROM accounts WHERE agent_id='carl'").fetchone()
    print(f"Databasen är klar. Carl-Gustaf har {a['kassa_sek']:,.2f} kr i kassa, {a['konkurser']} konkurser.")
