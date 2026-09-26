"""Fas 1: marknadstider, prislogik och databas – utan nätverk (hämtningen mockas)."""
from datetime import datetime, timezone

import pytest

from carl import db, markets, prices


def utc(s):  # svensk tid -> UTC (sommartid +2, vintertid +1 hanteras av zoneinfo)
    return datetime.fromisoformat(s).replace(tzinfo=markets.SE_TZ).astimezone(timezone.utc)


# ---------- Marknader ----------

@pytest.mark.parametrize("ticker,borse", [
    ("VOLV-B.ST", "stockholm"), ("NOKIA.HE", "helsingfors"), ("NOVO-B.CO", "kopenhamn"),
    ("EQNR.OL", "oslo"), ("AAPL", "usa"), ("BTC", "krypto"), ("eth-usd", "krypto"),
])
def test_exchange_for(ticker, borse):
    assert markets.exchange_for(ticker) == borse


def test_okand_borse_ger_fel():
    with pytest.raises(ValueError):
        markets.exchange_for("XYZ.ZZ")


def test_stockholm_oppettider():
    assert markets.is_open("VOLV-B.ST", utc("2026-09-28T09:00"))       # måndag öppning
    assert markets.is_open("VOLV-B.ST", utc("2026-09-28T17:29"))
    assert not markets.is_open("VOLV-B.ST", utc("2026-09-28T17:30"))   # stängt
    assert not markets.is_open("VOLV-B.ST", utc("2026-09-28T08:59"))
    assert not markets.is_open("VOLV-B.ST", utc("2026-09-26T12:00"))   # lördag
    assert not markets.is_open("VOLV-B.ST", utc("2026-12-24T12:00"))   # julafton


def test_usa_oppettider_i_svensk_tid():
    assert markets.is_open("AAPL", utc("2026-09-28T15:30"))
    assert markets.is_open("AAPL", utc("2026-09-28T21:59"))
    assert not markets.is_open("AAPL", utc("2026-09-28T22:00"))
    # Veckan när USA bytt till vintertid men inte Sverige (mars): USA öppnar 14:30 svensk tid
    assert markets.is_open("AAPL", utc("2027-03-15T14:30"))


def test_krypto_alltid_oppet():
    assert markets.is_open("BTC", utc("2026-09-26T03:00"))


def test_nasta_oppning_efter_helg():
    s = markets.status("stockholm", utc("2026-09-26T12:00"))
    assert not s.oppen and s.nasta_oppning.isoformat().startswith("2026-09-28T09:00")


# ---------- Priser (mockade) ----------

def fake_quote(ticker, pris, valuta):
    return prices.Quote(ticker, pris, valuta, datetime.now(timezone.utc), "test")


def test_krypto_reserv_coingecko(monkeypatch):
    def binance_nere(sym):
        raise ConnectionError("nere")
    monkeypatch.setattr(prices, "fetch_binance", binance_nere)
    monkeypatch.setattr(prices, "fetch_coingecko", lambda s: fake_quote(s, 65000.0, "USD"))
    q = prices.get_quote("btc-usd")
    assert q.ticker == "BTC" and q.pris == 65000.0 and q.kalla == "test"


def test_inget_pris_ger_fel_aldrig_pahittat(monkeypatch):
    def nere(sym):
        raise ConnectionError("nere")
    monkeypatch.setattr(prices, "fetch_binance", nere)
    monkeypatch.setattr(prices, "fetch_coingecko", nere)
    with pytest.raises(prices.PriceError):
        prices.get_quote("BTC")


def test_omrakning_till_sek(monkeypatch):
    def fake_yahoo(t):
        return {"AAPL": fake_quote("AAPL", 200.0, "USD"),
                "USDSEK=X": fake_quote("USDSEK=X", 10.5, "SEK")}[t]
    monkeypatch.setattr(prices, "fetch_yahoo", fake_yahoo)
    q, fx = prices.get_quote_sek("AAPL")
    assert q.pris * fx.pris == pytest.approx(2100.0)


def test_sek_aktie_kurs_ett(monkeypatch):
    monkeypatch.setattr(prices, "fetch_yahoo", lambda t: fake_quote(t, 250.0, "SEK"))
    q, fx = prices.get_quote_sek("VOLV-B.ST")
    assert fx.pris == 1.0


# ---------- Databas ----------

def test_databas_skapar_carl_med_startkapital(tmp_path):
    with db.session(tmp_path / "t.db") as conn:
        db.ensure_agent(conn)
        db.ensure_agent(conn)  # andra gången ska inget hända
        a = conn.execute("SELECT * FROM accounts").fetchall()
        assert len(a) == 1 and a[0]["kassa_sek"] == 100000 and a[0]["konkurser"] == 0
        prices.save_quote(conn, fake_quote("AAPL", 200.0, "USD"))
        assert conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0] == 1
