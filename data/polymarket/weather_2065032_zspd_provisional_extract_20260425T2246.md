# Shanghai 2065032 — extrait provisoire ZSPD

- URL: https://www.wunderground.com/history/daily/cn/shanghai/ZSPD/date/2026-04-26
- Source: Wunderground Shanghai Pudong International Airport `ZSPD`
- Statut: **PROVISIONAL_ONLY_NOT_FINALIZED**

## Valeur extraite
- Date marché: 2026-04-26T07:00:00+0800
- Max affiché/provisoire: 72°F ≈ 22.2°C
- Arrondi Celsius: 22°C

## Interprétation
- Le marché demande exactement **21°C**.
- L’extrait embarqué indique provisoirement environ **22°C** si on convertit 72°F.
- Donc le side **NO 21°C** est cohérent en proxy/provisoire.
- Mais ce n’est pas encore la table historique finalisée: ne pas traiter comme résolution finale.

## Décision paper
- Candidat reste `SOURCE_CHECK_FIRST_THEN_PAPER_LIMIT`.
- Si la table finalisée confirme max ≠ 21°C, on peut simuler strict-limit paper.
- Limite actuelle à respecter: NO ask ≤ 0.954; ne pas chase.
- Top ask size observée: 0.47 seulement, donc fill papier réaliste très petit ou attendre profondeur.