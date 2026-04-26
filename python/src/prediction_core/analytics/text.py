from __future__ import annotations

import re

FINANCIAL_KEYWORDS: tuple[str, ...] = (
    "fed",
    "federal reserve",
    "rate",
    "interest rate",
    "rate hike",
    "rate cut",
    "monetary policy",
    "quantitative easing",
    "tightening",
    "dovish",
    "hawkish",
    "central bank",
    "ecb",
    "boj",
    "inflation",
    "cpi",
    "ppi",
    "gdp",
    "unemployment",
    "nonfarm",
    "payroll",
    "jobs",
    "housing",
    "retail sales",
    "consumer confidence",
    "pmi",
    "earnings",
    "revenue",
    "profit",
    "loss",
    "guidance",
    "forecast",
    "beat",
    "miss",
    "eps",
    "dividend",
    "buyback",
    "ipo",
    "merger",
    "acquisition",
    "bankruptcy",
    "restructuring",
    "trade",
    "tariff",
    "sanctions",
    "embargo",
    "export",
    "import",
    "trade war",
    "trade deal",
    "supply chain",
    "war",
    "invasion",
    "conflict",
    "ceasefire",
    "nato",
    "military",
    "nuclear",
    "missile",
    "escalation",
    "tensions",
    "oil",
    "crude",
    "brent",
    "wti",
    "natural gas",
    "opec",
    "gold",
    "silver",
    "copper",
    "lithium",
    "commodities",
    "recession",
    "crisis",
    "default",
    "collapse",
    "crash",
    "volatility",
    "bear market",
    "correction",
    "bubble",
    "contagion",
    "systemic",
    "china",
    "russia",
    "ukraine",
    "europe",
    "asia",
    "emerging markets",
    "bitcoin",
    "crypto",
    "stablecoin",
    "stimulus",
    "spending",
    "debt ceiling",
    "deficit",
    "treasury",
    "bond",
    "yield",
    "yield curve",
)

_KEYWORD_SET = {keyword.lower() for keyword in FINANCIAL_KEYWORDS}
_KEYWORD_SINGLES = {
    word
    for keyword in FINANCIAL_KEYWORDS
    for word in keyword.lower().split()
    if len(word) >= 3
}
_SENTENCE_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"])|(?<=[.!?])$')


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    if not text or not text.strip():
        return []

    normalized = text.strip()
    if len(normalized) <= chunk_size:
        return [normalized]

    chunks: list[str] = []
    current_chunk = ""
    for sentence in _split_sentences(normalized):
        if current_chunk and len(current_chunk) + len(sentence) + 1 > chunk_size:
            chunks.append(current_chunk.strip())
            if overlap > 0 and len(current_chunk) > overlap:
                current_chunk = current_chunk[-overlap:] + " " + sentence
            else:
                current_chunk = sentence
        else:
            current_chunk = f"{current_chunk} {sentence}".strip() if current_chunk else sentence

    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    return chunks


def extract_key_sentences(text: str, max_sentences: int = 5) -> list[str]:
    if max_sentences <= 0 or not text or not text.strip():
        return []

    scored = [
        (index, _score_sentence(sentence), sentence)
        for index, sentence in enumerate(_split_sentences(text))
    ]
    scored.sort(key=lambda item: item[1], reverse=True)
    top = scored[:max_sentences]
    top.sort(key=lambda item: item[0])
    return [sentence for _, _, sentence in top]


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    return [sentence.strip() for sentence in _SENTENCE_RE.split(normalized) if sentence and sentence.strip()]


def _score_sentence(sentence: str) -> float:
    lower = sentence.lower()
    hits = 0
    for keyword in _KEYWORD_SET:
        if " " in keyword and keyword in lower:
            hits += 2

    words = re.findall(r"[a-z]+", lower)
    for word in words:
        if word in _KEYWORD_SINGLES:
            hits += 1

    word_count = max(len(words), 1)
    density = hits / word_count
    length_bonus = min(word_count / 20.0, 1.0)
    return hits + density + length_bonus
