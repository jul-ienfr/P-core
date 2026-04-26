from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from prediction_core.analytics import chunk_text, extract_key_sentences


def test_chunk_text_prefers_sentence_boundaries_and_preserves_overlap() -> None:
    text = (
        "Inflation cooled faster than expected. "
        "The Fed signaled a possible rate cut. "
        "Energy prices stayed volatile after supply shocks."
    )

    chunks = chunk_text(text, chunk_size=72, overlap=18)

    assert chunks == [
        "Inflation cooled faster than expected.",
        "ter than expected. The Fed signaled a possible rate cut.",
        "possible rate cut. Energy prices stayed volatile after supply shocks.",
    ]


def test_extract_key_sentences_ranks_financial_sentences_but_returns_original_order() -> None:
    text = (
        "The festival opened downtown. "
        "The Federal Reserve discussed an interest rate cut after CPI cooled. "
        "Oil prices jumped as sanctions disrupted supply. "
        "A local team won its match."
    )

    key_sentences = extract_key_sentences(text, max_sentences=2)

    assert key_sentences == [
        "The Federal Reserve discussed an interest rate cut after CPI cooled.",
        "Oil prices jumped as sanctions disrupted supply.",
    ]


def test_text_helpers_handle_blank_and_small_limits() -> None:
    assert chunk_text("   ") == []
    assert chunk_text("Short text", chunk_size=100) == ["Short text"]
    assert extract_key_sentences("   ") == []
    assert extract_key_sentences("No market keywords here.", max_sentences=0) == []
