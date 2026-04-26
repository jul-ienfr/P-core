from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from prediction_core.client import PredictionCoreClient
from prediction_core.server import build_external_seed_document, build_server


def _start_server() -> tuple[object, threading.Thread, int]:
    server = build_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, server.server_address[1]


def _json_request(url: str, *, method: str = "GET", payload: dict | None = None) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_build_external_seed_document_reads_local_markdown_without_llm(tmp_path) -> None:
    seed_path = tmp_path / "denver_seed.md"
    seed_path.write_text(
        "# Denver KDEN seed\n\nResolution source: NOAA daily climate report for station KDEN.\n",
        encoding="utf-8",
    )

    result = build_external_seed_document(
        {
            "question": "Denver high temp?",
            "seed_document_paths": [str(seed_path)],
            "paper_only": True,
            "live_order_allowed": False,
        }
    )

    assert result["model"] == "external_seed"
    assert result["seed_document_source"] == "seed_document_paths"
    assert result["seed_document_paths"] == [str(seed_path)]
    assert "KDEN" in result["seed_document"]
    assert "KDEN" in result["simulation_requirement"]
    assert result["paper_only"] is True
    assert result["live_order_allowed"] is False


def test_external_seed_endpoint_returns_seed_document_for_ontology_handoff(tmp_path) -> None:
    seed_path = tmp_path / "kden_seed.md"
    seed_path.write_text(
        "# Denver KDEN ontology seed\n\nStation: KDEN\nMetric: daily high temperature\n",
        encoding="utf-8",
    )
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/external-seed-document",
            method="POST",
            payload={
                "question": "Build a paper-only KDEN ontology seed",
                "seed_document_paths": [str(seed_path)],
                "paper_only": True,
                "live_order_allowed": False,
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 200
    assert payload["model"] == "external_seed"
    assert payload["title"] == "Build a paper-only KDEN ontology seed"
    assert payload["seed_document_source"] == "seed_document_paths"
    assert payload["paper_only"] is True
    assert payload["live_order_allowed"] is False
    assert "KDEN" in payload["seed_document"]


def test_external_seed_endpoint_rejects_missing_path(tmp_path) -> None:
    server, thread, port = _start_server()
    try:
        status, payload = _json_request(
            f"http://127.0.0.1:{port}/weather/external-seed-document",
            method="POST",
            payload={"question": "Denver?", "seed_document_paths": [str(tmp_path / "missing.md")]},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert status == 400
    assert payload["status"] == "error"
    assert "seed_document_paths entry not found" in payload["message"]


def test_client_external_seed_document_returns_handoff_payload(tmp_path) -> None:
    seed_path = tmp_path / "client_seed.md"
    seed_path.write_text("# Client seed\n\nStation KDEN\n", encoding="utf-8")
    server, thread, port = _start_server()
    client = PredictionCoreClient(f"http://127.0.0.1:{port}")
    try:
        payload = client.external_seed_document(
            question="Client KDEN handoff",
            seed_document_paths=[str(seed_path)],
            paper_only=True,
            live_order_allowed=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert payload["model"] == "external_seed"
    assert payload["seed_document_paths"] == [str(seed_path)]
    assert "KDEN" in payload["seed_document"]
