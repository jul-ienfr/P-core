from weather_pm.paper_report import build_paper_portfolio_report


def test_build_report_separates_realized_exit_official_and_open_mtm():
    positions = [
        {
            "question": "won official",
            "action": "SETTLED_WON",
            "settlement_status": "SETTLED_WON",
            "filled_usdc": 10.0,
            "shares": 14.0,
            "paper_settlement_value_usdc": 14.0,
            "paper_realized_pnl_usdc": 4.0,
        },
        {
            "question": "open",
            "action": "HOLD_CAPPED",
            "settlement_status": "UNSETTLED",
            "filled_usdc": 5.0,
            "shares": 9.0,
            "paper_mtm_bid_usdc": 1.25,
        },
    ]
    closed_positions = [
        {
            "question": "exited",
            "action": "EXIT_PAPER",
            "filled_usdc": 2.0,
            "shares": 3.0,
            "paper_realized_pnl_usdc": -0.2,
            "official_settlement_status": "SETTLED_WON",
            "official_hold_to_settlement_pnl_usdc": 1.0,
        }
    ]

    report = build_paper_portfolio_report(positions, closed_positions)

    assert report["counts"] == {"total": 3, "open": 1, "settled": 1, "exit_paper": 1}
    assert report["spend_usdc"]["total_displayed"] == 17.0
    assert report["pnl_usdc"]["settled_realized"] == 4.0
    assert report["pnl_usdc"]["exit_realized"] == -0.2
    assert report["pnl_usdc"]["realized_total"] == 3.8
    assert report["pnl_usdc"]["open_mtm_bid"] == 1.25
    assert report["pnl_usdc"]["realized_plus_open_mtm"] == 5.05
    assert report["pnl_usdc"]["if_open_loses"] == -1.2
    assert report["pnl_usdc"]["if_open_wins_full_payout"] == 7.8
    assert report["pnl_usdc"]["official_hold_to_settlement_for_exits"] == 1.0
