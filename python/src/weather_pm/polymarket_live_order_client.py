from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PolymarketLiveOrderClientConfig:
    mode: str = "shadow"
    host: str = "https://clob.polymarket.com"
    chain_id: int = 137
    private_key: str | None = None
    funder: str | None = None
    signature_type: int = 1

    @property
    def configured(self) -> bool:
        return bool(self.private_key and self.funder and self.host)

    def redacted(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "configured": self.configured,
            "host": self.host,
            "chain_id": self.chain_id,
            "funder": "[REDACTED]" if self.funder else None,
            "private_key": "[REDACTED]" if self.private_key else None,
            "signature_type": self.signature_type,
        }


def build_order_client_config_from_env() -> PolymarketLiveOrderClientConfig:
    return PolymarketLiveOrderClientConfig(
        mode=_env_mode("WEATHER_LIVE_CANARY_MODE", "shadow"),
        host=os.environ.get("POLYMARKET_HOST", "https://clob.polymarket.com"),
        chain_id=_env_int("POLYMARKET_CHAIN_ID", 137),
        private_key=os.environ.get("POLYMARKET_PRIVATE_KEY"),
        funder=os.environ.get("POLYMARKET_FUNDER") or os.environ.get("POLYMARKET_PROXY_WALLET"),
        signature_type=_env_int("POLYMARKET_SIGNATURE_TYPE", 1),
    )


class PolymarketLiveOrderClient:
    """Thin py-clob-client adapter, intentionally constructed only in live mode.

    The import is lazy so the repo stays testable without live trading deps installed.
    """

    def __init__(self, config: PolymarketLiveOrderClientConfig) -> None:
        if config.mode != "live":
            raise ValueError("PolymarketLiveOrderClient requires WEATHER_LIVE_CANARY_MODE=live")
        if not config.configured:
            raise ValueError("Polymarket live order client is not configured")
        self.config = config
        try:
            from py_clob_client.client import ClobClient  # type: ignore
            from py_clob_client.clob_types import OrderArgs  # type: ignore
            from py_clob_client.order_builder.constants import BUY, SELL  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on live deployment env
            raise RuntimeError("py-clob-client is required only for live order submission") from exc
        self._OrderArgs = OrderArgs
        self._BUY = BUY
        self._SELL = SELL
        self._client = ClobClient(
            config.host,
            key=config.private_key,
            chain_id=config.chain_id,
            signature_type=config.signature_type,
            funder=config.funder,
        )
        self._client.set_api_creds(self._client.create_or_derive_api_creds())

    def submit_limit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        side = self._BUY if str(payload.get("side", "YES")).upper() in {"YES", "BUY"} else self._SELL
        notional = float(payload["notional_usdc"])
        price = float(payload["limit_price"])
        size = round(notional / price, 6)
        order_args = self._OrderArgs(
            token_id=str(payload["token_id"]),
            price=price,
            size=size,
            side=side,
        )
        signed_order = self._client.create_order(order_args)
        response = self._client.post_order(signed_order, orderType=str(payload.get("time_in_force") or "IOC"))
        if isinstance(response, dict):
            return response
        return {"status": "submitted", "response": response, "client_order_id": payload.get("client_order_id")}


def _env_mode(key: str, default: str) -> str:
    value = os.environ.get(key, default).strip().lower()
    return value if value in {"shadow", "live"} else default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default
