from __future__ import annotations

from pathlib import Path
from time import perf_counter
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from prediction_core.execution.book import estimate_fill_from_book  # noqa: E402
from prediction_core.execution.models import BookLevel, OrderBookSnapshot  # noqa: E402

ITERATIONS = 10_000


def main() -> None:
    for levels in (10, 100, 1_000):
        book = make_book(levels)
        report(levels, "estimate_fill_buy", lambda: estimate_fill_from_book(book=book, side="buy", requested_quantity=levels / 2))
        report(levels, "estimate_fill_sell", lambda: estimate_fill_from_book(book=book, side="sell", requested_quantity=levels / 2))


def make_book(levels: int) -> OrderBookSnapshot:
    bids: list[BookLevel] = []
    asks: list[BookLevel] = []

    for index in range(levels):
        step = index * 0.0001
        bids.append(BookLevel(price=0.49 - step, quantity=1.0 + index % 7))
        asks.append(BookLevel(price=0.50 + step, quantity=1.0 + index % 7))

    return OrderBookSnapshot(bids=bids, asks=asks)


def report(levels: int, label: str, run_once) -> None:
    start = perf_counter()
    for _ in range(ITERATIONS):
        run_once()
    elapsed = perf_counter() - start
    print(
        f"levels={levels:4} op={label:20} iterations={ITERATIONS:6} "
        f"total_ms={elapsed * 1_000:.3f} ns_per_op={elapsed * 1_000_000_000 / ITERATIONS:.1f}"
    )


if __name__ == "__main__":
    main()
