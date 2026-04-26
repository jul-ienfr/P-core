# Shanghai 2065032 — Wunderground source check

- URL: https://www.wunderground.com/history/daily/cn/shanghai/ZSPD/date/2026-04-26
- Fetch: ok
- HTML bytes: 247600

## Résultat opérateur
- La page Wunderground est accessible côté HTML.
- Je ne considère pas encore la température comme finale: il faut extraire/valider la table horaire finalisée.
- Statut: `SOURCE_ACCESSIBLE_PARSE_REQUIRED`.

## Règle du marché extraite
- Marché 2065032: “Will the highest temperature in Shanghai be 21°C on April 26?”
- Source: Wunderground, station Shanghai Pudong International Airport `ZSPD`.
- Résolution: plus haute température en degrés Celsius, arrondie/mesurée au degré entier, une fois toutes les données finalisées.

## Décision
- Tant que la table Wunderground finalisée n’est pas parsée: pas de paper fill.
- Si max final != 21°C, le side NO est cohérent; ensuite seulement vérifier carnet/limite.
- Si max final = 21°C, skip NO.