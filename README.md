# Carl-Gustaf – AI-tradern

Carl-Gustaf (Carl, CG) är en AI-trader som handlar aktier och krypto med **låtsaspengar**
i en egen simulerad portfölj. Han är inte kopplad till någon riktig mäklare eller
några riktiga pengar. Allt ligger i en lokal SQLite-databas (`data/carl.db`).

## Status
- ✅ Fas 1 – Grunden: databas, prisskript, marknadstider, konfiguration
- ⬜ Fas 2 – Handelsmotorn
- ⬜ Fas 3 – Carls hjärna (CLAUDE.md, /session, indikatorer, lärdomar)
- ⬜ Fas 4 – Dashboard
- ⬜ Fas 5 – Första riktiga sessionen

## Installation (bara om man vill köra själv – behövs inte för att använda Carl)
```
pip install -r requirements.txt
python init_db.py
```

## Kommandon
| Kommando | Vad det gör |
|---|---|
| `python init_db.py` | Skapar databasen och Carls konto (100 000 kr) |
| `python market.py` | Visar vilka börser som är öppna |
| `python market.py VOLV-B.ST` | Går just den tickern att handla nu? |
| `python price.py VOLV-B.ST AAPL BTC` | Hämtar priser (även omräknat till SEK) och hur gamla de är |
| `python price.py fx USD EUR` | Valutakurser mot SEK |
| `python price.py test` | Testar alla datakällor |
| `python -m pytest` | Kör alla tester |

## Tickers
- Stockholm: `VOLV-B.ST`, Helsingfors: `NOKIA.HE`, Köpenhamn: `NOVO-B.CO`, Oslo: `EQNR.OL`
- USA: `AAPL`, `NVDA` (inget suffix)
- Krypto: `BTC`, `ETH`, `SOL` … (listan finns i `config.yaml`)

## Konfiguration
Alla avgifter (courtage, valutaväxling, låneränta, blankningsavgift), likvidationsnivå,
börsernas öppettider och helgdagar finns i `config.yaml`.

## Datakällor
- Aktier och valutor: Yahoo Finance via `yfinance` (svenska kurser ofta ~15 min fördröjda)
- Krypto: Binance publika API, reserv CoinGecko
- Går ett pris inte att hämta blir det **ingen affär**. Carl hittar aldrig på priser.
