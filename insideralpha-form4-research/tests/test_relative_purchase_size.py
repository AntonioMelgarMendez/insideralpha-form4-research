from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from analysis.relative_purchase_size import analyze  # noqa: E402


def row(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Ticker": "TEST",
        "Executive": "Research Owner",
        "Date": "2020-01-02",
        "Type": "P",
        "Shares": 10.0,
        "calculated_total_value": 1000.0,
        "reporting_owner_cik": "123",
        "transaction_table": "non_derivative",
        "security_title": "Common Stock",
        "shares_owned_after": 1000.0,
        "ownership_nature": "D",
        "is_current": True,
        "insider_return_30d": 1.0,
        "insider_return_90d": 2.0,
        "insider_return_180d": 3.0,
    }
    return {**base, **overrides}


class RelativePurchaseSizeTest(unittest.TestCase):
    def test_price_tranches_collapse_to_one_event(self) -> None:
        frame = pd.DataFrame(
            [
                row(Shares=4.0, calculated_total_value=400.0),
                row(Shares=6.0, calculated_total_value=600.0),
            ]
        )

        result = analyze(frame)

        self.assertEqual(len(result.eligible_events), 1)
        event = result.eligible_events.iloc[0]
        self.assertEqual(event["purchased_shares"], 10.0)
        self.assertEqual(event["disclosed_value"], 1000.0)
        self.assertAlmostEqual(event["purchase_fraction"], 0.01)
        self.assertEqual(str(event["bucket"]), "1% to under 5%")

    def test_ineligible_and_above_100_percent_rows_are_excluded(self) -> None:
        frame = pd.DataFrame(
            [
                row(Ticker="SALE", Type="S"),
                row(Ticker="INDIRECT", ownership_nature="I"),
                row(Ticker="DERIVATIVE", transaction_table="derivative"),
                row(Ticker="STALE", is_current=False),
                row(Ticker="TOO_LARGE", Shares=101.0, shares_owned_after=100.0),
                row(Ticker="VALID", Shares=50.0, shares_owned_after=100.0),
            ]
        )

        result = analyze(frame)

        self.assertEqual(result.eligible_events["Ticker"].tolist(), ["VALID"])
        self.assertEqual(str(result.eligible_events.iloc[0]["bucket"]), "50% to 100%")

    def test_bucket_summary_reports_counts_and_positive_rate(self) -> None:
        frame = pd.DataFrame(
            [
                row(Ticker="ONE", Shares=1.0, shares_owned_after=1000.0, insider_return_180d=4.0),
                row(Ticker="TWO", Shares=2.0, shares_owned_after=1000.0, insider_return_180d=-2.0),
            ]
        )

        result = analyze(frame)
        under_one = result.bucket_summary.set_index("bucket").loc["Under 1%"]

        self.assertEqual(under_one["event_count"], 2)
        self.assertEqual(under_one["issuer_count"], 2)
        self.assertEqual(under_one["positive_return_180d_pct"], 50.0)


if __name__ == "__main__":
    unittest.main()

