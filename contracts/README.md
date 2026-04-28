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

## Phase 5 — Frontière adaptateurs prediction markets

`prediction_core.execution.prediction_market_adapters` décrit les capacités candidates (`pmxt`, `pykalshi`, `Parsec`, `PolyClawster`) uniquement comme métadonnées d’audit. Ces contrats préservent le langage d’origine : clients Python côté Python pour discovery/replay/paper/calibration, composants Rust côté Rust derrière les contrats communs. La politique par défaut reste `read_only=true`, `paper_only=true`, `live_order_allowed=false` ; toute capacité mutable, mode live, wallet signing, credentials ou primitive d’ordre/cancel réel est bloquée et nécessite une approbation séparée hors de cette frontière.
