from prediction_core.polymarket_stack import recommended_polymarket_stack, stack_decision_table


def test_recommended_stack_names_rust_clob_websocket_as_fastest_hot_path():
    stack = recommended_polymarket_stack()

    assert stack["fastest_hot_path"]["technology"] == "Polymarket/rs-clob-client"
    assert stack["fastest_hot_path"]["language"] == "Rust"
    assert stack["fastest_hot_path"]["transport"] == "CLOB WebSocket"
    assert stack["fastest_hot_path"]["role"] == "long-running daemon for live orderbook updates"


def test_recommended_stack_places_official_cli_as_script_surface_not_hot_loop():
    stack = recommended_polymarket_stack()

    cli = stack["official_cli"]
    assert cli["repository"] == "Polymarket/polymarket-cli"
    assert cli["language"] == "Rust"
    assert cli["sdk"] == "polymarket-client-sdk"
    assert cli["uses"] == ["Gamma API", "CLOB API", "Data API", "Bridge API", "CTF API"]
    assert cli["best_for"] == "terminal automation and JSON scripting"
    assert cli["not_best_for"] == "tight low-latency trading loops because each command starts a process"


def test_stack_decision_table_keeps_gamma_and_data_out_of_hot_execution_loop():
    rows = stack_decision_table()

    by_layer = {row["layer"]: row for row in rows}
    assert by_layer["discovery"]["api"] == "Gamma API"
    assert by_layer["live_market_data"]["api"] == "CLOB WebSocket"
    assert by_layer["order_execution"]["api"] == "CLOB REST"
    assert by_layer["analytics"]["api"] == "Data API"
    assert by_layer["analytics"]["hot_path"] is False
    assert by_layer["discovery"]["hot_path"] is False
    assert by_layer["live_market_data"]["hot_path"] is True
    assert by_layer["order_execution"]["hot_path"] is True
