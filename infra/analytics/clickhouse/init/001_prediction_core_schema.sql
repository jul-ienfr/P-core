CREATE DATABASE IF NOT EXISTS prediction_core;

CREATE TABLE IF NOT EXISTS prediction_core.prediction_runs (
    run_id String,
    strategy_id String DEFAULT '',
    profile_id String DEFAULT '',
    market_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    completed_at Nullable(DateTime64(3, 'UTC')),
    source String,
    mode String,
    status String,
    strategy_count UInt32,
    profile_count UInt32,
    market_count UInt32,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id);

CREATE TABLE IF NOT EXISTS prediction_core.market_snapshots (
    run_id String,
    strategy_id String DEFAULT '',
    profile_id String DEFAULT '',
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    mode String DEFAULT '',
    slug String,
    question String,
    active Bool,
    closed Bool,
    yes_price Nullable(Float64),
    best_bid Nullable(Float64),
    best_ask Nullable(Float64),
    volume Nullable(Float64),
    liquidity Nullable(Float64),
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, token_id);

CREATE TABLE IF NOT EXISTS prediction_core.orderbook_snapshots (
    run_id String,
    strategy_id String DEFAULT '',
    profile_id String DEFAULT '',
    market_id String,
    token_id String,
    observed_at DateTime64(3, 'UTC'),
    mode String DEFAULT '',
    best_bid Nullable(Float64),
    best_ask Nullable(Float64),
    spread Nullable(Float64),
    bid_depth_levels UInt32,
    ask_depth_levels UInt32,
    bids_json String,
    asks_json String,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, token_id);

CREATE TABLE IF NOT EXISTS prediction_core.strategy_signals (
    run_id String,
    strategy_id String,
    profile_id String DEFAULT '',
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    mode String,
    signal_id String,
    signal_type String,
    side String,
    probability Nullable(Float64),
    market_price Nullable(Float64),
    edge Nullable(Float64),
    confidence Nullable(Float64),
    paper_only Bool DEFAULT true,
    live_order_allowed Bool DEFAULT false,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, signal_id);

CREATE TABLE IF NOT EXISTS prediction_core.profile_decisions (
    run_id String,
    strategy_id String,
    profile_id String,
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    mode String,
    decision_status String,
    skip_reason String DEFAULT '',
    execution_mode String DEFAULT '',
    edge Nullable(Float64),
    limit_price Nullable(Float64),
    requested_spend_usdc Nullable(Float64),
    capped_spend_usdc Nullable(Float64),
    source_ok Bool,
    orderbook_ok Bool,
    risk_ok Bool,
    paper_only Bool DEFAULT true,
    live_order_allowed Bool DEFAULT false,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, decision_status);

CREATE TABLE IF NOT EXISTS prediction_core.paper_orders (
    run_id String,
    strategy_id String,
    profile_id String,
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    mode String,
    paper_order_id String,
    side String,
    price Nullable(Float64),
    size Nullable(Float64),
    spend_usdc Nullable(Float64),
    status String,
    opening_fee_usdc Nullable(Float64),
    opening_slippage_usdc Nullable(Float64),
    estimated_exit_cost_usdc Nullable(Float64),
    paper_only Bool DEFAULT true,
    live_order_allowed Bool DEFAULT false,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, paper_order_id);

CREATE TABLE IF NOT EXISTS prediction_core.paper_positions (
    run_id String,
    strategy_id String,
    profile_id String,
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    mode String,
    paper_position_id String,
    quantity Float64,
    avg_price Nullable(Float64),
    exposure_usdc Nullable(Float64),
    mtm_bid_usdc Nullable(Float64),
    status String,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, paper_position_id);

CREATE TABLE IF NOT EXISTS prediction_core.paper_pnl_snapshots (
    run_id String,
    strategy_id String,
    profile_id String,
    market_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    mode String,
    gross_pnl_usdc Nullable(Float64),
    net_pnl_usdc Nullable(Float64),
    costs_usdc Nullable(Float64),
    exposure_usdc Nullable(Float64),
    roi Nullable(Float64),
    winrate Nullable(Float64),
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id);

CREATE TABLE IF NOT EXISTS prediction_core.execution_events (
    run_id String,
    strategy_id String,
    profile_id String,
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    execution_event_id String,
    event_type String,
    mode String,
    paper_only Bool DEFAULT true,
    live_order_allowed Bool DEFAULT false,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, execution_event_id);

CREATE TABLE IF NOT EXISTS prediction_core.strategy_configs (
    strategy_id String,
    observed_at DateTime64(3, 'UTC'),
    enabled Bool,
    mode String,
    allow_live Bool DEFAULT false,
    settings String,
    raw String
)
ENGINE = ReplacingMergeTree(observed_at)
ORDER BY strategy_id;

CREATE TABLE IF NOT EXISTS prediction_core.resolution_events (
    run_id String,
    strategy_id String DEFAULT '',
    profile_id String DEFAULT '',
    market_id String,
    observed_at DateTime64(3, 'UTC'),
    mode String DEFAULT '',
    resolved_at Nullable(DateTime64(3, 'UTC')),
    outcome String,
    outcome_price Nullable(Float64),
    closed Bool,
    source String,
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, market_id, run_id, strategy_id, profile_id);

CREATE TABLE IF NOT EXISTS prediction_core.strategy_metrics (
    run_id String,
    strategy_id String,
    profile_id String DEFAULT '',
    market_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    mode String,
    signal_count UInt32,
    trade_count UInt32,
    skip_count UInt32,
    avg_edge Nullable(Float64),
    gross_pnl_usdc Nullable(Float64),
    net_pnl_usdc Nullable(Float64),
    exposure_usdc Nullable(Float64),
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id);

CREATE TABLE IF NOT EXISTS prediction_core.profile_metrics (
    run_id String,
    strategy_id String DEFAULT '',
    profile_id String,
    market_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    mode String,
    decision_count UInt32,
    trade_count UInt32,
    skip_count UInt32,
    exposure_usdc Nullable(Float64),
    gross_pnl_usdc Nullable(Float64),
    net_pnl_usdc Nullable(Float64),
    roi Nullable(Float64),
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id);

CREATE TABLE IF NOT EXISTS prediction_core.debug_decisions (
    run_id String,
    strategy_id String,
    profile_id String,
    market_id String,
    token_id String DEFAULT '',
    observed_at DateTime64(3, 'UTC'),
    mode String,
    decision_status String,
    skip_reason String DEFAULT '',
    edge Nullable(Float64),
    limit_price Nullable(Float64),
    source_ok Bool,
    orderbook_ok Bool,
    risk_ok Bool,
    blocker String DEFAULT '',
    raw String
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(observed_at)
ORDER BY (observed_at, run_id, strategy_id, profile_id, market_id, decision_status);
