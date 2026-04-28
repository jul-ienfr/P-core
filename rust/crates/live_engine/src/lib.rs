use pm_book::TopOfBook;
use pm_executor::{build_order_intent, OrderIntent};
use pm_ledger::LedgerEnvelope;
use pm_risk::{approve_if_spread_not_crossed, RiskDecision};
use pm_signal::{signal_from_book, SignalConfig, SignalEvent};
use pm_storage::{
    execution_report_row, order_intent_row, risk_decision_row, ExecutionReportRow, FillRow,
    OrderIntentRow, RiskDecisionRow,
};
use pm_types::{
    ExecutionStatus, FillEvent, MarketEvent, OrderBookSnapshot, RiskDecisionStatus, Venue,
};

#[derive(Debug, Clone)]
pub struct LiveEngineOutput {
    pub signal: Option<SignalEvent>,
    pub risk_decision: RiskDecision,
    pub risk_decision_row: RiskDecisionRow,
    pub order_intent: Option<OrderIntent>,
    pub order_intent_row: Option<OrderIntentRow>,
    pub fill: Option<FillEvent>,
    pub fill_row: Option<FillRow>,
    pub fill_metadata: Option<FillMetadata>,
    pub execution_report: ExecutionReportRow,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FillMetadata {
    pub source: &'static str,
    pub status: &'static str,
    pub live_submit: bool,
}

#[derive(Debug, Clone)]
pub struct NormalizedMarketData {
    pub venue: Venue,
    pub market_id: String,
    pub top_of_book: TopOfBook,
}

impl NormalizedMarketData {
    pub fn from_market_event(event: &MarketEvent) -> Self {
        let mut top_of_book = TopOfBook::default();
        top_of_book.apply(event);
        Self {
            venue: event.venue.clone(),
            market_id: event.market_id.clone(),
            top_of_book,
        }
    }

    pub fn from_order_book_snapshot(
        venue: Venue,
        market_id: impl Into<String>,
        snapshot: &OrderBookSnapshot,
    ) -> Self {
        let best_bid = snapshot.bids.first().map(|level| level.price);
        let best_ask = snapshot.asks.first().map(|level| level.price);
        Self {
            venue,
            market_id: market_id.into(),
            top_of_book: TopOfBook { best_bid, best_ask },
        }
    }
}

pub trait MarketDataSource {
    fn next_market_data(&mut self) -> Option<NormalizedMarketData>;
}

pub struct EventMarketDataSource<I> {
    events: I,
}

impl<I> EventMarketDataSource<I> {
    pub fn new(events: I) -> Self {
        Self { events }
    }
}

impl<I> MarketDataSource for EventMarketDataSource<I>
where
    I: Iterator<Item = MarketEvent>,
{
    fn next_market_data(&mut self) -> Option<NormalizedMarketData> {
        self.events
            .next()
            .map(|event| NormalizedMarketData::from_market_event(&event))
    }
}

pub trait StrategySignal {
    fn signal(&self, market: &NormalizedMarketData) -> Option<SignalEvent>;
}

#[derive(Debug, Clone)]
pub struct PmSignalStrategy {
    config: SignalConfig,
}

impl PmSignalStrategy {
    pub fn new(config: SignalConfig) -> Self {
        Self { config }
    }
}

impl StrategySignal for PmSignalStrategy {
    fn signal(&self, market: &NormalizedMarketData) -> Option<SignalEvent> {
        signal_from_book(
            &self.config,
            market.venue.clone(),
            market.market_id.clone(),
            &market.top_of_book,
        )
    }
}

pub trait RiskGate {
    fn evaluate(&self, market: &NormalizedMarketData, signal: Option<&SignalEvent>)
        -> RiskDecision;
}

#[derive(Debug, Clone, Copy, Default)]
pub struct SpreadRiskGate;

impl RiskGate for SpreadRiskGate {
    fn evaluate(
        &self,
        market: &NormalizedMarketData,
        _signal: Option<&SignalEvent>,
    ) -> RiskDecision {
        approve_if_spread_not_crossed(market.top_of_book.best_bid, market.top_of_book.best_ask)
    }
}

pub trait ExecutionSink {
    fn execute(
        &mut self,
        market: &NormalizedMarketData,
        intent: &OrderIntent,
    ) -> ExecutionReportRow;
}

#[derive(Debug, Clone, Copy, Default)]
pub struct DryRunAdvisory;

impl DryRunAdvisory {
    pub const REPORT_MESSAGE: &'static str = "simulation_only_advisory_no_exchange_fill";

    pub fn fill_metadata() -> FillMetadata {
        FillMetadata {
            source: "simulation_only",
            status: "advisory_no_exchange_fill",
            live_submit: false,
        }
    }
}

impl ExecutionSink for DryRunAdvisory {
    fn execute(
        &mut self,
        market: &NormalizedMarketData,
        _intent: &OrderIntent,
    ) -> ExecutionReportRow {
        execution_report_row(
            market.market_id.clone(),
            &ExecutionStatus::Rejected,
            Some(Self::REPORT_MESSAGE.to_string()),
        )
    }
}

#[derive(Debug, Clone)]
pub enum LedgerRecord {
    OrderIntent(OrderIntentRow),
    ExecutionReport(ExecutionReportRow),
}

pub trait LedgerSink {
    fn record_order_intent(&mut self, intent: &OrderIntentRow);
    fn record_execution_report(&mut self, report: &ExecutionReportRow);
}

#[derive(Debug, Default)]
pub struct NoopLedgerSink;

impl LedgerSink for NoopLedgerSink {
    fn record_order_intent(&mut self, _intent: &OrderIntentRow) {}
    fn record_execution_report(&mut self, _report: &ExecutionReportRow) {}
}

#[derive(Debug, Default)]
pub struct InMemoryLedgerSink {
    records: Vec<LedgerRecord>,
}

impl InMemoryLedgerSink {
    pub fn records(&self) -> &[LedgerRecord] {
        &self.records
    }

    pub fn envelopes(&self) -> Vec<LedgerEnvelope<LedgerRecord>> {
        self.records
            .iter()
            .cloned()
            .map(|record| LedgerEnvelope {
                kind: "live_engine_advisory",
                payload: record,
            })
            .collect()
    }
}

impl LedgerSink for InMemoryLedgerSink {
    fn record_order_intent(&mut self, intent: &OrderIntentRow) {
        self.records.push(LedgerRecord::OrderIntent(intent.clone()));
    }

    fn record_execution_report(&mut self, report: &ExecutionReportRow) {
        self.records
            .push(LedgerRecord::ExecutionReport(report.clone()));
    }
}

pub struct AdvisoryPipeline<S, R, E, L> {
    strategy: S,
    risk_gate: R,
    execution_sink: E,
    ledger_sink: L,
}

impl<S, R, E, L> AdvisoryPipeline<S, R, E, L>
where
    S: StrategySignal,
    R: RiskGate,
    E: ExecutionSink,
    L: LedgerSink,
{
    pub fn new(strategy: S, risk_gate: R, execution_sink: E, ledger_sink: L) -> Self {
        Self {
            strategy,
            risk_gate,
            execution_sink,
            ledger_sink,
        }
    }

    pub fn process_market_data(&mut self, market: &NormalizedMarketData) -> LiveEngineOutput {
        let signal = self.strategy.signal(market);
        let risk_decision = self.risk_gate.evaluate(market, signal.as_ref());
        let risk_decision_row = risk_decision_row(&risk_decision);

        if risk_decision.decision != RiskDecisionStatus::Approved {
            let execution_report = execution_report_row(
                market.market_id.clone(),
                &ExecutionStatus::Rejected,
                Some("risk_rejected".to_string()),
            );
            self.ledger_sink.record_execution_report(&execution_report);
            return LiveEngineOutput {
                signal,
                risk_decision,
                risk_decision_row,
                order_intent: None,
                order_intent_row: None,
                fill: None,
                fill_row: None,
                fill_metadata: None,
                execution_report,
            };
        }

        let Some(signal) = signal else {
            let execution_report = execution_report_row(
                market.market_id.clone(),
                &ExecutionStatus::Rejected,
                Some("no_signal".to_string()),
            );
            self.ledger_sink.record_execution_report(&execution_report);
            return LiveEngineOutput {
                signal: None,
                risk_decision,
                risk_decision_row,
                order_intent: None,
                order_intent_row: None,
                fill: None,
                fill_row: None,
                fill_metadata: None,
                execution_report,
            };
        };

        let order_intent = build_order_intent(
            signal.market_id.clone(),
            signal.side.clone(),
            signal.observed_price,
        );
        let order_intent_row = order_intent_row(&order_intent);
        self.ledger_sink.record_order_intent(&order_intent_row);
        let execution_report = self.execution_sink.execute(market, &order_intent);
        self.ledger_sink.record_execution_report(&execution_report);

        LiveEngineOutput {
            signal: Some(signal),
            risk_decision,
            risk_decision_row,
            order_intent: Some(order_intent),
            order_intent_row: Some(order_intent_row),
            fill: None,
            fill_row: None,
            fill_metadata: Some(DryRunAdvisory::fill_metadata()),
            execution_report,
        }
    }

    pub fn process_source<D>(&mut self, source: &mut D) -> Vec<LiveEngineOutput>
    where
        D: MarketDataSource,
    {
        let mut outputs = Vec::new();
        while let Some(market) = source.next_market_data() {
            outputs.push(self.process_market_data(&market));
        }
        outputs
    }

    pub fn ledger(&self) -> &L {
        &self.ledger_sink
    }
}

pub type DefaultAdvisoryPipeline =
    AdvisoryPipeline<PmSignalStrategy, SpreadRiskGate, DryRunAdvisory, NoopLedgerSink>;

pub fn engine_name() -> &'static str {
    "prediction_core_live_engine"
}

pub fn process_market_event(event: &MarketEvent, config: &SignalConfig) -> LiveEngineOutput {
    let market = NormalizedMarketData::from_market_event(event);
    let mut pipeline = default_pipeline(config.clone());
    pipeline.process_market_data(&market)
}

pub fn process_market_events<'a, I>(events: I, config: &SignalConfig) -> Vec<LiveEngineOutput>
where
    I: IntoIterator<Item = &'a MarketEvent>,
{
    events
        .into_iter()
        .map(|event| process_market_event(event, config))
        .collect()
}

pub fn process_market_event_batch(
    events: &[MarketEvent],
    config: &SignalConfig,
) -> Vec<LiveEngineOutput> {
    process_market_events(events.iter(), config)
}

pub fn default_pipeline(config: SignalConfig) -> DefaultAdvisoryPipeline {
    AdvisoryPipeline::new(
        PmSignalStrategy::new(config),
        SpreadRiskGate,
        DryRunAdvisory,
        NoopLedgerSink,
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::Utc;
    use pm_types::{BookLevel, MarketEventType, OrderSide, Venue};
    use uuid::Uuid;

    fn base_event(best_bid: Option<f64>, best_ask: Option<f64>) -> MarketEvent {
        MarketEvent {
            event_id: Uuid::new_v4(),
            ts: Utc::now(),
            venue: Venue::Polymarket,
            market_id: "demo-market".to_string(),
            event_type: MarketEventType::Quote,
            best_bid,
            best_ask,
            last_trade_price: None,
            bid_size: None,
            ask_size: None,
            quote_age_ms: Some(5),
        }
    }

    fn signal_config() -> SignalConfig {
        SignalConfig {
            min_edge_bps: 5.0,
            default_side: OrderSide::BuyYes,
            side_fair_value: Some(0.52),
        }
    }

    #[test]
    fn exposes_engine_name() {
        assert_eq!(engine_name(), "prediction_core_live_engine");
    }

    #[test]
    fn process_market_event_builds_order_intent_without_exchange_fill() {
        let event = base_event(Some(0.49), Some(0.50));
        let output = process_market_event(&event, &signal_config());

        assert!(output.signal.is_some());
        assert!(output.order_intent.is_some());
        assert_eq!(output.risk_decision_row.decision, "approved");
        assert_eq!(
            output.order_intent_row.as_ref().map(|row| row.side),
            Some("buy_yes")
        );
        assert!(output.fill.is_none());
        assert!(output.fill_row.is_none());
        assert_eq!(
            output
                .fill_metadata
                .as_ref()
                .map(|metadata| metadata.source),
            Some("simulation_only")
        );
        assert_eq!(
            output
                .fill_metadata
                .as_ref()
                .map(|metadata| metadata.live_submit),
            Some(false)
        );
        assert_eq!(output.execution_report.status, "rejected");
        assert_eq!(
            output.execution_report.message.as_deref(),
            Some("simulation_only_advisory_no_exchange_fill")
        );
    }

    #[test]
    fn advisory_mode_never_live_submits_or_simulates_exchange_fill() {
        let event = base_event(Some(0.49), Some(0.50));
        let output = process_market_event(&event, &signal_config());

        let metadata = output.fill_metadata.as_ref().expect("metadata exists");
        assert!(output.order_intent.is_some());
        assert!(output.fill.is_none());
        assert!(output.fill_row.is_none());
        assert_eq!(metadata.source, "simulation_only");
        assert_eq!(metadata.status, "advisory_no_exchange_fill");
        assert!(!metadata.live_submit);
        assert_eq!(output.execution_report.status, "rejected");
        assert_eq!(
            output.execution_report.message.as_deref(),
            Some("simulation_only_advisory_no_exchange_fill")
        );
    }

    #[test]
    fn process_market_event_rejects_normal_spread_without_model_side_fair_value() {
        let event = base_event(Some(0.49), Some(0.50));
        let output = process_market_event(&event, &SignalConfig::default());

        assert!(output.signal.is_none());
        assert!(output.order_intent.is_none());
        assert!(output.order_intent_row.is_none());
        assert_eq!(output.execution_report.status, "rejected");
        assert_eq!(
            output.execution_report.message.as_deref(),
            Some("no_signal")
        );
    }

    #[test]
    fn process_market_event_rejects_when_signal_is_missing() {
        let event = base_event(Some(0.4995), Some(0.5000));
        let output = process_market_event(
            &event,
            &SignalConfig {
                min_edge_bps: 20.0,
                default_side: OrderSide::BuyYes,
                side_fair_value: None,
            },
        );

        assert!(output.signal.is_none());
        assert!(output.order_intent.is_none());
        assert!(output.order_intent_row.is_none());
        assert!(output.fill_row.is_none());
        assert_eq!(output.execution_report.status, "rejected");
        assert_eq!(
            output.execution_report.message.as_deref(),
            Some("no_signal")
        );
    }

    #[test]
    fn process_market_event_rejects_when_risk_fails() {
        let event = base_event(Some(0.51), Some(0.50));
        let output = process_market_event(&event, &signal_config());

        assert_eq!(output.risk_decision.decision, RiskDecisionStatus::Rejected);
        assert_eq!(output.risk_decision_row.decision, "rejected");
        assert!(output.order_intent.is_none());
        assert!(output.fill.is_none());
        assert_eq!(output.execution_report.status, "rejected");
        assert_eq!(
            output.execution_report.message.as_deref(),
            Some("risk_rejected")
        );
    }

    #[test]
    fn composable_pipeline_records_intent_and_advisory_report_in_memory() {
        let event = base_event(Some(0.49), Some(0.50));
        let market = NormalizedMarketData::from_market_event(&event);
        let mut pipeline = AdvisoryPipeline::new(
            PmSignalStrategy::new(signal_config()),
            SpreadRiskGate,
            DryRunAdvisory,
            InMemoryLedgerSink::default(),
        );

        let output = pipeline.process_market_data(&market);

        assert!(output.order_intent.is_some());
        assert!(output.fill.is_none());
        assert!(output.fill_row.is_none());
        assert_eq!(
            output
                .fill_metadata
                .as_ref()
                .map(|metadata| metadata.live_submit),
            Some(false)
        );
        assert_eq!(pipeline.ledger().records().len(), 2);
        assert!(matches!(
            &pipeline.ledger().records()[0],
            LedgerRecord::OrderIntent(row) if row.status == "advisory_intent"
        ));
        assert!(matches!(
            &pipeline.ledger().records()[1],
            LedgerRecord::ExecutionReport(row)
                if row.status == "rejected"
                    && row.message.as_deref()
                        == Some("simulation_only_advisory_no_exchange_fill")
        ));
        assert_eq!(
            pipeline.ledger().envelopes()[0].kind,
            "live_engine_advisory"
        );
    }

    #[test]
    fn process_source_handles_multiple_market_events_in_order() {
        let events = vec![
            base_event(Some(0.49), Some(0.50)),
            base_event(Some(0.4995), Some(0.5000)),
        ];
        let mut source = EventMarketDataSource::new(events.into_iter());
        let mut pipeline = default_pipeline(SignalConfig {
            min_edge_bps: 20.0,
            default_side: OrderSide::BuyYes,
            side_fair_value: Some(0.52),
        });

        let outputs = pipeline.process_source(&mut source);

        assert_eq!(outputs.len(), 2);
        assert!(outputs[0].order_intent.is_some());
        assert!(outputs[1].order_intent.is_some());
        assert!(outputs.iter().all(|output| output.fill.is_none()));
        assert!(outputs.iter().all(|output| output.fill_row.is_none()));
    }

    #[test]
    fn process_market_event_batch_keeps_simple_unit_api() {
        let events = vec![
            base_event(Some(0.49), Some(0.50)),
            base_event(Some(0.51), Some(0.50)),
        ];

        let outputs = process_market_event_batch(&events, &signal_config());

        assert_eq!(outputs.len(), 2);
        assert!(outputs[0].order_intent.is_some());
        assert_eq!(
            outputs[1].risk_decision.decision,
            RiskDecisionStatus::Rejected
        );
        assert!(outputs.iter().all(|output| output.fill.is_none()));
        assert!(outputs.iter().all(|output| output.fill_row.is_none()));
    }

    #[test]
    fn normalized_snapshot_can_enter_same_advisory_pipeline() {
        let snapshot = OrderBookSnapshot {
            bids: vec![BookLevel {
                price: 0.49,
                quantity: 100.0,
            }],
            asks: vec![BookLevel {
                price: 0.50,
                quantity: 100.0,
            }],
        };
        let market = NormalizedMarketData::from_order_book_snapshot(
            Venue::Polymarket,
            "snapshot-market",
            &snapshot,
        );
        let mut pipeline = default_pipeline(signal_config());

        let output = pipeline.process_market_data(&market);

        assert_eq!(
            output.signal.as_ref().map(|s| s.market_id.as_str()),
            Some("snapshot-market")
        );
        assert!(output.order_intent.is_some());
        assert!(output.fill.is_none());
        assert!(output.fill_row.is_none());
        assert_eq!(
            output
                .fill_metadata
                .as_ref()
                .map(|metadata| metadata.live_submit),
            Some(false)
        );
    }
}
