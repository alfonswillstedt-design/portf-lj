"""Fas 3: indikatorer, statistik, lärdomar och sessioner (påhittad data)."""
import numpy as np
import pandas as pd
import pytest

from carl import engine, indicators, journal, stats
from test_fas2 import MANDAG_10, world  # noqa: F401  (fixture)


def serie(values):
    idx = pd.date_range("2025-01-01", periods=len(values), freq="B")
    c = pd.Series(values, index=idx, dtype=float)
    return pd.DataFrame({"Close": c, "High": c * 1.01, "Low": c * 0.99, "Volume": 1000.0})


def test_rsi_extremer():
    upp = indicators.rsi(pd.Series(np.arange(1, 60, dtype=float)))
    ner = indicators.rsi(pd.Series(np.arange(60, 1, -1, dtype=float)))
    assert upp.iloc[-1] > 95 and ner.iloc[-1] < 5


def test_rsi_kant_varde():
    # Klassiskt exempel: växlande +1/-1 ger RSI runt 50
    s = pd.Series([10 + (i % 2) for i in range(100)], dtype=float)
    assert 40 < indicators.rsi(s).iloc[-1] < 60


def test_sammanfattning_upptrend_och_signaler():
    h = serie(np.linspace(100, 200, 300))
    s = indicators.summarize("TEST", h)
    assert s.sma20 > s.sma50 > s.sma200
    assert s.rsi14 > 70 and "överköpt" in " ".join(s.signaler)
    assert "Långsiktig upptrend" in " ".join(s.signaler)
    assert s.avk_1a == pytest.approx(100 * (200 / h["Close"].iloc[-253] - 1))
    assert s.fran_hogsta_procent == pytest.approx(0)


def test_hog_volym_signal():
    h = serie(np.linspace(100, 110, 60))
    h.iloc[-1, h.columns.get_loc("Volume")] = 5000.0
    assert "Ovanligt hög volym" in " ".join(indicators.summarize("T", h).signaler)


def test_for_kort_historik():
    with pytest.raises(ValueError):
        indicators.summarize("T", serie([1, 2, 3]))


def test_statistik_och_lardomar(world):
    conn, m, ctx = world
    engine.open_position(ctx(), "VOLV-B.ST", 100, strategi="momentum")
    m.p["VOLV-B.ST"] = (120.0, "SEK")
    vinst = engine.close_position(ctx(), "VOLV-B.ST")
    engine.open_position(ctx(), "ERIC-B.ST", 200, "blankad", havstang=2, strategi="nyhet")
    m.p["ERIC-B.ST"] = (55.0, "SEK")
    engine.close_position(ctx(), "ERIC-B.ST")
    st = stats.compute(conn)
    assert st.totalt.antal == 2 and st.totalt.vinster == 1 and st.totalt.traffsakerhet == 50
    assert set(st.per_strategi) == {"momentum", "nyhet"}
    assert "1–2x" in st.per_havstang and "blankning" in st.per_riktning
    assert len(st.saknar_lardom) == 2
    assert "<5 %" in "".join(st.per_storlek) or "5–15 %" in st.per_storlek
    tid = conn.execute("SELECT id FROM trades WHERE handling='sell'").fetchone()["id"]
    with pytest.raises(engine.TradeError):
        journal.add_lesson(ctx(), tid, "kort")
    journal.add_lesson(ctx(), tid, "Momentum i Volvo höll hela vägen, rätt att låta vinnaren löpa.")
    assert len(stats.compute(conn).saknar_lardom) == 1
    text = journal.read_lessons(ctx())
    assert "✅" in text and "Momentum i Volvo" in text and "Kärnlärdomar" in text
    assert "Träffsäkerhet: 50 %" in stats.format_stats(st)
    # Lärdom kan bara skrivas för avslutade affärer
    kop = conn.execute("SELECT id FROM trades WHERE handling='buy'").fetchone()["id"]
    with pytest.raises(engine.TradeError, match="avslutad"):
        journal.add_lesson(ctx(), kop, "Det här är ett köp och har inget resultat än.")


def test_session_och_att_kopiera(world):
    conn, m, ctx = world
    engine.start_round(ctx(), engine.date(2026, 12, 31))
    s, nr, ny = journal.start_session(ctx())
    assert nr == 1 and ny
    s2, _, ny2 = journal.start_session(ctx())
    assert s2["id"] == s["id"] and not ny2                     # återupptas, ingen dubblett
    engine.open_position(ctx(), "VOLV-B.ST", 50, motivering="stark rapport")
    engine.open_position(ctx(), "ERIC-B.ST", 100, "blankad", havstang=3)
    m.p["VOLV-B.ST"] = (110.0, "SEK")
    r = journal.end_session(ctx(), "Bra dag.", "Blankningen i ERIC görs med BEAR ERICSSON X3.", "Bevaka Volvo.")
    assert "1. KÖP 50 st VOLV-B.ST à ca 100,00 SEK (≈ 5 000 kr)" in r["att_kopiera"]
    assert "2. BLANKA 100 st ERIC-B.ST" in r["att_kopiera"] and "certifikat" in r["att_kopiera"]
    assert "BEAR ERICSSON X3" in r["att_kopiera"]
    assert r["sedan_forra"] == pytest.approx(r["varde"] - 100000)
    assert r["dagar_kvar"] == 94
    assert engine.active_session(ctx()) is None
    # Nästa session utan affärer
    journal.start_session(ctx())
    r2 = journal.end_session(ctx(), "Lugnt.", None, None)
    assert "Inga affärer" in r2["att_kopiera"] and r2["sedan_forra"] == pytest.approx(0, abs=0.01)
