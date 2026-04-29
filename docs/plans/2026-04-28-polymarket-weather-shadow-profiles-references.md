# Plan de référence — Shadow profiles météo Polymarket

> **Pour Hermes / P-core :** utiliser ce document comme plan d’intégration pour construire des profils fantômes (`shadow profiles`) de traders météo Polymarket à partir des meilleurs comptes gagnants, de datasets historiques, de sources orderbook et d’un observer live paper-only.

**Date :** 2026-04-28
**Repo canonique :** `/home/jul/P-core`
**Remote :** `git@github.com:jul-ienfr/P-core.git`
**Branche observée :** `main`
**Mode obligatoire :** read-only / paper-only / no live order

---

## 1. Objectif produit

Construire dans P-core un système capable d’apprendre les stratégies de comptes gagnants Polymarket spécialisés météo, sans faire de copy-trading brut.

Le système doit apprendre :

1. **Les entrées réelles** : quand un compte trade, sur quel marché, à quel prix, avec quelle taille.
2. **Les abstentions** : dans quels cas similaires il ne trade pas.
3. **Le contexte marché** : prix, spread, profondeur, mouvement récent, surface des bins météo.
4. **Le contexte météo** : forecast disponible, source officielle, fraîcheur de la donnée, distance au seuil/bin.
5. **Les patterns de comportement** : timing, villes préférées, type de marché, prix d’entrée, tolérance au spread, style early/late.
6. **La valeur simulée** : est-ce qu’un profil reconstruit bat une baseline après spread, slippage et frais.

Le produit final n’est pas :

- un bot de copy-trading ;
- un système live ;
- une réécriture de P-core ;
- une boucle LLM continue ;
- un aspirateur de full orderbook illimité.

Le produit final est :

```text
un système d’observation + reverse-engineering + simulation paper-only
pour comprendre les stratégies météo gagnantes Polymarket.
```


### 1.1 Clarification produit — backfill-first, pas attente live

Décision produit Julien (2026-04-28) : **ne pas attendre 6 mois, 30 jours, 14 jours ou même 7 jours pour créer les premiers profils**.

Les premiers shadow profiles doivent être générés **immédiatement à partir de l’historique déjà disponible**, car les éléments suivants sont déjà accessibles par backfill / fichiers locaux / datasets publics :

- top marchés ;
- top villes ;
- types de marchés météo ;
- timing d’entrée/sortie ;
- taille des positions ;
- PnL par compte/type de marché ;
- prix d’entrée ;
- répétition de patterns ;
- clusters de comportement par compte.

Le live observer ne doit donc **pas** être présenté comme la source principale d’apprentissage initial. Il sert à collecter les variables qu’on reconstruit mal après coup :

- orderbook exact au moment T ;
- spread/profondeur réellement tradable ;
- abstentions propres sur marchés visibles ;
- forecast/source-at-time avec fraîcheur exacte ;
- surface complète des bins au moment T ;
- microstructure autour des trades et gros mouvements.

Doctrine v1 :

```text
1. Générer les profils historiques maintenant.
2. Les rejouer / backtester immédiatement en paper.
3. Lancer l’observer live en parallèle uniquement pour combler les angles morts.
4. Corriger les profils si le live montre que l’historique surestime l’edge.
```

---

## 2. Sources locales déjà disponibles

### 2.1 Followlist comptes météo

Fichier local :

```text
/home/jul/P-core/data/polymarket/weather_accounts_followlist_20260425.csv
```

Colonnes observées :

```text
bucket, rank, handle, wallet, x_username, pnl, volume, roi_pct,
class, active_weather, recent_weather, active_nonweather,
recent_nonweather, score, profile, sample_weather_titles
```

Ce fichier contient 100 comptes classés comme weather specialist / weather-heavy.

### 2.2 Patterns top 80

Fichier local :

```text
/home/jul/P-core/data/polymarket/weather_profitable_strategy_patterns_top80.json
```

Structure observée :

```text
sampled_accounts
fetched_accounts
kind_counts
top_cities
top_repeated_titles
accounts
```

Faits vérifiés :

```json
{
  "sampled_accounts": 80,
  "fetched_accounts": 80,
  "kind_counts": {
    "range_or_bin": 15305,
    "threshold": 2734,
    "other_weather": 30
  }
}
```

Villes les plus fréquentes dans les patterns :

| Rang | Ville | Occurrences |
|---:|---|---:|
| 1 | London | 1336 |
| 2 | Seoul | 1249 |
| 3 | New York City | 1060 |
| 4 | Hong Kong | 961 |
| 5 | Paris | 763 |
| 6 | Ankara | 711 |
| 7 | Miami | 632 |
| 8 | Munich | 473 |
| 9 | Madrid | 456 |
| 10 | Denver | 426 |
| 11 | Moscow | 425 |
| 12 | Helsinki | 413 |

Interprétation : les marchés météo les plus exploitables au départ sont probablement les marchés **temperature range/bin** et **threshold** sur grandes villes liquides.

---

## 3. Comptes à surveiller en priorité

### 3.1 Groupe prioritaire v0

Ces comptes sont les meilleurs candidats initiaux pour construire les premiers profils.

| Priorité | Handle | Wallet public | Rank | PnL approx. | Volume approx. | ROI % | Classe | Score |
|---:|---|---|---:|---:|---:|---:|---|---:|
| 1 | ColdMath | `0x594edb9112f526fa6a80b8f858a6379c8a2c1c11` | 3 | 121302.21 | 8832029.43 | 1.37 | weather specialist / weather-heavy | 257.9 |
| 2 | Poligarch | `0xb40e89677d59665d5188541ad860450a6e2a7cc9` | 18 | 50120.07 | 6119248.26 | 0.82 | weather specialist / weather-heavy | 224.7 |
| 3 | Railbird | `0x906f2454a777600aea6c506247566decef82371a` | 42 | 23358.41 | 797165.70 | 2.93 | weather specialist / weather-heavy | 249.2 |

Pourquoi commencer par eux :

- `ColdMath` : meilleur PnL météo observé, gros volume, score élevé.
- `Poligarch` : très gros volume, utile pour comprendre les stratégies scalables.
- `Railbird` : PnL plus bas mais ROI meilleur, utile comme profil plus sélectif.

### 3.2 Groupe prioritaire v1

À ajouter après la première preuve de concept :

| Handle | Wallet public | Rank | PnL approx. | Volume approx. | ROI % | Classe | Score |
|---|---|---:|---:|---:|---:|---|---:|
| Handsanitizer23 | `0x05e70727a2e2dcd079baa2ef1c0b88af06bb9641` | 7 | 71174.40 | 953274.81 | 7.47 | weather specialist / weather-heavy | 213.9 |
| Maskache2 | `0x1f66796b45581868376365aef54b51eb84184c8d` | 19 | 49973.43 | 4620632.97 | 1.08 | weather specialist / weather-heavy | 249.4 |
| xX25Xx | `0x2a353ce9e57a51e65814d2fe7cdd4ad3f20741ce` | 59 | 18841.23 | 93610.22 | 20.13 | weather specialist / weather-heavy | 261.0 |
| syacxxa | `0x2b2866a724e73bf45af306036f12f20170b4d021` | 56 | 19511.69 | 475869.55 | 4.10 | weather specialist / weather-heavy | 250.4 |
| 0xhana | `0xa37d1d1a3367c6ebc692e37c29bccb8bb015b2b4` | 72 | 15798.98 | 321617.19 | 4.91 | weather specialist / weather-heavy | 250.0 |
| dpnd | `0x5f211a24da4c005d9438a1ea269673b85ed0b376` | 41 | 24134.16 | 8113002.18 | 0.30 | weather specialist / weather-heavy | 240.4 |
| Amano-Hina | `0x8aa29c27241b6909a7c4d6cb4f400267aa215a0b` | 132 | 8831.67 | 137310.31 | 6.43 | weather specialist / weather-heavy | 248.9 |

### 3.3 Autres comptes top PnL à garder en radar

Ces comptes sont ressortis dans le top PnL du fichier local :

| Handle | Rank | PnL approx. | Classe | Score |
|---|---:|---:|---|---:|
| BeefSlayer | 9 | 63444.05 | weather specialist / weather-heavy | 214.0 |
| `0x77266604E63f5cAF08D19CaEBae0C563ce64aEE` | 40 | 24256.28 | weather specialist / weather-heavy | 229.2 |
| MrFox | 50 | 21382.09 | weather specialist / weather-heavy | 228.8 |
| Ooookey | 73 | 15772.14 | weather specialist / weather-heavy | 216.5 |
| cyberkurajber | 75 | 15394.30 | weather specialist / weather-heavy | 225.9 |
| mjf02 | 78 | 14775.84 | weather specialist / weather-heavy | 242.0 |

Note : `automatedAItradingbot` avait été repéré dans des résumés antérieurs comme intéressant, mais il n’est pas ressorti dans l’extraction CSV vérifiée de cette passe. Il doit rester en watchlist secondaire et être résolu par wallet/handle via dataset brut avant inclusion.

---

## 4. Sources externes de référence

### 4.1 Dataset Hugging Face `SII-WANGZJ/Polymarket_data`

URL :

```text
https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data
```

Rôle : **source principale de backfill historique trades / markets / users / fills**.

Fichiers observés lors de l’audit :

```text
README.md
markets.parquet
trades.parquet
quant.parquet
users.parquet
orderfilled_part1.parquet
orderfilled_part2.parquet
orderfilled_part3.parquet
orderfilled_part4.parquet
```

Volumes observés par métadonnées parquet :

| Fichier | Lignes approx. | Utilité |
|---|---:|---|
| `trades.parquet` | 568,646,651 | historique trades nettoyé |
| `quant.parquet` | 568,590,741 | données quantitatives associées |
| `users.parquet` | 933,335,553 | historique actions/wallets |
| `orderfilled_*` | 954,657,229 total | raw `OrderFilled` events |

Ce que ça permet :

- reconstruire l’historique par wallet ;
- identifier tous les trades des comptes météo ;
- relier wallet → market → timestamp → prix → taille ;
- créer les exemples positifs ;
- faire du backfill massif sans tout rescanner via API.

Limite :

- ne donne pas toujours le carnet d’ordres exact au moment du trade ;
- ne suffit pas à reconstruire la microstructure fine ;
- doit être complété par PMXT/Telonex ou observer live.

### 4.2 Repo GitHub `SII-WANGZJ/Polymarket_data`

URL :

```text
https://github.com/SII-WANGZJ/Polymarket_data
```

Rôle : **référence ETL pour comprendre comment le dataset HF est produit**.

Fichiers inspectés lors de l’audit :

```text
polymarket/processors/trades.py
polymarket/processors/cleaner.py
polymarket/fetchers/gamma.py
polymarket/fetchers/rpc.py
polymarket/config.py
data/README.md
```

Utilisation recommandée :

- ne pas importer tout le repo tel quel ;
- lire ses schémas et transformations ;
- créer un adapter P-core propre ;
- conserver la logique de mapping Gamma/RPC comme référence.

### 4.3 Repo `evan-kolberg/prediction-market-backtesting`

URL :

```text
https://github.com/evan-kolberg/prediction-market-backtesting
```

Rôle : **source prioritaire pour orderbook historique / replay L2**.

Ce repo est potentiellement le plus important pour comprendre le contexte `au moment T`.

Capacités observées :

- replay orderbook ;
- PMXT hourly L2 archive ;
- Telonex full-depth snapshots ;
- backtests NautilusTrader ;
- microprice / imbalance / spread / depth ;
- account ledger replay.

Ce que ça peut débloquer :

- best bid/ask au moment du trade ;
- spread exact ;
- profondeur disponible ;
- imbalance ;
- microprice ;
- mouvement avant/après ;
- conditions de fill réalistes ;
- comparaison trades vs non-trades avec contexte orderbook.

Limites :

- PMXT semble commencer vers février 2026 ;
- Telonex peut nécessiter accès/API ;
- stack potentiellement lourde ;
- à utiliser comme source/adaptateur, pas comme nouveau framework principal.

### 4.4 Repo `Jon-Becker/prediction-market-analysis`

URL :

```text
https://github.com/Jon-Becker/prediction-market-analysis
```

Rôle : **référence analyse / calibration / datasets markets-trades**.

Utilité :

- calibration prix → probabilité réelle ;
- analyse resolved markets ;
- win rate by price bucket ;
- comparaison Polymarket/Kalshi ;
- scripts analytiques utiles pour nos métriques.

Moins utile pour :

- microstructure fine ;
- carnet L2 exact ;
- profiling wallet très détaillé.

### 4.5 Repo `warproxxx/poly_data`

URL :

```text
https://github.com/warproxxx/poly_data
```

Rôle : **ETL simple / cross-check CSV**.

Ce qu’il récupère :

- Gamma markets ;
- Goldsky `OrderFilled` ;
- CSV `trades.csv` ;
- maker/taker/price/size/tx.

Utilisation recommandée :

- référence simple ;
- backup / cross-check ;
- pas base principale de stockage long terme.

### 4.6 APIs Polymarket publiques testées

Endpoints utiles :

```text
https://data-api.polymarket.com/trades?limit=1
https://gamma-api.polymarket.com/markets?limit=1&closed=false
https://clob.polymarket.com/book?token_id=<token_id>
```

État observé :

- `data-api / trades` a répondu HTTP 200 ;
- `gamma-api / markets` a répondu HTTP 200 ;
- un essai sur `clob.polymarket.com/book?token_id=1` a répondu 404, donc l’endpoint doit être utilisé avec un vrai `token_id`, pas tel quel.

Utilité :

- Gamma : métadonnées marchés/events ;
- data-api : trades récents/historiques selon limites ;
- CLOB : carnet courant, utile pour observer live mais pas pour reconstruire tout l’historique sans snapshots.

---

## 5. Architecture cible dans P-core

Respecter les frontières existantes :

```text
prediction_core = primitives génériques
weather_pm      = domaine météo / Polymarket
panoptique      = observation / shadow profiles / evidence
```

### 5.1 `weather_pm`

Responsable de :

- classification des marchés météo ;
- import historique trades/wallets ;
- construction dataset trade/no-trade ;
- extraction des features météo ;
- patterns par compte ;
- runners paper météo.

Modules probables :

```text
python/src/weather_pm/account_trade_import.py
python/src/weather_pm/account_universe.py
python/src/weather_pm/weather_market_classifier.py
python/src/weather_pm/shadow_dataset.py
python/src/weather_pm/account_profile.py
python/src/weather_pm/account_pattern_extractor.py
python/src/weather_pm/orderbook_context_import.py
python/src/weather_pm/orderbook_features.py
python/src/weather_pm/weather_context.py
python/src/weather_pm/forecast_context.py
python/src/weather_pm/shadow_paper_runner.py
```

### 5.2 `panoptique`

Responsable de :

- profils fantômes ;
- observer live ;
- evidence register ;
- séparation entre observation, hypothèse et décision paper ;
- mesure de crowd-flow / trader-flow.

Modules probables :

```text
python/src/panoptique/shadow_profiles.py
python/src/panoptique/shadow_profile_runner.py
python/src/panoptique/weather_observer.py
python/src/panoptique/market_context_snapshots.py
```

### 5.3 `prediction_core`

Responsable de :

- paper ledger générique ;
- simulation coûts/slippage/frais ;
- evaluation/calibration ;
- contrats replay/paper/live_dry_run ;
- analytics.

À ne pas mettre dans `prediction_core` :

- logique spécifique ColdMath/Poligarch ;
- parsing de titres météo ;
- source/station météo ;
- heuristiques weather-only ;
- logique de scraping de datasets externes.

---

## 6. Modèle de données cible

### 6.1 Trade historique normalisé

```json
{
  "account_handle": "ColdMath",
  "wallet": "0x594edb9112f526fa6a80b8f858a6379c8a2c1c11",
  "market_id": "...",
  "event_id": "...",
  "condition_id": "...",
  "token_id": "...",
  "outcome": "YES",
  "side": "buy",
  "price": 0.21,
  "size": 125.0,
  "timestamp": "2026-04-01T12:35:00Z",
  "tx_hash": "...",
  "block_number": 12345678,
  "maker_taker": "taker"
}
```

### 6.2 Marché météo normalisé

```json
{
  "market_id": "...",
  "question": "Will Paris have a high temperature between 21-22°C on May 4?",
  "city": "Paris",
  "date": "2026-05-04",
  "market_kind": "temperature_exact_bin",
  "measurement_type": "temperature_high",
  "bin_low": 21,
  "bin_high": 22,
  "threshold": null,
  "unit": "celsius",
  "resolution_source": "official_or_market_defined"
}
```

### 6.3 Exemple décisionnel positif/négatif

```json
{
  "label": "trade",
  "account_handle": "ColdMath",
  "market_id": "...",
  "timestamp_bucket": "2026-04-01T12:30:00Z",
  "city": "Paris",
  "market_kind": "temperature_exact_bin",
  "price": 0.21,
  "spread": 0.02,
  "depth_near_touch": 450.0,
  "time_to_resolution_hours": 18.5,
  "forecast_distance_to_bin_center": 0.4,
  "reason": "actual_account_trade"
}
```

Pour une abstention :

```json
{
  "label": "no_trade",
  "account_handle": "ColdMath",
  "market_id": "...",
  "timestamp_bucket": "2026-04-01T12:30:00Z",
  "city": "Paris",
  "market_kind": "temperature_exact_bin",
  "price": 0.19,
  "spread": 0.08,
  "depth_near_touch": 60.0,
  "time_to_resolution_hours": 18.5,
  "reason": "similar_surface_no_account_trade"
}
```

### 6.4 Shadow profile

```json
{
  "profile_id": "shadow_coldmath_v0",
  "source_account": "ColdMath",
  "wallet": "0x594edb9112f526fa6a80b8f858a6379c8a2c1c11",
  "profile_type": "temperature_bin_specialist",
  "preferred_cities": ["London", "Seoul", "New York City", "Paris"],
  "preferred_market_kinds": ["temperature_exact_bin", "temperature_threshold"],
  "entry_price_band": [0.08, 0.32],
  "median_time_to_resolution_hours": 18.0,
  "liquidity_rule": "avoid_wide_spread_low_depth",
  "paper_only": true,
  "live_order_allowed": false
}
```

---

## 7. Plan d’implémentation détaillé

## Phase 0 — Plan repo et audit local

**Objectif :** documenter l’état réel avant d’écrire du code.

⚠️ Cette phase ne doit pas retarder la création des profils. Elle sert seulement à éviter de dupliquer des modules existants.

Actions :

- vérifier les modules existants dans `/home/jul/P-core/python/src/weather_pm`, `/home/jul/P-core/python/src/panoptique`, `/home/jul/P-core/python/src/prediction_core` ;
- vérifier les tests existants ;
- ajouter ce plan sous `docs/plans/` ;
- ne pas créer de nouveau repo.

Livrable :

```text
docs/plans/2026-04-28-polymarket-weather-shadow-profiles-references.md
```

Validation :

```bash
cd /home/jul/P-core
git status --short
PYTHONPATH=python/src python3 -m pytest python/tests/test_weather_winning_patterns.py -q
```

## Phase 1 — Import historique ciblé immédiat

**Objectif :** importer les trades historiques des comptes v0 et produire tout de suite les features disponibles sans attendre l’observer live.

Cette phase est la source principale de la v0 : elle doit suffire à produire top marchés, top villes, timing, taille, PnL par type de marché et premiers patterns.

Comptes v0 :

```text
ColdMath
Poligarch
Railbird
```

Sources :

```text
SII-WANGZJ/Polymarket_data HF
SII-WANGZJ/Polymarket_data GitHub pour schéma/ETL
```

Créer :

```text
python/src/weather_pm/account_trade_import.py
python/tests/test_weather_account_trade_import.py
```

Sortie :

```text
data/polymarket/account_trades/weather_account_trades.parquet
```

Critères d’acceptation :

- les 3 wallets v0 sont retrouvés ;
- seuls les marchés météo sont conservés ;
- chaque trade a `wallet`, `market_id`, `token_id`, `price`, `size`, `timestamp` ;
- les champs inconnus sont explicitement `null`, pas inventés.

## Phase 2 — Classification marchés météo

**Objectif :** transformer les titres Polymarket météo en features structurées.

Créer :

```text
python/src/weather_pm/weather_market_classifier.py
python/tests/test_weather_market_classifier.py
```

Classes initiales :

```text
temperature_exact_bin
temperature_threshold
rain_threshold
snow_threshold
wind_threshold
humidity_threshold
other_weather
unknown
```

Priorité v0 :

```text
temperature_exact_bin
temperature_threshold
```

Critères d’acceptation :

- extraire ville, date, unité, seuil/bin quand présent ;
- ne pas halluciner les champs ambigus ;
- produire `unknown` quand le titre n’est pas parseable.

## Phase 3 — Dataset trades + non-trades

**Objectif :** apprendre aussi les abstentions.

Créer :

```text
python/src/weather_pm/shadow_dataset.py
python/tests/test_weather_shadow_dataset.py
```

Méthode :

- positif = trade réel du compte ;
- négatif = marché météo similaire actif dans la même fenêtre où le compte n’a pas tradé ;
- grouper par ville/date/type/surface ;
- construire des buckets temporels, par exemple 5m/15m/1h selon disponibilité.

Sortie :

```text
data/polymarket/shadow_profiles/weather_decision_examples.parquet
```

Critères d’acceptation :

- chaque exemple a `label = trade` ou `label = no_trade` ;
- les no-trades ne sont générés que si le marché était réellement observable/actif ;
- chaque no-trade a une raison explicite.

## Phase 4 — Contexte orderbook historique

**Objectif :** reconstituer le contexte de liquidité autour des trades.

Sources :

```text
evan-kolberg/prediction-market-backtesting
PMXT hourly L2 archive
Telonex full-depth snapshots si accès disponible
```

Créer :

```text
python/src/weather_pm/orderbook_context_import.py
python/src/weather_pm/orderbook_features.py
python/tests/test_weather_orderbook_context_import.py
python/tests/test_weather_orderbook_features.py
```

Features :

```text
best_bid
best_ask
mid
spread
depth_yes
depth_no
imbalance
microprice
available_size_at_price
price_move_before_5m
price_move_after_5m
volume_before_15m
```

Critères d’acceptation :

- au moins 20 trades historiques v0 enrichis avec contexte orderbook ;
- si contexte manquant, marquer `orderbook_context_available=false` ;
- ne pas remplir avec des valeurs devinées.

## Phase 5 — Contexte météo historique

**Objectif :** savoir quelle information météo était disponible au moment de la décision.

Sources candidates :

```text
Open-Meteo archive / forecast
NOAA
Wunderground
HKO
AviationWeather / METAR / TAF
sources officielles indiquées par les marchés
```

Créer :

```text
python/src/weather_pm/weather_context.py
python/src/weather_pm/forecast_context.py
python/tests/test_weather_context.py
```

Features :

```text
forecast_value
forecast_delta_1h
forecast_delta_3h
forecast_delta_6h
model_confidence
distance_to_threshold
distance_to_bin_center
official_source_available
source_freshness_minutes
```

Critères d’acceptation :

- source et timestamp de forecast toujours stockés ;
- distinguer forecast, observation officielle et résolution Polymarket ;
- ne jamais mélanger donnée connue après coup avec donnée disponible au moment T.

## Phase 6 — Profils comportementaux par compte — livrable immédiat

**Objectif :** produire une fiche lisible par trader à partir de l’historique, sans attendre le live.

Cette phase peut être exécutée dès que les trades historiques et la classification météo sont disponibles. Les métriques qui nécessitent du live doivent être marquées `missing_live_context`, pas bloquer le profil.

Créer :

```text
python/src/weather_pm/account_profile.py
python/src/weather_pm/account_pattern_extractor.py
python/tests/test_weather_account_profile.py
```

Mesures :

```text
preferred_cities
preferred_market_kinds
entry_price_distribution
avg_size
median_time_to_resolution
side_bias_yes_no
spread_tolerance
depth_requirement
early_or_late_entry
abstention_patterns
```

Sortie :

```text
data/polymarket/shadow_profiles/account_profiles/*.json
```

Critères d’acceptation :

- profil généré pour ColdMath, Poligarch, Railbird ;
- chaque conclusion est liée à des compteurs/samples ;
- petits échantillons marqués `not_enough_data`.

### 6.5 Activation/désactivation des profils

Chaque shadow profile doit avoir un état opérateur indépendant :

```json
{
  "profile_id": "shadow_coldmath_v0",
  "enabled": true,
  "disabled_reason": null,
  "paper_decisions_enabled": true,
  "live_capture_trigger_enabled": true,
  "history_backtest_enabled": true
}
```

Règles :

- `enabled=false` désactive les décisions paper live du profil ;
- l’historique et les backtests restent consultables ;
- la désactivation ne supprime jamais les données ;
- les rapports affichent clairement `enabled=false` et `disabled_reason` ;
- un compte suivi peut aussi être désactivé séparément d’un profil clusterisé.

## Phase 7 — Shadow profiles v0 — créer directement depuis l’historique

**Objectif :** transformer les profils observés en agents simulés paper-only, immédiatement après les profils comportementaux historiques.

Ne pas attendre l’orderbook live pour créer ces profils. Les règles de liquidité/spread doivent simplement être annotées avec un niveau de confiance plus faible tant que le contexte live manque.

Créer :

```text
python/src/panoptique/shadow_profiles.py
python/src/panoptique/shadow_profile_runner.py
python/tests/test_panoptique_shadow_profiles.py
```

Décisions possibles :

```text
trade
trade_small
skip
not_enough_data
blocked_by_liquidity
blocked_by_stale_weather_source
```

Sortie exemple :

```json
{
  "profile_id": "shadow_coldmath_v0",
  "market_id": "...",
  "decision": "trade",
  "side": "YES",
  "limit_price": 0.21,
  "confidence": 0.74,
  "reason": "matches historical exact-bin late-entry pattern",
  "paper_only": true,
  "live_order_allowed": false
}
```

Critères d’acceptation :

- aucune décision ne peut créer d’ordre réel ;
- chaque trade simulé a une raison et un niveau de confiance ;
- chaque skip a une raison exploitable.

## Phase 8 — Paper ledger et évaluation

**Objectif :** mesurer si les profils reconstruits valent quelque chose.

Réutiliser :

```text
prediction_core/paper
weather_pm/paper_ledger.py
prediction_core/evaluation
prediction_core/execution
```

Créer si nécessaire :

```text
python/src/weather_pm/shadow_paper_runner.py
python/tests/test_weather_shadow_paper_runner.py
```

Métriques :

```text
paper PnL
hit rate
Brier score
avg edge captured
skip quality
false positives
missed winners
cost-adjusted PnL
slippage-adjusted PnL
```

Baselines :

```text
market_price_baseline
weather_probability_baseline
naive_threshold_profile
random_liquid_market_baseline
```

Critères d’acceptation :

- PnL affiché net de spread/slippage/frais estimés ;
- aucune performance déclarée sans baseline ;
- split train/test ou période out-of-sample obligatoire.

## Phase 9 — Observer live continu — validation/correction, pas démarrage

**Objectif :** collecter les données qui ne sont pas récupérables après coup pour vérifier que les profils historiques sont réellement tradables.

L’observer live n’est pas un prérequis à la v0 des shadow profiles. Il est une couche de validation/correction : orderbook exact, abstentions propres, forecast-at-time, surface complète et microstructure.

Créer :

```text
python/src/panoptique/weather_observer.py
python/src/panoptique/market_context_snapshots.py
python/tests/test_panoptique_weather_observer.py
```

Fréquences recommandées :

| Donnée | Fréquence |
|---|---:|
| metadata marchés météo | 15-30 min |
| compact orderbook watchlist | 1-5 min |
| full book | autour trades/gros mouvements |
| trades comptes suivis | 1-5 min |
| météo/forecast | 15-60 min selon marché |

Stockage recommandé :

```text
data/polymarket/live_context/compact_snapshots/
data/polymarket/live_context/full_book_events/
data/polymarket/live_context/forecast_snapshots/
data/polymarket/live_context/observed_trades/
```

Critères d’acceptation :

- observer borné, pas full book illimité ;
- chaque snapshot a une source et un timestamp ;
- compression/rotation prévue ;
- paper-only/read-only.

## Phase 10 — Dashboard / cockpit

**Objectif :** rendre le système exploitable par opérateur.

Sources dashboard :

```text
ClickHouse / Grafana existant P-core
artifacts JSON/Parquet pour audit
```

Créer ou compléter :

```text
infra/analytics/grafana/dashboards/weather-shadow-profiles.json
python/src/weather_pm/analytics_adapter.py
python/tests/test_weather_shadow_analytics.py
```

Panels souhaités :

```text
Top shadow profiles
Profils qui auraient tradé maintenant
Marchés où plusieurs profils convergent
Marchés où bons comptes réels viennent de bouger
Abstentions importantes
PnL paper par profil
Hit rate par ville
Hit rate par type de marché
Source météo fraîche/périmée
Orderbook spread/depth
```

Critères d’acceptation :

- dashboard sans secret ;
- pas de bouton/order live ;
- décisions marquées paper-only ;
- liens vers preuves/sources.

---

## 8. Roadmap courte recommandée — fast-track historique d’abord

### Étape 1 — Profils historiques immédiats

1. Importer/charger les trades historiques des comptes prioritaires.
2. Classifier les marchés météo déjà présents.
3. Générer les fiches comptes : villes, marchés, timing, tailles, PnL, prix d’entrée, fréquence.
4. Créer les premiers profils comportementaux même si certaines variables live manquent.

Résultat : on sait déjà **ce qu’ils font** et quels patterns reviennent, sans attendre de nouvelles données.

### Étape 2 — Shadow profiles v0 immédiats

1. Transformer les fiches comptes en profils paper-only.
2. Créer des profils explicables : `shadow_coldmath_v0`, `shadow_poligarch_v0`, `shadow_railbird_v0`, puis profils clusterisés.
3. Marquer explicitement les hypothèses faibles : spread, profondeur, forecast-at-time, abstentions.
4. Produire une sortie opérateur lisible : règles, exemples, confiance, limites.

Résultat : premiers agents simulés basés sur comportements historiques, sans live observer préalable.

### Étape 3 — Backtest/replay historique

1. Rejouer les profils sur historique avec coûts approximés.
2. Comparer contre baselines : market price, météo baseline, naive threshold, random liquid.
3. Séparer train/test ou périodes out-of-sample.
4. Rejeter les profils qui ne battent pas les baselines après coûts estimés.

Résultat : on sait si les profils ont un signal exploitable, même avant validation microstructurelle live.

### Étape 4 — Observer live TrueNAS agressif en parallèle

1. Démarrer l’observer sur TrueNAS avec scénario agressif ciblé météo.
2. Capturer uniquement les angles morts : orderbook exact, abstentions, forecast-at-time, surfaces complètes, microstructure.
3. Refuser de démarrer si `/mnt/truenas` n’est pas un mountpoint réel.
4. Utiliser le live pour corriger les profils, pas pour attendre de les créer.

Résultat : les performances historiques sont corrigées par la réalité d’exécution.

### Étape 5 — Décision rapide

Décider à partir de :

- qualité des profils historiques ;
- backtest paper vs baselines ;
- nombre d’hypothèses non vérifiées ;
- premiers écarts observés par le live ;
- coût de stockage réel sur TrueNAS.

La décision initiale ne doit pas attendre 6 mois. Les longs horizons servent uniquement à prouver la robustesse saisonnière.

---

## 9. Questions auxquelles la v1 doit répondre

La v1 est réussie si on peut répondre factuellement :

1. ColdMath entre sur quels types de marchés météo ?
2. Poligarch trade-t-il plus tôt ou plus tard que ColdMath ?
3. Railbird évite-t-il les spreads larges ?
4. Les comptes gagnants préfèrent-ils les bins exacts ou les thresholds ?
5. Quelles villes reviennent le plus dans leurs profits ?
6. À quelle distance de la résolution entrent-ils ?
7. Quels prix d’entrée sont typiques ?
8. Dans quels cas similaires s’abstiennent-ils ?
9. Le contexte orderbook explique-t-il une partie des entrées ?
10. Un shadow profile paper-only bat-il une baseline après coûts ?

---

## 10. Garde-fous

Obligatoires :

```text
paper_only = true
live_order_allowed = false
no wallet
no signing
no real order
no credential
no cancellation
```

Règles :

- ne jamais présenter un backtest in-sample comme une preuve d’edge ;
- ne jamais confondre prédiction météo et prédiction comportement trader ;
- ne jamais inclure de secret dans les artifacts ;
- ne jamais générer de live order depuis un shadow profile ;
- respecter `enabled=false` sur profils/comptes/streams comme un kill switch opérateur ;
- garder les abstentions comme données de première classe ;
- marquer `not_enough_data` au lieu d’être optimiste sur petits échantillons.

---

## 11. Commandes de validation recommandées

Depuis `/home/jul/P-core` :

```bash
PYTHONPATH=python/src python3 -m pytest \
  python/tests/test_weather_winning_patterns.py \
  python/tests/test_weather_strategy_profiles.py \
  python/tests/test_weather_strategy_shortlist.py -q
```

Pour les nouveaux modules :

```bash
PYTHONPATH=python/src python3 -m pytest \
  python/tests/test_weather_account_trade_import.py \
  python/tests/test_weather_market_classifier.py \
  python/tests/test_weather_shadow_dataset.py \
  python/tests/test_weather_account_profile.py \
  python/tests/test_panoptique_shadow_profiles.py \
  python/tests/test_weather_shadow_paper_runner.py -q
```

Contrôle sécurité :

```bash
grep -RInE "private_key|wallet_secret|signing|place_order|cancel_order|live_order_allowed.*true" \
  python/src/weather_pm python/src/panoptique python/src/prediction_core || true
```

Contrôle format :

```bash
git diff --check
python3 -m py_compile \
  python/src/weather_pm/account_trade_import.py \
  python/src/weather_pm/weather_market_classifier.py \
  python/src/weather_pm/shadow_dataset.py \
  python/src/weather_pm/account_profile.py \
  python/src/panoptique/shadow_profiles.py
```

---

## 12. Ordre d’exécution conseillé

Ne pas tout lancer d’un coup.

Ordre recommandé :

1. Phase 1 avec seulement ColdMath, Poligarch, Railbird.
2. Phase 2 température uniquement.
3. Phase 3 dataset positif/négatif minimal.
4. Premier rapport Markdown opérateur.
5. Ensuite seulement Phase 4 orderbook historique.
6. Puis Phase 7 shadow profiles.

La première milestone utile est :

```text
Un rapport qui compare ColdMath / Poligarch / Railbird sur les marchés température :
- marchés tradés,
- marchés évités,
- prix d’entrée,
- timing,
- villes,
- taille,
- premiers signaux de pattern.
```

---

## 13. Résumé décisionnel

Sources à utiliser dans cet ordre :

1. **`SII-WANGZJ/Polymarket_data` HF** — backfill massif trades/wallets.
2. **Repo GitHub `SII-WANGZJ/Polymarket_data`** — schémas et ETL de référence.
3. **`evan-kolberg/prediction-market-backtesting`** — orderbook historique / replay L2.
4. **`Jon-Becker/prediction-market-analysis`** — calibration et analyses marché.
5. **`warproxxx/poly_data`** — cross-check simple CSV/Goldsky.
6. **APIs Polymarket Gamma/data-api/CLOB** — live observer et compléments.
7. **Sources météo officielles/forecast** — contexte décisionnel et résolution.

Comptes v0 :

```text
ColdMath
Poligarch
Railbird
```

Comptes v1 :

```text
Handsanitizer23
Maskache2
xX25Xx
syacxxa
0xhana
dpnd
Amano-Hina
```

Question centrale :

```text
Est-ce que les comportements reconstruits de ces comptes produisent des règles explicables
qui restent positives en paper après spread, slippage et frais ?
```

C’est le critère de valeur. Tout le reste est de l’infrastructure.
