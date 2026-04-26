# Polymarket météo — validation live top patterns

- Généré: 2026-04-25T22:36:24Z
- Mode: **paper-only / no real orders**
- But: vérifier Gamma/CLOB sans transformer le signal comptes gagnants en ordre réel.

## Résumé
| market | surface | question | target ask | live fetch | décision |
|---|---|---|---:|---|---|
| 2065210 | Moscow April 26 12°C | Will the highest temperature in Moscow be 12°C on April 26? | 0.987 | ok | strict_limit_paper_only_after_source_check |
| 2065032 | Shanghai April 26 21°C | Will the highest temperature in Shanghai be 21°C on April 26? | 0.954 | ok | source_and_book_validation_candidate |
| 2065108 | Beijing April 26 22°C | Will the highest temperature in Beijing be 22°C on April 26? | 0.995 | ok | micro_paper_only_if_source_confirmed_and_no_chase |
| 2064990 | Munich April 26 16°C | Will the highest temperature in Munich be 16°C on April 26? | 0.991 | ok | micro_paper_only_if_source_confirmed_and_no_chase |
| 2074474 | Shanghai April 27 24°C | Will the highest temperature in Shanghai be 24°C on April 27? | 0.965 | ok | source_and_book_validation_candidate |

## Interprétation
- Si Gamma/CLOB échoue: ne pas inventer prix/source; rester watch-only.
- Si ask >= 0.99: même avec bons comptes, micro-paper uniquement.
- Si source officielle non validée: aucun live/normal sizing.

## Prochaine action
Construire une file `paper_validation_queue`: source officielle par ville + dernier carnet + limite stricte, puis seulement ensuite simulation de fill.