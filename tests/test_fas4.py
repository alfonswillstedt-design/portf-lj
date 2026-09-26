"""Fas 4: dashboardens data och ögonblicksbild."""
import json

import pytest

from carl import dashboard_data, engine, journal
from dashboard import build
from test_fas2 import world  # noqa: F401


def test_dashboard_data_och_html(world):
    conn, m, ctx = world
    engine.start_round(ctx(), engine.date(2026, 12, 31))
    journal.start_session(ctx())
    engine.open_position(ctx(), "VOLV-B.ST", 100, motivering="Stark rapport </script> test")
    engine.open_position(ctx(), "ERIC-B.ST", 100, "blankad", havstang=2)
    engine.update(ctx())
    journal.end_session(ctx(), "Test.", None, "Bevaka Volvo.")
    m.p["VOLV-B.ST"] = (110.0, "SEK")
    engine.update(ctx())                        # sparar nytt pris i databasen
    d = dashboard_data.build(conn)
    assert len(d["positioner"]) == 2
    volvo = next(p for p in d["positioner"] if p["ticker"] == "VOLV-B.ST")
    assert volvo["pris"] == 110.0 and volvo["resultat_sek"] == pytest.approx(1000 - 25)
    blank = next(p for p in d["positioner"] if p["ticker"] == "ERIC-B.ST")
    assert blank["riktning"] == "blankad" and blank["likvidationspris"]
    assert d["totalt"] == pytest.approx(engine.snapshot(ctx()).totalt_sek)
    assert d["omgang"]["dagar_kvar"] >= 0 and "KÖP 100 st VOLV-B.ST" in d["senaste_session"]["att_kopiera"]
    html = build.render(d)
    assert "/*__CARL_DATA__*/" not in html and "</script> test" not in html   # ingen script-injektion
    blob = html.split("const EMBEDDED = ", 1)[1].split(";\nconst TZ", 1)[0]
    assert json.loads(blob.replace("<\\/", "</"))["totalt"] == pytest.approx(d["totalt"])
