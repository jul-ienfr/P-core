from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator


_WALLET_ALIASES = ("wallet", "user", "proxyWallet", "proxy_wallet")
_TITLE_ALIASES = ("title", "question", "market", "marketTitle")
_MARKET_ID_ALIASES = ("market_id", "marketId")
_CONDITION_ID_ALIASES = ("conditionId", "condition_id")
_TOKEN_ID_ALIASES = ("asset", "token_id", "tokenId")
_PRICE_ALIASES = ("price",)
_SIZE_ALIASES = ("size", "amount")
_TIMESTAMP_ALIASES = ("timestamp", "createdAt")
_TX_HASH_ALIASES = ("tx_hash", "transactionHash")
_BLOCK_NUMBER_ALIASES = ("block_number",)
_MAKER_TAKER_ALIASES = ("maker_taker",)


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    return value


def _first_present(row: dict[str, Any], aliases: tuple[str, ...]) -> Any:
    for alias in aliases:
        if alias in row:
            return _json_safe_value(row[alias])
    return None


def normalize_hf_trade_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize one SII-WANGZJ/Polymarket_data-like trade row.

    The adapter is intentionally conservative: it maps observed aliases, keeps
    source data under ``raw``, marks every result paper-only, and never invents
    identifiers that are absent from the input row.
    """

    if not isinstance(row, dict):
        raise TypeError("HF Polymarket trade row must be a dict")

    return {
        "paper_only": True,
        "live_order_allowed": False,
        "wallet": _first_present(row, _WALLET_ALIASES),
        "title": _first_present(row, _TITLE_ALIASES),
        "question": _first_present(row, _TITLE_ALIASES),
        "market_id": _first_present(row, _MARKET_ID_ALIASES),
        "condition_id": _first_present(row, _CONDITION_ID_ALIASES),
        "token_id": _first_present(row, _TOKEN_ID_ALIASES),
        "price": _first_present(row, _PRICE_ALIASES),
        "size": _first_present(row, _SIZE_ALIASES),
        "amount": _first_present(row, _SIZE_ALIASES),
        "timestamp": _first_present(row, _TIMESTAMP_ALIASES),
        "tx_hash": _first_present(row, _TX_HASH_ALIASES),
        "block_number": _first_present(row, _BLOCK_NUMBER_ALIASES),
        "maker_taker": _first_present(row, _MAKER_TAKER_ALIASES),
        "raw": _json_safe_value(dict(row)),
    }


def iter_hf_dataset_rows(path: str | Path, *, limit: int | None = None) -> Iterator[dict[str, Any]]:
    """Iterate rows from a local sample file without downloading any dataset.

    Supports JSON arrays/objects, JSONL/NDJSON, and parquet files. Parquet
    support is optional and raises a clear RuntimeError if pandas/pyarrow is not
    installed in the running environment.
    """

    source = Path(path)
    suffix = source.suffix.lower()
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative or None")
    if limit == 0:
        return

    yielded = 0
    if suffix in {".jsonl", ".ndjson"}:
        with source.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                row = json.loads(stripped)
                if not isinstance(row, dict):
                    raise ValueError(f"JSONL row {line_number} must be an object")
                yield row
                yielded += 1
                if limit is not None and yielded >= limit:
                    return
        return

    if suffix == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            candidates = payload.get("rows", payload.get("trades", payload.get("data")))
            if candidates is None:
                rows = [payload]
            else:
                rows = candidates
        else:
            rows = payload
        if not isinstance(rows, list):
            raise ValueError("JSON input must be an object, an array, or contain rows/trades/data array")
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValueError(f"JSON row {index} must be an object")
            yield row
            yielded += 1
            if limit is not None and yielded >= limit:
                return
        return

    if suffix == ".parquet":
        try:
            import pandas as pd  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover - depends on optional env
            raise RuntimeError("Reading parquet samples requires optional dependencies: pandas and pyarrow") from exc
        try:
            frame = pd.read_parquet(source)
        except ImportError as exc:  # pragma: no cover - depends on optional env
            raise RuntimeError("Reading parquet samples requires optional dependencies: pandas and pyarrow") from exc
        if limit is not None:
            frame = frame.head(limit)
        for row in frame.to_dict(orient="records"):
            yield dict(row)
        return

    raise ValueError(f"unsupported HF Polymarket sample file extension: {source.suffix}")


def load_wallet_filter(wallets: list[str] | None = None, wallets_json: str | Path | None = None) -> set[str]:
    selected: set[str] = {wallet.lower() for wallet in (wallets or []) if wallet}
    if wallets_json:
        payload = json.loads(Path(wallets_json).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            values = payload.get("wallets", payload.get("accounts", []))
        else:
            values = payload
        if not isinstance(values, list):
            raise ValueError("wallets JSON must be an array or an object with wallets/accounts array")
        selected.update(str(wallet).lower() for wallet in values if wallet)
    return selected


def write_hf_account_trades_sample(
    input_path: str | Path,
    output_json: str | Path,
    *,
    wallets: list[str] | None = None,
    wallets_json: str | Path | None = None,
    limit: int | None = 1000,
) -> dict[str, Any]:
    wallet_filter = load_wallet_filter(wallets, wallets_json)
    trades: list[dict[str, Any]] = []
    rows_scanned = 0

    for row in iter_hf_dataset_rows(input_path, limit=limit):
        rows_scanned += 1
        normalized = normalize_hf_trade_row(row)
        wallet = normalized.get("wallet")
        if wallet_filter and (wallet is None or str(wallet).lower() not in wallet_filter):
            continue
        trades.append(normalized)

    output_path = Path(output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "paper_only": True,
        "live_order_allowed": False,
        "source": "SII-WANGZJ/Polymarket_data",
        "input": str(input_path),
        "wallets": sorted(wallet_filter),
        "rows_scanned": rows_scanned,
        "matched_trades": len(trades),
        "trades": trades,
    }
    output_path.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "paper_only": True,
        "live_order_allowed": False,
        "rows_scanned": rows_scanned,
        "matched_trades": len(trades),
        "output_json": str(output_path),
    }
