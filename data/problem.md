# Problemlogg

Alla chattar skriver hit när något inte går att genomföra. Huvudchatten läser, fixar och bockar av.
Format: `- [ ] ÅÅÅÅ-MM-DD HH:MM (chattens gren): vad du försökte, vad som hände, felmeddelande`
Löst: ändra till `- [x]` och lägg till en kort rad om lösningen.

## Olösta
- [ ] 2026-10-30 20:00 (claude/wizardly-hamilton-z6gv6n): price.py för Stockholmsaktier (MYCR.ST, HANZA.ST, BOOZT.ST, ^OMX) ger samma pris hela eftermiddagen, märkt "7.0 h gammalt" (senast ca 12:00) trots att börsen var öppen till 17:30. USA-kurser (QQQ) är färska. Samtidigt "Crumb fetch rate-limited (HTTP 429)" från Yahoo. Stängningskurser 30/10 kan därför inte bekräftas.

## Lösta
- [x] 2026-09-29 (claude/wizardly-hamilton-z6gv6n): verktygen blockerades i läget Auto ("tool-use blocked by
  Claude security check"). Tillfälligt fel hos Claude, gick över av sig självt 30/9.
