from __future__ import annotations

from weather_pm.wallet_sizing_priors import build_wallet_sizing_priors


def test_build_wallet_sizing_priors_summarizes_styles() -> None:
    payload = {
        "accounts": [
            {
                "handle": "Railbird",
                "style": "breadth/grid small-ticket surface trader",
                "recent_trade_avg_usdc": 21.43,
                "recent_trade_max_usdc": 29.98,
            },
            {
                "handle": "ColdMath",
                "style": "sparse/large-ticket conviction trader",
                "recent_trade_avg_usdc": 194.87,
                "recent_trade_max_usdc": 4149.66,
            },
            {
                "handle": "0xhana",
                "style": "breadth/grid small-ticket surface trader",
                "recent_trade_avg_usdc": 23.69,
                "recent_trade_max_usdc": 75.0,
            },
            {
                "handle": "WxOnly",
                "style": "selective weather trader",
                "recent_trade_avg_usdc": 41.0,
                "recent_trade_max_usdc": 88.0,
            },
            {
                "handle": "Mystery",
                "style": "unclassified market maker",
                "recent_trade_avg_usdc": 10.0,
                "recent_trade_max_usdc": 18.0,
            },
        ]
    }

    priors = build_wallet_sizing_priors(payload)

    grid = priors["styles"]["breadth/grid small-ticket surface trader"]
    assert grid["accounts"] == 2
    assert grid["median_recent_trade_avg_usdc"] == 22.56
    assert grid["median_recent_trade_max_usdc"] == 52.49
    assert grid["recommended_copy_mode"] == "imitate_small_grid_notional"

    large = priors["styles"]["sparse/large-ticket conviction trader"]
    assert large["accounts"] == 1
    assert large["median_recent_trade_avg_usdc"] == 194.87
    assert large["median_recent_trade_max_usdc"] == 4149.66
    assert large["recommended_copy_mode"] == "confidence_only_cap_size"

    selective = priors["styles"]["selective weather trader"]
    assert selective["recommended_copy_mode"] == "confidence_only_no_size_bump"

    unknown = priors["styles"]["unclassified market maker"]
    assert unknown["recommended_copy_mode"] == "model_execution_only"

    assert priors["operator_default_style"] == "breadth/grid small-ticket surface trader"
    assert priors["copy_warning"] == "wallet priors adjust size/confidence but do not authorize blind copy-trading"


def test_build_wallet_sizing_priors_handles_empty_accounts() -> None:
    assert build_wallet_sizing_priors({"accounts": []}) == {
        "styles": {},
        "operator_default_style": "breadth/grid small-ticket surface trader",
        "copy_warning": "wallet priors adjust size/confidence but do not authorize blind copy-trading",
    }
