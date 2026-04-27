# Polymarket météo — Top 10 comptes gagnants et patterns (20260427T093821Z)
Source: leaderboard live `weather/all/profit` + endpoints publics `trades` / `positions`. Données publiques récentes, pas historique exhaustif.
Comptes profitable-PnL récupérés avant arrêt: **10050**. Sélection analysée: **top 10 par PnL météo live**.
| Rank | Compte | PnL météo | Volume météo | ROI PnL/vol | Pattern dominant | Trades/positions météo visibles |
|---:|---|---:|---:|---:|---|---:|
| 1 | gopfan2 | $344,909 | $4,571,405 | 7.54% | weather-heavy signal/generalist | 1 / 21 |
| 2 | aenews2 | $277,050 | $9,972,309 | 2.78% | weather-profitable generalist (current/recent flow mostly non-weather) | 3 / 0 |
| 3 | ColdMath | $123,800 | $8,940,156 | 1.38% | breadth/grid surface trader | 451 / 414 |
| 4 | gopfan | $118,426 | $739,901 | 16.01% | sparse/large-ticket conviction trader | 30 / 0 |
| 5 | bama124 | $86,601 | $410,556 | 21.09% | weather-profitable generalist (current/recent flow mostly non-weather) | 0 / 0 |
| 6 | Hans323 | $80,872 | $6,971,547 | 1.16% | breadth/grid surface trader | 293 / 0 |
| 7 | Handsanitizer23 | $71,174 | $953,275 | 7.47% | sparse/large-ticket conviction trader | 27 / 15 |
| 8 | automatedAItradingbot | $64,279 | $2,363,702 | 2.72% | weather-heavy signal/generalist | 0 / 5 |
| 9 | BeefSlayer | $63,514 | $1,429,671 | 4.44% | breadth/grid surface trader | 500 / 7 |
| 10 | BigMike11 | $62,777 | $850,756 | 7.38% | sparse/large-ticket conviction trader | 48 / 0 |

## Lecture transversale
- Styles top10: 2× weather-heavy signal/generalist, 2× weather-profitable generalist (current/recent flow mostly non-weather), 3× breadth/grid surface trader, 3× sparse/large-ticket conviction trader.
- Ce qui revient le plus: grilles ville/date, exact bins, thresholds `or higher/below`, gros écart entre comptes breadth/small-ticket et comptes conviction gros tickets.
- À copier: la structure de décision (surface complète + source officielle + prix limite), pas les wallets ni les tailles brutes.

## 1. gopfan2 — rank 1 — weather-heavy signal/generalist
- Profil: https://polymarket.com/profile/0xf2f6af4f27ec2dcf4072095ab804016e14cd5817
- PnL météo leaderboard: **$344,908.99** / volume **$4,571,404.83** / PnL-volume **7.54%**.
- Public récent: 1 trades météo, 21 positions météo actives, valeur active météo ~$10,768.45.
- Sizing visible: trade moyen météo récent ~$33.10, max ~$33.10.
- Notes pattern: unit sizing plutôt petit: approche probe/multi-lignes plus copiable; activité publique récente mixte/non-weather: utile comme signal, pas pur spécialiste météo.
- Exemples trades récents:
  - BUY $33.1: Will global temperature increase by less than 1.10ºC in April 2026?
- Exemples positions actives:
  - $5625.54: Zelenskyy out as Ukraine president by end of 2026?
  - $4497.08: Will a hurricane form by May 31?
  - $261.68: Ukraine signs peace deal with Russia before 2027?
  - $176.57: Will any Category 4 hurricane make landfall in the US in before 2027?
  - $127.36: Named storm forms before hurricane season?

## 2. aenews2 — rank 2 — weather-profitable generalist (current/recent flow mostly non-weather)
- Profil: https://polymarket.com/profile/0x44c1dfe43260c94ed4f1d00de2e1f80fb113ebc1
- PnL météo leaderboard: **$277,050.19** / volume **$9,972,308.56** / PnL-volume **2.78%**.
- Public récent: 3 trades météo, 0 positions météo actives, valeur active météo ~$0.00.
- Sizing visible: trade moyen météo récent ~$357.04, max ~$942.15.
- Notes pattern: présence forte de thresholds: harvest de contrats 'or higher/below', souvent proche résolution; présence d'exact bins/temp surfaces: chasse aux anomalies de grille ville/date; activité publique récente mixte/non-weather: utile comme signal, pas pur spécialiste météo.
- Exemples trades récents:
  - BUY $942.15: Will 150 or more tornadoes occur in the United States in March 2026?
  - BUY $126.6: Will the highest temperature in Chicago be between 46-47°F on March 11?
  - BUY $2.36: Will the highest temperature in Chicago be 54°F or higher on March 11?

## 3. ColdMath — rank 3 — breadth/grid surface trader
- Profil: https://polymarket.com/profile/0x594edb9112f526fa6a80b8f858a6379c8a2c1c11
- PnL météo leaderboard: **$123,799.94** / volume **$8,940,156.46** / PnL-volume **1.38%**.
- Public récent: 451 trades météo, 414 positions météo actives, valeur active météo ~$29,406.36.
- Sizing visible: trade moyen météo récent ~$162.81, max ~$6,631.81.
- Notes pattern: grand nombre de lignes: process/automatisation probable, diversification par surfaces; présence forte de thresholds: harvest de contrats 'or higher/below', souvent proche résolution; présence d'exact bins/temp surfaces: chasse aux anomalies de grille ville/date; tickets max élevés: conviction/banque significative, pas copiable tel quel.
- Exemples trades récents:
  - BUY $12.26: Will the highest temperature in Jeddah be 35°C on April 29?
  - BUY $4.48: Will the highest temperature in Lucknow be 39°C or below on April 28?
  - BUY $15.83: Will the highest temperature in Lucknow be 39°C or below on April 28?
  - BUY $1309.72: Will the highest temperature in Lucknow be 43°C on April 28?
  - BUY $4.48: Will the highest temperature in Lucknow be 39°C or below on April 28?
- Exemples positions actives:
  - $2803.95: Will the lowest temperature in London be 4°C on April 28?
  - $2423.81: Will the lowest temperature in New York City be 35°F or below on April 26?
  - $1617.4: Will the lowest temperature in New York City be 37°F or below on April 27?
  - $1331.49: Will the highest temperature in Lucknow be 43°C on April 28?
  - $1242.58: Will the highest temperature in Seoul be 20°C on April 27?

## 4. gopfan — rank 4 — sparse/large-ticket conviction trader
- Profil: https://polymarket.com/profile/0x6af75d4e4aaf700450efbac3708cce1665810ff1
- PnL météo leaderboard: **$118,426.47** / volume **$739,900.98** / PnL-volume **16.01%**.
- Public récent: 30 trades météo, 0 positions météo actives, valeur active météo ~$0.00.
- Sizing visible: trade moyen météo récent ~$576.96, max ~$7,646.20.
- Notes pattern: présence d'exact bins/temp surfaces: chasse aux anomalies de grille ville/date; tickets max élevés: conviction/banque significative, pas copiable tel quel; activité publique récente mixte/non-weather: utile comme signal, pas pur spécialiste météo.
- Exemples trades récents:
  - BUY $62.55: August temperature increase greater than 1.29°C?
  - SELL $290.0: August temperature increase by between 1.20-1.24°C?
  - BUY $30.0: August temperature increase greater than 1.29°C?
  - BUY $83.26: August temperature increase greater than 1.29°C?
  - BUY $458.73: August temperature increase greater than 1.29°C?

## 5. bama124 — rank 5 — weather-profitable generalist (current/recent flow mostly non-weather)
- Profil: https://polymarket.com/profile/0xe5c8026239919339b988fdb150a7ef4ea196d3e7
- PnL météo leaderboard: **$86,600.55** / volume **$410,556.07** / PnL-volume **21.09%**.
- Public récent: 0 trades météo, 0 positions météo actives, valeur active météo ~$0.00.
- Sizing visible: trade moyen météo récent ~$0.00, max ~$0.00.
- Notes pattern: activité publique récente mixte/non-weather: utile comme signal, pas pur spécialiste météo.

## 6. Hans323 — rank 6 — breadth/grid surface trader
- Profil: https://polymarket.com/profile/0x0f37cb80dee49d55b5f6d9e595d52591d6371410
- PnL météo leaderboard: **$80,872.37** / volume **$6,971,546.61** / PnL-volume **1.16%**.
- Public récent: 293 trades météo, 0 positions météo actives, valeur active météo ~$0.00.
- Sizing visible: trade moyen météo récent ~$695.45, max ~$22,909.19.
- Notes pattern: grand nombre de lignes: process/automatisation probable, diversification par surfaces; présence forte de thresholds: harvest de contrats 'or higher/below', souvent proche résolution; présence d'exact bins/temp surfaces: chasse aux anomalies de grille ville/date; tickets max élevés: conviction/banque significative, pas copiable tel quel.
- Exemples trades récents:
  - BUY $10727.05: Will the highest temperature in New York City be between 50-51°F on April 21?
  - BUY $453.59: Will the highest temperature in Manila be 33°C on April 15?
  - BUY $527.28: Will the highest temperature in Manila be 34°C on April 15?
  - BUY $1252.29: Will the highest temperature in Guangzhou be 30°C or below on April 15?
  - BUY $237.76: Will the lowest temperature in Seoul be 12°C on April 15?

## 7. Handsanitizer23 — rank 7 — sparse/large-ticket conviction trader
- Profil: https://polymarket.com/profile/0x05e70727a2e2dcd079baa2ef1c0b88af06bb9641
- PnL météo leaderboard: **$71,174.40** / volume **$953,274.81** / PnL-volume **7.47%**.
- Public récent: 27 trades météo, 15 positions météo actives, valeur active météo ~$0.00.
- Sizing visible: trade moyen météo récent ~$14,325.70, max ~$76,142.40.
- Notes pattern: présence forte de thresholds: harvest de contrats 'or higher/below', souvent proche résolution; présence d'exact bins/temp surfaces: chasse aux anomalies de grille ville/date; tickets max élevés: conviction/banque significative, pas copiable tel quel.
- Exemples trades récents:
  - BUY $106.79: Will the highest temperature in Guangzhou be 31°C on April 16?
  - BUY $6.01: Will the highest temperature in Hong Kong be 26°C on April 5?
  - BUY $36.7: Will the highest temperature in Hong Kong be 26°C on April 5?
  - BUY $95.0: Will the highest temperature in Miami be between 78-79°F on March 29?
  - BUY $76142.4: Will the highest temperature in Munich be 7°C on March 27?
- Exemples positions actives:
  - $0.0: Will the highest temperature in Dallas be between 84-85°F on March 19?
  - $0.0: Will the highest temperature in Dallas be between 72-73°F on March 4?
  - $0.0: Will the highest temperature in Shenzhen be 28°C on March 22?
  - $0.0: Will the highest temperature in Guangzhou be 31°C on April 16?
  - $0.0: Will the highest temperature in Wellington be 21°C on February 24?

## 8. automatedAItradingbot — rank 8 — weather-heavy signal/generalist
- Profil: https://polymarket.com/profile/0xd8f8c13644ea84d62e1ec88c5d1215e436eb0f11
- PnL météo leaderboard: **$64,279.03** / volume **$2,363,702.37** / PnL-volume **2.72%**.
- Public récent: 0 trades météo, 5 positions météo actives, valeur active météo ~$10.12.
- Sizing visible: trade moyen météo récent ~$0.00, max ~$0.00.
- Notes pattern: présence forte de thresholds: harvest de contrats 'or higher/below', souvent proche résolution; présence d'exact bins/temp surfaces: chasse aux anomalies de grille ville/date.
- Exemples positions actives:
  - $10.0: Will the highest temperature in Panama City be 31°C on April 26?
  - $0.09: Will the highest temperature in Seoul be 22°C on April 27?
  - $0.03: Will the highest temperature in Tokyo be 20°C on April 27?
  - $0.0: Will the highest temperature in Taipei be 31°C on April 27?
  - $0.0: Will the highest temperature in Panama City be 32°C or higher on April 26?

## 9. BeefSlayer — rank 9 — breadth/grid surface trader
- Profil: https://polymarket.com/profile/0x331bf91c132af9d921e1908ca0979363fc47193f
- PnL météo leaderboard: **$63,514.16** / volume **$1,429,670.68** / PnL-volume **4.44%**.
- Public récent: 500 trades météo, 7 positions météo actives, valeur active météo ~$217.04.
- Sizing visible: trade moyen météo récent ~$117.65, max ~$10,098.41.
- Notes pattern: grand nombre de lignes: process/automatisation probable, diversification par surfaces; présence forte de thresholds: harvest de contrats 'or higher/below', souvent proche résolution; présence d'exact bins/temp surfaces: chasse aux anomalies de grille ville/date; tickets max élevés: conviction/banque significative, pas copiable tel quel.
- Exemples trades récents:
  - BUY $158.06: Will the highest temperature in Seoul be 19°C on April 27?
  - SELL $21.66: Will the highest temperature in Houston be between 82-83°F on April 26?
  - BUY $14.28: Will the highest temperature in Houston be between 82-83°F on April 26?
  - SELL $10.7: Will the lowest temperature in Seoul be 8°C or below on April 26?
  - SELL $36.55: Will the lowest temperature in Seoul be 9°C on April 26?
- Exemples positions actives:
  - $217.04: Will the highest temperature in Seoul be 19°C on April 27?
  - $0.0: Will the highest temperature in Austin be 86°F or higher on April 26?
  - $0.0: Will the highest temperature in Miami be between 86-87°F on April 25?
  - $0.0: Will the highest temperature in Atlanta be between 76-77°F on April 25?
  - $0.0: Will the highest temperature in Atlanta be 71°F or below on April 25?

## 10. BigMike11 — rank 10 — sparse/large-ticket conviction trader
- Profil: https://polymarket.com/profile/0xecdbd79566a25693b9971c48d7de84bc05f7da79
- PnL météo leaderboard: **$62,776.72** / volume **$850,755.65** / PnL-volume **7.38%**.
- Public récent: 48 trades météo, 0 positions météo actives, valeur active météo ~$0.00.
- Sizing visible: trade moyen météo récent ~$789.91, max ~$3,543.58.
- Notes pattern: présence d'exact bins/temp surfaces: chasse aux anomalies de grille ville/date; tickets max élevés: conviction/banque significative, pas copiable tel quel; activité publique récente mixte/non-weather: utile comme signal, pas pur spécialiste météo.
- Exemples trades récents:
  - BUY $970.0: Russia x Ukraine ceasefire in 2025?
  - BUY $7.83: Russia x Ukraine ceasefire in 2025?
  - BUY $191.81: Will Belarus invade Ukraine before October?
  - BUY $932.82: Will Belarus invade Ukraine before October?
  - BUY $297.3: Will Belarus invade Ukraine before October?
