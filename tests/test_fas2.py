"""Fas 2: handelsmotorn testad med påhittade scenarier (inga riktiga priser)."""
from datetime import datetime, timedelta, timezone

import pytest

from carl import db, engine, markets
from carl.prices import PriceError, Quote

MANDAG_10 = datetime(2026, 9, 28, 10, 0, tzinfo=markets.SE_TZ).astimezone(timezone.utc)
LORDAG = datetime(2026, 9, 26, 12, 0, tzinfo=markets.SE_TZ).astimezone(timezone.utc)
FX = {"SEK": 1.0, "USD": 10.0}


class Market:
    """Påhittad marknad: priser vi styr själva."""
    def __init__(self, **priser):
        self.p = {k.replace("_", "-").replace("-ST", ".ST"): v for k, v in priser.items()}

    def __call__(self, ticker):
        if ticker not in self.p:
            raise PriceError(f"inget pris för {ticker}")
        pris, val = self.p[ticker]
        now = datetime.now(timezone.utc)
        return Quote(ticker, pris, val, now, "test"), Quote(val, FX[val], "SEK", now, "test")


@pytest.fixture
def world(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    m = Market(VOLV_B_ST=(100.0, "SEK"), ERIC_B_ST=(50.0, "SEK"), AAPL=(200.0, "USD"))

    def ctx(now=MANDAG_10):
        return engine.Ctx(conn, quote_fn=m, now=now, lardomar_path=tmp_path / "lardomar.md")
    yield conn, m, ctx
    conn.close()


def cash(c):
    return engine.account(c)["kassa_sek"]


# ---------- Grundläggande köp och sälj ----------

def test_kop_och_salj_med_courtage(world):
    conn, m, ctx = world
    c = ctx()
    r = engine.open_position(c, "VOLV-B.ST", 100, motivering="test")
    assert r.varde_sek == 10000 and r.avgift_sek == 25.0          # 0,25 %
    assert cash(c) == pytest.approx(100000 - 10025)
    m.p["VOLV-B.ST"] = (110.0, "SEK")
    r = engine.close_position(ctx(), "VOLV-B.ST")
    assert r.avgift_sek == 27.5
    assert r.resultat_sek == pytest.approx(11000 - 27.5 - 10025)   # vinst efter båda avgifterna
    assert cash(c) == pytest.approx(100000 + 1000 - 25 - 27.5)
    assert engine.positions(c) == []


def test_minsta_courtage_1_kr(world):
    _, _, ctx = world
    r = engine.open_position(ctx(), "ERIC-B.ST", 1)
    assert r.avgift_sek == 1.0


def test_utlandsk_aktie_valutaavgift(world):
    _, _, ctx = world
    usa_oppen = MANDAG_10 + timedelta(hours=6)                      # 16:00 svensk tid
    r = engine.open_position(ctx(usa_oppen), "AAPL", 10)            # 10 * 200 USD * 10 = 20 000 kr
    assert r.varde_sek == 20000
    assert r.avgift_sek == pytest.approx(50 + 50)                   # courtage 0,25 % + växling 0,25 %


def test_delforsaljning(world):
    _, m, ctx = world
    engine.open_position(ctx(), "VOLV-B.ST", 100)
    engine.close_position(ctx(), "VOLV-B.ST", 40)
    (p,) = engine.positions(ctx())
    assert p["antal"] == 60 and p["kostnad_sek"] == pytest.approx(6000)


def test_okar_position_snittpris(world):
    _, m, ctx = world
    engine.open_position(ctx(), "VOLV-B.ST", 100)
    m.p["VOLV-B.ST"] = (120.0, "SEK")
    engine.open_position(ctx(), "VOLV-B.ST", 100)
    (p,) = engine.positions(ctx())
    assert p["antal"] == 200 and p["snittpris"] == pytest.approx(110)


# ---------- Avvisningar ----------

def test_for_lite_pengar_avvisas_kontot_aldrig_negativt(world):
    _, _, ctx = world
    with pytest.raises(engine.TradeError, match="För lite pengar"):
        engine.open_position(ctx(), "VOLV-B.ST", 1000)               # 100 000 + avgift > kassan
    assert cash(ctx()) == 100000


def test_stangd_borse_avvisas(world):
    _, _, ctx = world
    with pytest.raises(engine.TradeError, match="stängd"):
        engine.open_position(ctx(LORDAG), "VOLV-B.ST", 10)
    with pytest.raises(engine.TradeError, match="stängd"):
        engine.open_position(ctx(), "AAPL", 1)                        # USA öppnar 15:30


def test_inget_pris_ingen_affar(world):
    _, _, ctx = world
    with pytest.raises(PriceError):
        engine.open_position(ctx(), "FINNSINTE.ST", 10)
    assert cash(ctx()) == 100000 and engine.positions(ctx()) == []


def test_kan_inte_salja_det_man_inte_har(world):
    _, _, ctx = world
    with pytest.raises(engine.TradeError):
        engine.close_position(ctx(), "VOLV-B.ST")
    engine.open_position(ctx(), "VOLV-B.ST", 10)
    with pytest.raises(engine.TradeError):
        engine.close_position(ctx(), "VOLV-B.ST", 11)
    with pytest.raises(engine.TradeError, match="Stäng den först"):
        engine.open_position(ctx(), "VOLV-B.ST", 5, "blankad")


def test_inga_tak_pa_storlek_eller_havstang(world):
    _, _, ctx = world
    r = engine.open_position(ctx(), "VOLV-B.ST", 9700, havstang=10)   # 970 000 kr position på 97 000 kr insats
    assert r.varde_sek == 970000


# ---------- Hävstång och likvidation ----------

def test_havstang_vinst_forstarks(world):
    _, m, ctx = world
    engine.open_position(ctx(), "VOLV-B.ST", 500, havstang=2)       # 50 000 kr, 25 000 egen insats
    assert cash(ctx()) == pytest.approx(100000 - 25000 - 125)
    m.p["VOLV-B.ST"] = (110.0, "SEK")                                # +10 % -> +5000 kr = +20 % på insatsen
    s = engine.snapshot(ctx())
    assert s.positioner[0].eget_kapital_sek == pytest.approx(55000 - 25000)
    assert s.totalt_sek == pytest.approx(100000 - 125 + 5000)


def test_likvidationspris_lang(world):
    _, _, ctx = world
    engine.open_position(ctx(), "VOLV-B.ST", 500, havstang=2)       # lån 25 000
    (p,) = engine.positions(ctx())
    # 500*P - 25000 = 0.05 * 500*P  ->  P = 25000 / (500*0.95)
    assert p["likvidationspris"] == pytest.approx(25000 / 475)


def test_lang_med_havstang_likvideras_korrekt(world):
    _, m, ctx = world
    engine.open_position(ctx(), "VOLV-B.ST", 500, havstang=2)
    m.p["VOLV-B.ST"] = (53.0, "SEK")                                 # strax över likvidation (52,63)
    assert engine.update(ctx()).likvidationer == []
    m.p["VOLV-B.ST"] = (52.0, "SEK")                                 # under -> margin call
    rep = engine.update(ctx())
    assert len(rep.likvidationer) == 1 and rep.likvidationer[0].handling == "liquidation"
    assert engine.positions(ctx()) == []
    # Tillbaka: 500*52 - 25000 - courtage(65) = 935 kr
    assert cash(ctx()) == pytest.approx(100000 - 25125 + 26000 - 25000 - 65)
    t = world[0].execute("SELECT * FROM trades WHERE handling='liquidation'").fetchone()
    assert "MARGIN CALL" in t["motivering"]


def test_kursras_forbi_likvidation_kontot_aldrig_under_noll(world):
    """Aktien rasar 90 % över en natt (långt förbi likvidationsnivån). Förlusten större än
    säkerheten får aldrig göra kontot negativt."""
    _, m, ctx = world
    engine.open_position(ctx(), "VOLV-B.ST", 9700, havstang=10)     # allt in med 10x
    m.p["VOLV-B.ST"] = (10.0, "SEK")
    rep = engine.update(ctx())
    assert rep.likvidationer and cash(ctx()) >= 0
    assert rep.konkurs                                               # kontot tomt -> konkurs


# ---------- Blankning ----------

def test_blankning_vinst_nar_kursen_faller(world):
    _, m, ctx = world
    engine.open_position(ctx(), "ERIC-B.ST", 1000, "blankad")        # 50 000 kr, säkerhet 50 000
    m.p["ERIC-B.ST"] = (40.0, "SEK")
    r = engine.close_position(ctx(), "ERIC-B.ST")
    assert r.handling == "cover"
    assert r.resultat_sek == pytest.approx(10000 - 125 - 100)
    assert cash(ctx()) == pytest.approx(100000 + 10000 - 125 - 100)


def test_blankning_likvideras_nar_kursen_stiger(world):
    _, m, ctx = world
    engine.open_position(ctx(), "ERIC-B.ST", 1000, "blankad", havstang=2)  # säkerhet 25 000
    (p,) = engine.positions(ctx())
    lp = p["likvidationspris"]
    assert lp == pytest.approx(75000 / (1000 * 1.05))                # 71,43
    m.p["ERIC-B.ST"] = (lp + 0.5, "SEK")
    rep = engine.update(ctx())
    assert len(rep.likvidationer) == 1 and cash(ctx()) >= 0


def test_blankningsavgift_och_laneranta_dras_over_tid(world):
    _, _, ctx = world
    engine.open_position(ctx(), "ERIC-B.ST", 1000, "blankad")        # 50 000 blankat
    engine.open_position(ctx(), "VOLV-B.ST", 200, havstang=2)       # lån 10 000
    engine.update(ctx())                                             # startar räkningen
    before = cash(ctx())
    rep = engine.update(ctx(MANDAG_10 + timedelta(days=365)))
    # 50 000 * 3 % + 10 000 * 6 % = 1500 + 600
    assert rep.kostnader_sek == pytest.approx(2100)
    assert cash(ctx()) == pytest.approx(before - 2100)


# ---------- Konkurs ----------

def test_konkurs_haveri_analys_och_nollstallning(world):
    conn, m, ctx = world
    engine.start_round(ctx())
    engine.open_position(ctx(), "VOLV-B.ST", 9700, havstang=10)
    m.p["VOLV-B.ST"] = (5.0, "SEK")
    rep = engine.update(ctx())
    assert rep.konkurs
    acc = engine.account(ctx())
    assert acc["konkurser"] == 1 and acc["kassa_sek"] == 100000     # nollställt
    # Ingen handel förrän haveri-analysen är skriven
    m.p["VOLV-B.ST"] = (100.0, "SEK")
    with pytest.raises(engine.TradeError, match="haveri"):
        engine.open_position(ctx(), "VOLV-B.ST", 1)
    with pytest.raises(engine.TradeError, match="för kort"):
        engine.write_crash_analysis(ctx(), "oj")
    engine.write_crash_analysis(ctx(), "Jag satsade hela kontot med 10x hävstång i en enda aktie. "
                                       "Aldrig mer än en bråkdel av kapitalet med så hög hävstång.")
    text = (world[2]().lardomar_path).read_text(encoding="utf-8")
    assert "HAVERI-ANALYS – KONKURS #1" in text
    engine.open_position(ctx(), "VOLV-B.ST", 1)                       # nu går det igen
    # Tillskottet räknas bort från omgångens avkastning
    rnd = engine.active_round(ctx())
    assert rnd["tillskott_sek"] > 99000


# ---------- Omgångar ----------

def test_omgangar_fortsatter_med_samma_portfolj(world):
    conn, m, ctx = world
    r = engine.start_round(ctx(), engine.date(2026, 12, 31))
    assert engine.days_left(ctx()) == (engine.date(2026, 12, 31) - engine.date(2026, 9, 28)).days
    engine.open_position(ctx(), "VOLV-B.ST", 100)
    m.p["VOLV-B.ST"] = (150.0, "SEK")
    jan2 = datetime(2027, 1, 2, 12, 0, tzinfo=timezone.utc)
    rep = engine.update(ctx(jan2))
    assert len(rep.avslutade_omgangar) == 1
    gammal = conn.execute("SELECT * FROM rounds WHERE id=?", (r["id"],)).fetchone()
    assert gammal["status"] == "avslutad" and gammal["slutvarde_sek"] == pytest.approx(rep.snapshot.totalt_sek)
    ny = engine.active_round(ctx(jan2))
    assert ny["startdatum"] == "2027-01-01" and ny["slutdatum"] == "2027-03-31"
    assert ny["startvarde_sek"] == pytest.approx(gammal["slutvarde_sek"])   # ingen nollställning
    assert len(engine.positions(ctx(jan2))) == 1                             # innehavet finns kvar


def test_kvartalsslut():
    assert engine.quarter_end(engine.date(2027, 1, 1)) == engine.date(2027, 3, 31)
    assert engine.quarter_end(engine.date(2027, 6, 30)) == engine.date(2027, 6, 30)
    assert engine.quarter_end(engine.date(2027, 7, 1)) == engine.date(2027, 9, 30)


# ---------- Stresstest: kontot går aldrig under 0 ----------

def test_slumpmassiga_affarer_kontot_aldrig_negativt(world):
    import random
    rnd = random.Random(42)
    _, m, ctx = world
    tickers = ["VOLV-B.ST", "ERIC-B.ST"]
    t = MANDAG_10
    for i in range(400):
        for tk in tickers:
            old = m.p[tk][0]
            m.p[tk] = (max(0.5, old * rnd.uniform(0.7, 1.35)), "SEK")
        c = ctx(t)
        engine.update(c)
        if engine._pending_crash(c):
            engine.write_crash_analysis(c, "x" * 60)
        tk = rnd.choice(tickers)
        try:
            if engine._position(c, tk) and rnd.random() < 0.5:
                engine.close_position(c, tk)
            else:
                n = engine.shares_for_amount(c, tk, cash(c) * rnd.uniform(0.1, 1.0), rnd.choice([1, 2, 5, 10]))
                if n:
                    engine.open_position(c, tk, n, rnd.choice(["lång", "blankad"]), rnd.choice([1, 2, 5, 10]))
        except engine.TradeError:
            pass
        assert cash(c) >= 0
        assert engine.snapshot(c).totalt_sek >= 0
