# prediction_core/contracts

Zone des contrats partagés entre Rust, Python et TypeScript.

Cible :
- schémas JSON des artefacts
- conventions Postgres
- versions de payloads
- documents d’interface entre moteur live et cockpit

## Phase 1 — Parité replay / paper / live_dry_run

Périmètre strict : replay, paper trading et futur moteur Rust en `live_dry_run` uniquement. Aucun payload de contrat ne doit contenir de secret, de signature wallet, de client venue mutable, ni de primitive permettant un `place/cancel order` réel.

Flux canonique :

1. `prediction_core.replay` produit des événements marché déterministes et des signatures sans champs de bookkeeping.
2. `prediction_core.execution` transforme un carnet + des hypothèses d’exécution en quote déterministe via `ExecutionAssumptions` / `ExecutionParityQuote`.
3. `prediction_core.paper` consomme la quote pour produire ordres papier, fills, positions et PnL simulés.
4. Le futur moteur Rust live doit accepter les mêmes concepts côté `pm_types`, mais seulement sous mode explicite `LiveDryRun` tant que l’exécution réelle n’est pas autorisée séparément.

Contrats stabilisés pour la Phase 1 :

- `MarketEvent` / `OrderBookSnapshot` : événement marché, niveaux `price` + `quantity`, top-of-book dérivé côté consommateur.
- `ExecutionAssumptions` : latence, slippage additionnel, position de queue, sweep multi-niveaux, frais et politique de rejet profondeur/carnet vide.
- `ExecutionParityQuote` : quantité demandée/remplie/non remplie, prix moyen, coûts de slippage, latence, queue, niveaux consommés, statut et blocker.
- `PaperTradeSimulation` / `PaperTradeFill` : ordre/fill papier, `metadata.execution.parity_quote` si la quote de parité est activée.
- `PositionSnapshot` : position/PnL papier ou dry-run avec flag `paper_only` explicite.

Scénarios replay déterministes couverts côté Python : carnet vide, spread large avec latence/frais, fill partiel, rejet profondeur insuffisante, désactivation du sweep multi-niveaux, position de queue qui consomme le top-of-book.

## Phase 2 — Socle risk / sizing générique

`prediction_core.risk.evaluate_risk_sizing` fournit un gate déterministe paper/dry-run indépendant des modèles prédictifs. Les payloads `RiskSizingInput`, `RiskSizingLimits`, `RiskSizingDecision` et `RiskSizingSnapshot` couvrent notional, exposition, drawdown, turnover, concentration, coût all-in et edge net minimum. Les sorties `to_dict()` incluent toujours `paper_only=true` et `live_order_allowed=false` pour ingestion ClickHouse/Grafana sans autoriser d’ordre réel.

Comparaison avec les hypothèses `hftbacktest` :

- Latency : modélisée explicitement (`latency_ms`) et propagée dans la quote, sans simulation temporelle probabiliste.
- Slippage : coût carnet + slippage additionnel en bps.
- Queue position : approximation déterministe par `queue_ahead_quantity` consommant la profondeur prioritaire.
- Sweep multi-niveaux : activable/désactivable via `allow_multi_level_sweep`.
- Fees : maker/taker, min fee, deposit/withdrawal bps/fixes.
- Limite connue : pas encore de modèle probabiliste d’annulations devant nous ni de relecture tick-by-tick complète façon hftbacktest.

## Phase 4 — Contrats Rust P-core prediction markets

Périmètre strict : contrats Rust locaux, fixtures offline et validation déterministe. Cette phase ne définit aucun client réseau, aucune connexion stream/websocket, aucune dépendance async/network additionnelle, et aucune capacité d'exécution live.

### `pm_feed` — normalisation read-only

`rust/crates/pm_feed` convertit des messages déjà reçus ou chargés depuis fixture en événements canoniques :

- `FeedMessage` conserve les métadonnées d'audit (`source`, `venue`, `market_id`, `symbol`, `received_at`, `message_type`) et le `raw_json` original.
- `Trade` et `Bbo` se convertissent en `MarketEvent` sans effet de bord.
- `L2Snapshot` se convertit en `OrderBookSnapshot` avec niveaux `BookLevel { price, quantity }`.
- `FeedMessageType::L2Delta` reste une frontière de normalisation (`L2DeltaPlaceholder`) tant que le mapping venue-spécifique n'est pas approuvé.

Aucune fonction de `pm_feed` ne doit ouvrir de socket, appeler une API venue, signer une requête ou muter un état distant. Les entrées attendues sont des payloads offline, des fixtures ou des messages fournis par un composant read-only approuvé séparément.

### `BookDelta` / `L2Update` — replay tick-level et carnet

Le contrat L2 canonique côté `pm_types` est `BookDelta` : timestamp, séquence, côté (`Bid`/`Ask`), prix, quantité et indicateur `is_trade`. Il couvre l'usage `L2Update` du plan sous un nom Rust stabilisé.

`rust/crates/pm_book` applique ces deltas en replay tick-level :

- prix finis dans l'intervalle prediction-market `[0.0, 1.0]`, prix strictement positif pour les niveaux actifs ;
- quantité finie et non négative ; `quantity == 0.0` supprime le niveau ;
- séquences strictement contiguës quand `last_seq` est connu ;
- normalisation déterministe : bids décroissants, asks croissants ;
- rejet des carnets croisés sans mutation de l'état précédent.

Les fonctions de simulation de fill (`estimate_fill_from_book`, `simulate_spend_fill`, `simulate_exit_value`) restent des estimations locales de replay/paper : elles ne produisent pas de fill exchange et ne soumettent aucun ordre.

### `pm_storage::market_data_log` — JSONL offline

`rust/crates/pm_storage/src/market_data_log.rs` définit un journal JSONL local : un `MarketDataLogRecord` par ligne avec `market_id`, `ts` et un `MarketDataPayload` tagué (`market_event`, `order_book_snapshot`, `book_delta`).

Garanties :

- encodage/décodage `serde_json` ligne par ligne ;
- append/write/read locaux seulement via filesystem ;
- itération filtrable par `market_id` et fenêtre temporelle inclusive ;
- conversion utilitaire vers `MarketEvent`/`OrderBookSnapshot` pour replay et validation.

Ce module ne copie aucun code Tectonicdb, n'embarque aucun client de base distante et ne définit aucun transport réseau. Les optimisations async, streaming et stockage externe sont explicitement différées.

### `live_engine` — advisory / dry-run only

`rust/crates/live_engine` assemble source de marché normalisée, signal, risk gate, intent advisory et ledger local/in-memory. La frontière d'exécution autorisée est `DryRunAdvisory` :

- un signal approuvé peut créer un `OrderIntent` à statut advisory ;
- le rapport d'exécution est volontairement `rejected` avec `simulation_only_advisory_no_exchange_fill` ;
- `fill`, `fill_row` restent `None` ;
- `FillMetadata.live_submit` reste `false`.

`live_engine` ne doit exposer aucun sink mutable vers venue réelle. Toute évolution vers exécution réelle nécessite une phase séparée, une revue de sécurité et des contrats distincts.

### Garde-fous obligatoires

Interdits dans ces contrats Rust et leurs docs opérationnelles :

- primitives `place_order`, `cancel_order`, submit/cancel live, signing/wallet/private key/credentials ;
- client venue mutable, mutation de carnet distant, ordre réel ou fill exchange simulé comme réel ;
- commande réseau, stream marketdata live ou dépendance async/network nouvelle dans cette phase ;
- code copié de Tectonicdb ou couplage à un stockage externe.

Autorisés : fixtures offline, JSONL local, replay tick-by-tick déterministe, orderbook local, intents advisory non exécutables, tests unitaires/workspace `cargo test` depuis `/home/jul/P-core/rust`.

## Phase 5 — Frontière adaptateurs prediction markets

`prediction_core.execution.prediction_market_adapters` décrit les capacités candidates (`pmxt`, `pykalshi`, `Parsec`, `PolyClawster`) uniquement comme métadonnées d’audit. Ces contrats préservent le langage d’origine : clients Python côté Python pour discovery/replay/paper/calibration, composants Rust côté Rust derrière les contrats communs. La politique par défaut reste `read_only=true`, `paper_only=true`, `live_order_allowed=false` ; toute capacité mutable, mode live, wallet signing, credentials ou primitive d’ordre/cancel réel est bloquée et nécessite une approbation séparée hors de cette frontière.
