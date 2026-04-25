# Execution cost model

`prediction_core.execution` modélise le coût réellement capturable d'un ordre, au-delà d'un simple spread top-of-book.

## Couches séparées

### 1. Market microstructure / trading cost

Ces coûts appartiennent au trade lui-même :

- `quoted_best_bid` / `quoted_best_ask` : meilleur bid/ask observé.
- `quoted_mid_price` : milieu bid/ask quand les deux côtés existent.
- `estimated_avg_fill_price` : prix moyen estimé après sweep du carnet pour la taille demandée.
- `spread_cost` : dérive entre le mid et le top-of-book consommé.
- `book_slippage_cost` : coût supplémentaire créé par la consommation de niveaux plus profonds que le premier niveau.
- `trading_fee_cost` : frais maker/taker appliqués au notionnel exécuté.
- `total_execution_cost` : `spread_cost + book_slippage_cost + trading_fee_cost`.

Ces coûts servent à calculer `edge_net_execution` :

```text
edge_net_execution = edge_gross - total_execution_cost
```

C'est l'edge net du trade avant coûts de mouvement de fonds.

### 2. Funding / transfer cost

Ces coûts sont optionnels et séparés de la microstructure :

- `deposit_fee_cost` : frais fixes + bps pour amener les fonds.
- `withdrawal_fee_cost` : frais fixes + bps pour sortir les fonds.
- `total_all_in_cost` : `total_execution_cost + deposit_fee_cost + withdrawal_fee_cost`.

Ils servent à calculer `edge_net_all_in` :

```text
edge_net_all_in = edge_gross - total_all_in_cost
```

Doctrine : les frais de dépôt/retrait ne doivent pas polluer le score microstructure pur. Ils sont exposés séparément pour décider si un trade reste intéressant en all-in.

## Book depth et fallback

Quand un carnet multi-niveaux est disponible, `estimate_fill_from_book(...)` sweep les niveaux :

- buy : consomme les `asks` du moins cher au plus cher ;
- sell : consomme les `bids` du plus cher au moins cher ;
- si la profondeur est insuffisante, le fill est partiel et `unfilled_quantity` reste positif.

Quand la depth live n'est pas disponible, les surfaces météo restent compatibles avec un fallback top-of-book ou des champs de profondeur déjà normalisés. Le résultat est alors moins précis : le système peut estimer spread/frais, mais le slippage multi-niveaux reste best-effort.

## Worked example

Ordre : buy 20 contracts.

Carnet :

```text
best bid: 0.42
asks:
  10 @ 0.45
  10 @ 0.46
```

Frais :

```text
taker fee: 50 bps
deposit: 1.00 USDC + 10 bps
withdrawal: 2.00 USDC + 20 bps
fair probability: 0.60
```

Calcul :

```text
gross_notional = 10 * 0.45 + 10 * 0.46 = 9.10
estimated_avg_fill_price = 9.10 / 20 = 0.455
quoted_mid_price = (0.42 + 0.45) / 2 = 0.435
spread_cost = (0.45 - 0.435) * 20 = 0.30
book_slippage_cost = (0.455 - 0.45) * 20 = 0.10
trading_fee_cost = 9.10 * 50 / 10000 = 0.0455

deposit_fee_cost = 1.00 + 9.10 * 10 / 10000 = 1.0091
withdrawal_fee_cost = 2.00 + 9.10 * 20 / 10000 = 2.0182

total_execution_cost = 0.30 + 0.10 + 0.0455 = 0.4455
total_all_in_cost = 0.4455 + 1.0091 + 2.0182 = 3.4728

edge_gross = (0.60 - 0.455) * 20 = 2.90
edge_net_execution = 2.90 - 0.4455 = 2.4545
edge_net_all_in = 2.90 - 3.4728 = -0.5728

effective_unit_price = (9.10 + 3.4728) / 20 = 0.62864
```

Interprétation : le trade est attractif en microstructure pure (`edge_net_execution > 0`), mais non rentable si on doit réellement payer dépôt + retrait pour cette petite taille (`edge_net_all_in < 0`).

## Surfaces actuelles

- `prediction_core.execution.quote_execution_cost(...)` / `estimate_order_cost(...)` : façade canonique.
- `/weather/paper-cycle` : peut dériver automatiquement `fee_paid`, `slippage_bps`, `effective_price_after_fees` et stocker le breakdown sous `simulation.metadata.execution` quand un book + fee schedule sont fournis.
- `weather_pm.scoring` et `weather_pm.decision` utilisent `edge_net_execution` quand il est disponible, avec fallback conservateur sur `raw_edge` si le coût n'est pas calculable.
