# Carl-Gustaf – AI-tradern

Carl-Gustaf (Carl, CG) är en AI-trader som handlar aktier och krypto med **låtsaspengar**
i en egen simulerad portfölj. Han är inte kopplad till någon riktig mäklare eller
några riktiga pengar. Allt ligger i en lokal SQLite-databas (`data/carl.db`).

## Status
- ✅ Fas 1 – Grunden: databas, prisskript, marknadstider, konfiguration
- ✅ Fas 2 – Handelsmotorn
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
| `python price.py VOLV-B.ST AAPL BITCOIN-XBT.ST` | Hämtar priser (även omräknat till SEK) och hur gamla de är |
| `python price.py fx USD EUR` | Valutakurser mot SEK |
| `python price.py test` | Testar alla datakällor |
| `python trade.py buy VOLV-B.ST 50 -m "motivering"` | Köp 50 aktier |
| `python trade.py buy VOLV-B.ST --belopp 10000 -m "..."` | Köp för 10 000 kr |
| `python trade.py buy NVDA 20 --havstang 2 -m "..."` | Köp med 2x hävstång |
| `python trade.py sell VOLV-B.ST all -m "..."` | Sälj allt |
| `python trade.py short ERIC-B.ST 100 -m "..."` | Blanka |
| `python trade.py cover ERIC-B.ST all -m "..."` | Köp tillbaka blankade aktier |
| `python portfolio.py status` | Uppdaterar allt (räntor, likvidationer) och visar portföljen |
| `python portfolio.py trades 20` | De senaste affärerna med motivering |
| `python portfolio.py haveri "..."` | Obligatorisk haveri-analys efter konkurs |
| `python round.py status` / `historik` | Omgångar och dagar kvar |
| `python -m pytest` | Kör alla tester |

## Tickers
- Stockholm: `VOLV-B.ST`, Helsingfors: `NOKIA.HE`, Köpenhamn: `NOVO-B.CO`, Oslo: `EQNR.OL`
- USA: `AAPL`, `NVDA` (inget suffix)
- Krypto: bara via ETP:er på Stockholmsbörsen, t.ex. `BITCOIN-XBT.ST` (listan finns i `config.yaml`)

## Konfiguration
Alla avgifter (courtage, valutaväxling, låneränta, blankningsavgift), likvidationsnivå,
börsernas öppettider och helgdagar finns i `config.yaml`.

## Så fungerar handeln
- **Order när börsen är stängd avvisas.** Ingen väntande order.
- **Hävstång:** säkerhet = positionens värde / hävstång, resten lånas (låneränta per dag).
- **Blankning:** säkerhet = värdet / hävstång, blankningsavgift per dag.
- **Likvidation:** när eget kapital i en position understiger 5 % av dess värde stängs den automatiskt.
- **Kontot går aldrig under 0 kr.** Under 100 kr räknas som konkurs: räknaren +1, kontot
  nollställs till 100 000 kr och Carl måste skriva en haveri-analys innan han får handla igen.
- **Omgångar** slutar vid kvartalsslut. Portföljen följer med till nästa omgång.
- **Blankning och hävstång i tävlingen** görs via BULL/BEAR-certifikat. Carl skriver vilket i "ATT KOPIERA".

## Datakällor
- Aktier och valutor: Yahoo Finance via `yfinance` (svenska kurser ofta ~15 min fördröjda)
- Krypto: Binance publika API, reserv CoinGecko
- Går ett pris inte att hämta blir det **ingen affär**. Carl hittar aldrig på priser.
