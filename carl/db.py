"""SQLite-databasen. Allt är knutet till ett agent_id så att fler agenter kan läggas till senare."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,           -- t.ex. 'carl'
    namn        TEXT NOT NULL,
    strategi    TEXT,
    skapad      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Ett konto per agent. Kassan är alltid i SEK.
CREATE TABLE IF NOT EXISTS accounts (
    agent_id        TEXT PRIMARY KEY REFERENCES agents(id),
    kassa_sek       REAL NOT NULL,
    konkurser       INTEGER NOT NULL DEFAULT 0,
    avgifter_sek    REAL NOT NULL DEFAULT 0,  -- totalt betalda avgifter
    senast_ranta    TEXT                      -- när ränta/lånekostnad senast drogs
);

-- Omgångar på 3 månader. Portföljen följer med mellan omgångarna.
CREATE TABLE IF NOT EXISTS rounds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    startdatum      TEXT NOT NULL,
    slutdatum       TEXT NOT NULL,
    startvarde_sek  REAL NOT NULL,
    slutvarde_sek   REAL,                     -- fylls i när omgången avslutas
    tillskott_sek   REAL NOT NULL DEFAULT 0,  -- pengar som tillförts vid konkurs (räknas bort från avkastningen)
    status          TEXT NOT NULL DEFAULT 'aktiv'  -- aktiv / avslutad
);

-- Öppna positioner. antal > 0 = lång, antal < 0 = blankad.
CREATE TABLE IF NOT EXISTS positions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id            TEXT NOT NULL REFERENCES agents(id),
    ticker              TEXT NOT NULL,
    valuta              TEXT NOT NULL,
    antal               REAL NOT NULL,
    snittpris           REAL NOT NULL,        -- i instrumentets valuta
    havstang            REAL NOT NULL DEFAULT 1,
    kostnad_sek         REAL NOT NULL,        -- positionens värde i SEK när den öppnades
    sakerhet_sek        REAL NOT NULL,        -- låst säkerhet (minskar om räntor dras härifrån)
    lan_sek             REAL NOT NULL DEFAULT 0,  -- lånat belopp (bara långa med hävstång)
    insats_sek          REAL NOT NULL,        -- allt Carl lagt in: säkerhet + avgifter + räntor
    likvidationspris    REAL,                 -- i instrumentets valuta
    oppnad              TEXT NOT NULL DEFAULT (datetime('now')),
    strategi            TEXT
);

-- Varje affär, med Carls motivering.
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    round_id        INTEGER REFERENCES rounds(id),
    tid             TEXT NOT NULL DEFAULT (datetime('now')),
    handling        TEXT NOT NULL,            -- buy / sell / short / cover / liquidation
    ticker          TEXT NOT NULL,
    antal           REAL NOT NULL,
    pris            REAL NOT NULL,            -- i instrumentets valuta
    valuta          TEXT NOT NULL,
    valutakurs      REAL NOT NULL,            -- SEK per 1 enhet valuta
    varde_sek       REAL NOT NULL,
    avgift_sek      REAL NOT NULL,
    havstang        REAL NOT NULL DEFAULT 1,
    resultat_sek    REAL,                     -- realiserat resultat vid stängning
    strategi        TEXT,
    motivering      TEXT,
    prisalder_sek   REAL,                     -- hur gammalt priset var (sekunder)
    session_id      INTEGER
);

-- Senast hämtade priser (cache + historik för dashboarden).
CREATE TABLE IF NOT EXISTS prices (
    ticker      TEXT NOT NULL,
    pris        REAL NOT NULL,
    valuta      TEXT NOT NULL,
    pristid     TEXT NOT NULL,                -- när priset gällde (UTC)
    hamtad      TEXT NOT NULL,                -- när vi hämtade det (UTC)
    kalla       TEXT NOT NULL,
    PRIMARY KEY (ticker, hamtad)
);

-- Portföljvärde över tid (för grafen).
CREATE TABLE IF NOT EXISTS equity (
    agent_id    TEXT NOT NULL REFERENCES agents(id),
    tid         TEXT NOT NULL DEFAULT (datetime('now')),
    totalt_sek  REAL NOT NULL,
    kassa_sek   REAL NOT NULL
);

-- Sessioner, med sammanfattning och "ATT KOPIERA"-lista.
CREATE TABLE IF NOT EXISTS sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT NOT NULL REFERENCES agents(id),
    start           TEXT NOT NULL DEFAULT (datetime('now')),
    slut            TEXT,
    startvarde_sek  REAL,
    slutvarde_sek   REAL,
    sammanfattning  TEXT,
    att_kopiera     TEXT,
    tankar          TEXT
);

-- Konkurser med obligatorisk haveri-analys.
CREATE TABLE IF NOT EXISTS bankruptcies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL REFERENCES agents(id),
    tid         TEXT NOT NULL DEFAULT (datetime('now')),
    round_id    INTEGER REFERENCES rounds(id),
    varde_sek   REAL NOT NULL,                -- kontovärde när konkursen inträffade
    analys      TEXT                          -- NULL tills Carl skrivit den
);
"""

DEFAULT_AGENT = "carl"


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path) if path else config.db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(path: Path | str | None = None):
    """Öppnar databasen, committar vid lyckat slut, rullar tillbaka vid fel."""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def ensure_agent(conn: sqlite3.Connection, agent_id: str = DEFAULT_AGENT,
                 namn: str = "Carl-Gustaf", strategi: str | None = None) -> None:
    """Skapar agenten och dess konto med startkapital om de inte finns."""
    init(conn)
    if conn.execute("SELECT 1 FROM agents WHERE id=?", (agent_id,)).fetchone():
        return
    start = float(config.load()["startkapital_sek"])
    conn.execute("INSERT INTO agents(id, namn, strategi) VALUES (?,?,?)", (agent_id, namn, strategi))
    conn.execute("INSERT INTO accounts(agent_id, kassa_sek) VALUES (?,?)", (agent_id, start))
