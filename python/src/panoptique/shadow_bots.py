from __future__ import annotations

"""Deterministic, paper-only Panoptique shadow bot archetypes.

These bots predict likely crowd behavior, not event truth.  They never call LLMs,
never access wallets directly, and never create trading actions.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Protocol
import json
import sqlite3

from .artifacts import JsonlArtifactWriter
from .contracts import MarketSnapshot, OrderbookSnapshot, SCHEMA_VERSION, ShadowPrediction
from .repositories import PanoptiqueRepository

JsonDict = dict[str, Any]
DEFAULT_OUTPUT_DIR = Path("/home/jul/prediction_core/data/panoptique/shadow_predictions")
PREDICTION_TARGET = "crowd_behavior_not_event_truth"
CROWD_NOT_TRUTH_RATIONALE = "This is a paper-only prediction of crowd behavior, not event truth; no real order placed."


def _timestamp_id(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _round(value: float | None, places: int = 6) -> float | None:
    if value is None:
        return None
    return round(float(value), places)


def _direction_from_signed(value: float, *, epsilon: float = 1e-12) -> str:
    if value > epsilon:
        return "up"
    if value < -epsilon:
        return "down"
    return "flat"


def _price_from_context(context: "ShadowContext") -> float | None:
    if context.market_snapshot.yes_price is not None:
        return float(context.market_snapshot.yes_price)
    if context.market_snapshot.best_bid is not None and context.market_snapshot.best_ask is not None:
        return (float(context.market_snapshot.best_bid) + float(context.market_snapshot.best_ask)) / 2.0
    return None


def _base_features(bot_id: str) -> JsonDict:
    return {
        "bot_id": bot_id,
        "schema_version": SCHEMA_VERSION,
        "prediction_target": PREDICTION_TARGET,
        "paper_only": True,
        "trading_action": "none",
    }


def _prediction(
    *,
    bot_id: str,
    context: "ShadowContext",
    direction: str,
    confidence: float,
    rationale_detail: str,
    features: Mapping[str, Any] | None = None,
    horizon_seconds: int = 900,
) -> ShadowPrediction:
    observed_at = context.market_snapshot.observed_at
    merged = _base_features(bot_id)
    if features:
        merged.update(dict(features))
    return ShadowPrediction(
        prediction_id=f"shadow-{bot_id}-{context.market_snapshot.market_id}-{_timestamp_id(observed_at)}-v1",
        market_id=context.market_snapshot.market_id,
        agent_id=bot_id,
        observed_at=observed_at,
        horizon_seconds=horizon_seconds,
        predicted_crowd_direction=direction,
        confidence=max(0.0, min(1.0, float(confidence))),
        rationale=f"{CROWD_NOT_TRUTH_RATIONALE} {rationale_detail}",
        features=merged,
    )


@dataclass(frozen=True, kw_only=True)
class ShadowContext:
    market_snapshot: MarketSnapshot
    orderbook_snapshot: OrderbookSnapshot | None = None
    weather_score: float | None = None
    recent_prices: list[float] = field(default_factory=list)
    wallet_signal: Mapping[str, Any] | None = None


class ShadowBot(Protocol):
    bot_id: str

    def predict(self, context: ShadowContext) -> ShadowPrediction:
        """Return one paper-only crowd-behavior prediction."""


@dataclass(frozen=True)
class WeatherNaiveThresholdBot:
    high_threshold: float = 0.60
    low_threshold: float = 0.40
    bot_id: str = "weather_naive_threshold"

    def predict(self, context: ShadowContext) -> ShadowPrediction:
        if context.weather_score is None:
            return _prediction(
                bot_id=self.bot_id,
                context=context,
                direction="insufficient_data",
                confidence=0.0,
                rationale_detail="missing weather_score fixture input for naive threshold behavior.",
                features={"weather_score": None, "thresholds": {"low": self.low_threshold, "high": self.high_threshold}},
            )
        score = float(context.weather_score)
        if score >= self.high_threshold:
            direction = "up"
        elif score <= self.low_threshold:
            direction = "down"
        else:
            direction = "flat"
        return _prediction(
            bot_id=self.bot_id,
            context=context,
            direction=direction,
            confidence=score if direction == "up" else (1.0 - score if direction == "down" else 0.5),
            rationale_detail="naive retail weather scorer expects crowd movement when weather probability crosses common thresholds.",
            features={"weather_score": _round(score), "thresholds": {"low": self.low_threshold, "high": self.high_threshold}},
        )


@dataclass(frozen=True)
class RoundNumberPriceBot:
    magic_levels: tuple[float, ...] = (0.50, 0.60, 0.65, 0.70, 0.75, 0.80)
    tolerance: float = 0.005
    bot_id: str = "round_number_price_bot"

    def predict(self, context: ShadowContext) -> ShadowPrediction:
        price = _price_from_context(context)
        if price is None:
            return _prediction(
                bot_id=self.bot_id,
                context=context,
                direction="insufficient_data",
                confidence=0.0,
                rationale_detail="missing price input for round-number crowd behavior heuristic.",
                features={"price": None, "magic_levels": list(self.magic_levels), "matched_level": None},
            )
        matched = min(self.magic_levels, key=lambda level: abs(price - level))
        is_match = abs(price - matched) <= self.tolerance
        direction = "up" if is_match else "flat"
        confidence = 0.65 if is_match else 0.25
        return _prediction(
            bot_id=self.bot_id,
            context=context,
            direction=direction,
            confidence=confidence,
            rationale_detail="retail bots often anchor on salient round probability levels and may crowd-follow near them.",
            features={"price": _round(price), "magic_levels": list(self.magic_levels), "matched_level": matched if is_match else None, "tolerance": self.tolerance},
        )


@dataclass(frozen=True)
class EdgePctBot:
    edge_threshold: float = 0.08
    bot_id: str = "edge_8pct_bot"

    def predict(self, context: ShadowContext) -> ShadowPrediction:
        price = _price_from_context(context)
        if price is None or context.weather_score is None:
            return _prediction(
                bot_id=self.bot_id,
                context=context,
                direction="insufficient_data",
                confidence=0.0,
                rationale_detail="missing price or model probability for common edge-threshold behavior.",
                features={"price": _round(price), "weather_score": _round(context.weather_score), "edge": None, "edge_threshold": self.edge_threshold},
            )
        edge = float(context.weather_score) - float(price)
        if abs(edge) >= self.edge_threshold:
            direction = _direction_from_signed(edge)
            confidence = 0.5 + min(abs(edge), 0.5)
        else:
            direction = "flat"
            confidence = 0.25
        return _prediction(
            bot_id=self.bot_id,
            context=context,
            direction=direction,
            confidence=confidence,
            rationale_detail="simulates common retail rule: react when perceived model edge exceeds a fixed threshold.",
            features={"price": _round(price), "weather_score": _round(context.weather_score), "edge": _round(edge, 4), "edge_threshold": self.edge_threshold},
        )


@dataclass(frozen=True)
class MomentumNaiveBot:
    min_delta: float = 0.01
    bot_id: str = "momentum_naive_bot"

    def predict(self, context: ShadowContext) -> ShadowPrediction:
        prices = [float(p) for p in context.recent_prices]
        if len(prices) < 2:
            return _prediction(
                bot_id=self.bot_id,
                context=context,
                direction="insufficient_data",
                confidence=0.0,
                rationale_detail="missing recent_prices sequence for naive momentum behavior.",
                features={"recent_prices": prices, "price_delta": None, "min_delta": self.min_delta},
            )
        delta = prices[-1] - prices[0]
        direction = _direction_from_signed(delta, epsilon=self.min_delta)
        confidence = 0.5 + min(abs(delta), 0.4) if direction in {"up", "down"} else 0.25
        return _prediction(
            bot_id=self.bot_id,
            context=context,
            direction=direction,
            confidence=confidence,
            rationale_detail="naive momentum bots infer crowd-following direction from recent price movement.",
            features={"recent_prices": [_round(p) for p in prices], "price_delta": _round(delta, 4), "min_delta": self.min_delta},
        )


@dataclass(frozen=True)
class CopyWalletPlaceholderBot:
    bot_id: str = "copy_wallet_placeholder"

    def predict(self, context: ShadowContext) -> ShadowPrediction:
        signal = context.wallet_signal
        if not signal:
            return _prediction(
                bot_id=self.bot_id,
                context=context,
                direction="insufficient_data",
                confidence=0.0,
                rationale_detail="wallet-copy archetype is contract-only until wallet signal data is available; no wallet access and no trading.",
                features={"wallet_signal_available": False, "wallet_signal": None},
            )
        direction = str(signal.get("direction") or "insufficient_data")
        confidence = float(signal.get("confidence") or 0.0)
        return _prediction(
            bot_id=self.bot_id,
            context=context,
            direction=direction,
            confidence=confidence,
            rationale_detail="wallet signal supplied by fixture/repository only; placeholder remains non-trading.",
            features={"wallet_signal_available": True, "wallet_signal": dict(signal)},
        )


def weather_naive_threshold(*, high_threshold: float = 0.60, low_threshold: float = 0.40) -> WeatherNaiveThresholdBot:
    return WeatherNaiveThresholdBot(high_threshold=high_threshold, low_threshold=low_threshold)


def round_number_price_bot(*, tolerance: float = 0.005) -> RoundNumberPriceBot:
    return RoundNumberPriceBot(tolerance=tolerance)


def edge_8pct_bot(*, edge_threshold: float = 0.08) -> EdgePctBot:
    return EdgePctBot(edge_threshold=edge_threshold)


def momentum_naive_bot(*, min_delta: float = 0.01) -> MomentumNaiveBot:
    return MomentumNaiveBot(min_delta=min_delta)


def copy_wallet_placeholder() -> CopyWalletPlaceholderBot:
    return CopyWalletPlaceholderBot()


def default_shadow_bots() -> list[ShadowBot]:
    return [weather_naive_threshold(), round_number_price_bot(), edge_8pct_bot(), momentum_naive_bot(), copy_wallet_placeholder()]


def evaluate_all_bots(context: ShadowContext, bots: list[ShadowBot] | None = None) -> list[ShadowPrediction]:
    return [bot.predict(context) for bot in (bots or default_shadow_bots())]


@dataclass(frozen=True)
class ShadowRunResult:
    command: str
    source: str
    status: str
    count: int
    artifact_path: Path
    report_path: Path
    db_status: str
    errors: list[str]


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    raise TypeError(f"Expected datetime string, got {type(value).__name__}")


def _market_from_record(record: Mapping[str, Any]) -> MarketSnapshot:
    data = dict(record)
    data["observed_at"] = _parse_datetime(data["observed_at"])
    return MarketSnapshot(**data)


def _orderbook_from_record(record: Mapping[str, Any] | None) -> OrderbookSnapshot | None:
    if record is None:
        return None
    data = dict(record)
    data["observed_at"] = _parse_datetime(data["observed_at"])
    return OrderbookSnapshot(**data)


def _context_from_fixture(payload: Mapping[str, Any]) -> ShadowContext:
    market_payload = payload.get("market_snapshot") or payload.get("market")
    if not isinstance(market_payload, Mapping):
        raise ValueError("shadow fixture requires market_snapshot object")
    orderbook_payload = payload.get("orderbook_snapshot")
    return ShadowContext(
        market_snapshot=_market_from_record(market_payload),
        orderbook_snapshot=_orderbook_from_record(orderbook_payload if isinstance(orderbook_payload, Mapping) else None),
        weather_score=payload.get("weather_score"),
        recent_prices=list(payload.get("recent_prices") or []),
        wallet_signal=payload.get("wallet_signal") if isinstance(payload.get("wallet_signal"), Mapping) else None,
    )


def _sqlite_repository(path: str | Path | None) -> PanoptiqueRepository | None:
    if path is None:
        return None
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    repo = PanoptiqueRepository(conn)
    repo.create_schema()
    return repo


def _write_predictions_artifact(*, path: Path, source: str, evaluated_at: datetime, db_status: str, predictions: list[ShadowPrediction], status: str = "ok", errors: list[str] | None = None) -> None:
    rows: list[JsonDict]
    metadata = {"source": source, "evaluated_at": evaluated_at.isoformat(), "schema_version": SCHEMA_VERSION, "db_status": db_status, "status": status}
    if predictions:
        rows = [{"metadata": metadata, "prediction": prediction.to_record()} for prediction in predictions]
    else:
        rows = [{"metadata": metadata, "prediction": None, "errors": errors or []}]
    JsonlArtifactWriter(path, source=source, artifact_type="panoptique_shadow_predictions").write_many(rows)


def _write_report(output_dir: Path, *, command: str, source: str, evaluated_at: datetime, status: str, count: int, artifact_path: Path, db_status: str, errors: list[str]) -> Path:
    report = render_shadow_report(command=command, source=source, evaluated_at=evaluated_at, status=status, count=count, artifact_path=artifact_path, db_status=db_status, errors=errors)
    path = output_dir / f"{command}-{source}-{_timestamp_id(evaluated_at)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
    return path


def _persist_predictions(repository: PanoptiqueRepository | None, predictions: list[ShadowPrediction]) -> str:
    if repository is None:
        return "skipped_unavailable"
    for prediction in predictions:
        repository.insert_shadow_prediction(prediction)
    return "inserted"


def run_shadow_evaluate_fixture(*, fixture_path: str | Path, output_dir: str | Path = DEFAULT_OUTPUT_DIR, sqlite_db: str | Path | None = None, repository: PanoptiqueRepository | None = None) -> ShadowRunResult:
    evaluated_at = datetime.now(UTC)
    output_path = Path(output_dir)
    artifact_path = output_path / f"shadow-evaluate-fixture-{_timestamp_id(evaluated_at)}.jsonl"
    errors: list[str] = []
    status = "ok"
    predictions: list[ShadowPrediction] = []
    repo = repository or _sqlite_repository(sqlite_db)
    try:
        payload = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("shadow fixture must be a JSON object")
        context = _context_from_fixture(payload)
        predictions = evaluate_all_bots(context)
    except Exception as exc:
        status = "error"
        errors.append(str(exc))
    db_status = _persist_predictions(repo, predictions) if status == "ok" else ("skipped_unavailable" if repo is None else "not_inserted_error")
    _write_predictions_artifact(path=artifact_path, source="fixture", evaluated_at=evaluated_at, db_status=db_status, predictions=predictions, status=status, errors=errors)
    report_path = _write_report(output_path, command="shadow-evaluate-fixture", source="fixture", evaluated_at=evaluated_at, status=status, count=len(predictions), artifact_path=artifact_path, db_status=db_status, errors=errors)
    return ShadowRunResult("shadow-evaluate-fixture", "fixture", status, len(predictions), artifact_path, report_path, db_status, errors)


def _latest_by_market(rows: list[JsonDict]) -> dict[str, JsonDict]:
    latest: dict[str, JsonDict] = {}
    for row in rows:
        market_id = str(row.get("market_id"))
        if market_id not in latest or str(row.get("observed_at")) > str(latest[market_id].get("observed_at")):
            latest[market_id] = row
    return latest


def run_shadow_evaluate_db(
    *,
    repository: PanoptiqueRepository | None,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    weather_scores: Mapping[str, float] | None = None,
    recent_prices: Mapping[str, list[float]] | None = None,
) -> ShadowRunResult:
    evaluated_at = datetime.now(UTC)
    output_path = Path(output_dir)
    artifact_path = output_path / f"shadow-evaluate-db-{_timestamp_id(evaluated_at)}.jsonl"
    if repository is None:
        db_status = "skipped_unavailable"
        _write_predictions_artifact(path=artifact_path, source="db", evaluated_at=evaluated_at, db_status=db_status, predictions=[], status="skipped", errors=["repository unavailable"])
        report_path = _write_report(output_path, command="shadow-evaluate-db", source="db", evaluated_at=evaluated_at, status="skipped", count=0, artifact_path=artifact_path, db_status=db_status, errors=["repository unavailable"])
        return ShadowRunResult("shadow-evaluate-db", "db", "skipped", 0, artifact_path, report_path, db_status, ["repository unavailable"])

    market_rows = repository.conn.execute("SELECT * FROM market_price_snapshots ORDER BY observed_at, snapshot_id").fetchall()
    orderbook_rows = repository.conn.execute("SELECT * FROM orderbook_snapshots ORDER BY observed_at, snapshot_id").fetchall()
    from .repositories import _decode_rows  # local import keeps public surface unchanged

    markets = _latest_by_market(_decode_rows(market_rows))
    orderbooks = _latest_by_market(_decode_rows(orderbook_rows))
    predictions: list[ShadowPrediction] = []
    weather_scores = weather_scores or {}
    recent_prices = recent_prices or {}
    for market_id, market_record in markets.items():
        context = ShadowContext(
            market_snapshot=_market_from_record(market_record),
            orderbook_snapshot=_orderbook_from_record(orderbooks.get(market_id)),
            weather_score=weather_scores.get(market_id),
            recent_prices=list(recent_prices.get(market_id) or []),
        )
        predictions.extend(evaluate_all_bots(context))
    db_status = _persist_predictions(repository, predictions)
    _write_predictions_artifact(path=artifact_path, source="db", evaluated_at=evaluated_at, db_status=db_status, predictions=predictions)
    report_path = _write_report(output_path, command="shadow-evaluate-db", source="db", evaluated_at=evaluated_at, status="ok", count=len(predictions), artifact_path=artifact_path, db_status=db_status, errors=[])
    return ShadowRunResult("shadow-evaluate-db", "db", "ok", len(predictions), artifact_path, report_path, db_status, [])


def render_shadow_report(*, command: str, source: str, evaluated_at: datetime, status: str, count: int, artifact_path: Path, db_status: str, errors: list[str]) -> str:
    lines = [
        "# Panoptique Shadow Bot Evaluation",
        "",
        "Deterministic shadow-bot report. Predictions target crowd behavior, not event truth.",
        "",
        f"- Command: `{command}`",
        f"- Source: `{source}`",
        f"- Evaluated at: `{evaluated_at.isoformat()}`",
        f"- Status: `{status}`",
        f"- Predictions: `{count}`",
        f"- Artifact: `{artifact_path}`",
        f"- DB status: `{db_status}`",
        "- Safety: No LLM calls, no wallet credentials, no trading actions. No real orders were placed.",
    ]
    if errors:
        lines.extend(["", "## Errors"])
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines) + "\n"
