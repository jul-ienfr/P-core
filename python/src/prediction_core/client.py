from __future__ import annotations

import json
from typing import Any
from urllib import error, request


class PredictionCoreClientError(RuntimeError):
    def __init__(self, *, status_code: int, payload: dict[str, Any] | None = None, message: str | None = None) -> None:
        self.status_code = status_code
        self.payload = payload
        detail = message or _message_from_payload(payload) or f"prediction_core request failed with status {status_code}"
        super().__init__(detail)


class PredictionCoreClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8080", *, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/health")

    def parse_market(self, *, question: str) -> dict[str, Any]:
        return self._request_json("POST", "/weather/parse-market", {"question": question})

    def fetch_markets(self, *, source: str = "fixture", limit: int = 100) -> list[dict[str, Any]]:
        payload = self._request_json("POST", "/weather/fetch-markets", {"source": source, "limit": limit})
        markets = payload.get("markets")
        if not isinstance(markets, list):
            raise PredictionCoreClientError(status_code=500, message="prediction_core returned an invalid markets payload")
        return markets

    def score_market(
        self,
        *,
        question: str | None = None,
        yes_price: float | None = None,
        market_id: str | None = None,
        source: str | None = None,
        **payload: Any,
    ) -> dict[str, Any]:
        body = dict(payload)
        if question is not None:
            body["question"] = question
        if yes_price is not None:
            body["yes_price"] = yes_price
        if market_id is not None:
            body["market_id"] = market_id
        if source is not None:
            body["source"] = source
        return self._request_json("POST", "/weather/score-market", body)

    def paper_cycle(
        self,
        *,
        run_id: str,
        market_id: str,
        **payload: Any,
    ) -> dict[str, Any]:
        body = {"run_id": run_id, "market_id": market_id, **payload}
        return self._request_json("POST", "/weather/paper-cycle", body)

    def external_seed_document(
        self,
        *,
        question: str,
        seed_document_paths: list[str],
        **payload: Any,
    ) -> dict[str, Any]:
        body = {"question": question, "seed_document_paths": seed_document_paths, **payload}
        return self._request_json("POST", "/weather/external-seed-document", body)

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        http_request = request.Request(f"{self.base_url}{path}", data=data, method=method)
        if data is not None:
            http_request.add_header("Content-Type", "application/json")

        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                return _decode_json_response(response.read())
        except error.HTTPError as exc:
            payload = _decode_json_response(exc.read())
            raise PredictionCoreClientError(status_code=exc.code, payload=payload) from exc


def _decode_json_response(raw_body: bytes) -> dict[str, Any]:
    decoded = json.loads(raw_body.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise PredictionCoreClientError(status_code=500, message="prediction_core returned a non-object JSON payload")
    return decoded


def _message_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    message = payload.get("message")
    return message if isinstance(message, str) else None