from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_MARKET_BIAS_KEYS = {
    "yes_price",
    "no_price",
    "price",
    "prices",
    "outcomePrices",
    "outcome_prices",
    "volume",
    "liquidity",
    "best_bid",
    "best_ask",
    "spread",
    "odds",
}


def build_miro_seed_markdown(market: Mapping[str, Any], research_items: Sequence[Mapping[str, Any]] | None = None) -> str:
    """Build a fact-only Miro/MiroFish seed document from a Polymarket market.

    Market odds, prices, volume and liquidity are deliberately excluded so the
    simulation receives the question/rules/facts, not the crowd answer.
    """
    question = str(market.get("question") or market.get("title") or "Untitled market")
    lines = [
        f"# Miro seed: {question}",
        "",
        "## Prediction task",
        question,
        "",
        "Market prices are intentionally excluded to avoid biasing the simulation.",
    ]

    resolution_source = _first_text(market, ("resolutionSource", "resolution_source", "source_url"))
    description = _first_text(market, ("description", "rules"))
    if resolution_source or description:
        lines.extend(["", "## Resolution context"])
        if resolution_source:
            lines.append(f"- Resolution source: {resolution_source}")
        if description:
            lines.append(f"- Rules/context: {description}")

    filtered_market_facts = _filtered_market_facts(market)
    if filtered_market_facts:
        lines.extend(["", "## Market metadata without odds"])
        for key, value in filtered_market_facts.items():
            lines.append(f"- {key}: {value}")

    items = list(research_items or [])
    if items:
        lines.extend(["", "## External factual research"])
        for item in items:
            title = str(item.get("title") or item.get("source") or "Untitled source")
            lines.extend(["", f"### {title}"])
            for key in ("url", "source", "published", "date"):
                if item.get(key):
                    lines.append(f"- {key.title()}: {item[key]}")
            content = item.get("content") or item.get("summary") or item.get("text")
            if content:
                lines.append(str(content))

    return "\n".join(lines).strip() + "\n"


def _first_text(payload: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = payload.get(key)
        if value:
            return str(value)
    return ""


def _filtered_market_facts(market: Mapping[str, Any]) -> dict[str, Any]:
    allowed: dict[str, Any] = {}
    for key, value in market.items():
        if key in _MARKET_BIAS_KEYS:
            continue
        if key in {"question", "title", "description", "rules", "resolutionSource", "resolution_source", "source_url"}:
            continue
        if value in (None, "", [], {}):
            continue
        if isinstance(value, (str, int, float, bool)):
            allowed[key] = value
    return allowed
