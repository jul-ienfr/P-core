# Miro repos compatibility grid — Polymarket weather seed workflow

Scope: quick local inspection of Julien's 9 linked GitHub repos cloned under `/tmp/miro-repos`.
Goal: decide what is useful for `prediction_core/python` and the `miro-seed-export` bridge.

| Repo | Type | Runtime/storage | Useful API / flow | Polymarket fit | Keep / use |
|---|---|---|---|---|---|
| `666ghj/MiroFish` | upstream multi-agent swarm prediction engine | Flask + Vue, Zep Cloud, OpenAI-compatible LLM, OASIS/Camel | `POST /api/graph/ontology/generate`, poll `/api/graph/task/{task_id}`, then simulation/report | Good simulation target once seeded with clean factual docs | Reference API baseline, but cloud/Zep dependency is friction |
| `Isaiahlp1/MiroFish-English` | English mirror/fork of upstream MiroFish | same as MiroFish | same endpoints | Same as upstream; useful docs only | Docs/reference, not primary runtime |
| `tt-a1i/MiroFish-local` | local-first MiroFish fork | Graphiti + Neo4j local mode, optional Zep | same MiroFish graph/simulation endpoints | Best MiroFish variant for private/local Polymarket experiments | Preferred runtime candidate |
| `jwc19890114/MiroFishOpt` | optimized local-storage fork | Neo4j + Qdrant local/vector, optional Zep | project/list, report download, same backend shape | Strong candidate if stability/local persistence matters | Compare with MiroFish-local before install |
| `aaronjmars/MiroShark` | polished universal swarm engine fork | Flask + Vue, Neo4j, OpenAI-compatible LLM | `POST /api/simulation/ask`, list/status/frame/report/publish endpoints | Good second target; easier question/seed oriented surface | Supported in manifest via `/api/simulation/ask` |
| `BMakx/MiroFish-Trading` | trading/news ingestion wrapper | Python scripts, RSS/PDF/MiroFish upload | scripts call `/api/graph/ontology/generate`, `/api/graph/build`, `/api/graph/task/{task_id}` | Useful pattern for document generation/upload, not core engine | Mine for ingestion ideas only |
| `dpbmaverick98/miroFish-x-Polymarket` | Polymarket + MiroFish glue repo | Node scripts + docs/skills | Polymarket skills, MiroFish startup notes, market fetch scripts | Directly relevant but more glue/docs than robust engine | Mine scripts/docs; avoid copying weak parts blindly |
| `MiroMindAI/MiroThinker` | deep research agent/model/tooling suite | research agents, traces, model ecosystem | not a MiroFish simulation API; research/trace tooling | Useful upstream research/enrichment layer before seeding | Not simulation target; possible future research provider |
| `heyjihyuk-stack/Predictions` | Flask market/news prediction app | Flask, OpenAI, NewsAPI/Finnhub/CoinGecko/Deribit | market/news APIs, knowledge graph endpoints | Adjacent, more general market/news than Polymarket execution | Low priority; reference only |

## Decision

Primary bridge should remain **paper-only factual seed export**:

1. Build factual market seed Markdown from `prediction_core` data.
2. Strip Polymarket prices, volume, liquidity, odds, spreads, orderbook data.
3. Emit manifest with:
   - MiroFish-compatible upload: `/api/graph/ontology/generate`
   - MiroShark-compatible ask: `/api/simulation/ask`
   - explicit `paper_only=true`
   - explicit `live_order_allowed=false`
4. Keep real trading/execution outside MiroFish/MiroShark outputs.

## Next useful implementation steps

- Add an optional `--target mirofish|miroshark|both` once a local runtime is selected.
- Add a `--base-url` override to generate ready-to-run curl for local ports.
- Later: a guarded `miro-run-smoke` command can call health/upload/status, but only paper/simulation endpoints.
