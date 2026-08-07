"""Analyze Form 4 purchases relative to reported post-transaction holdings."""

from __future__ import annotations

import argparse
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {
    "Ticker",
    "Executive",
    "Date",
    "Type",
    "Shares",
    "calculated_total_value",
    "reporting_owner_cik",
    "transaction_table",
    "security_title",
    "shares_owned_after",
    "ownership_nature",
    "is_current",
    "insider_return_30d",
    "insider_return_90d",
    "insider_return_180d",
}

BUCKET_ORDER = [
    "Under 1%",
    "1% to under 5%",
    "5% to under 20%",
    "20% to under 50%",
    "50% to 100%",
]


@dataclass(frozen=True)
class AnalysisResult:
    source_rows: int
    eligible_events: pd.DataFrame
    bucket_summary: pd.DataFrame
    diagnostics: dict[str, Any]


def load_dataset(path: str | Path) -> pd.DataFrame:
    """Load a release CSV or a ZIP archive containing exactly one CSV file."""
    dataset_path = Path(path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    if dataset_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(dataset_path) as archive:
            csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if len(csv_names) != 1:
                raise ValueError("Expected exactly one CSV file in the ZIP archive")
            with archive.open(csv_names[0]) as source:
                return pd.read_csv(source, low_memory=False)

    return pd.read_csv(dataset_path, low_memory=False)


def _as_boolean(series: pd.Series) -> pd.Series:
    return series.astype("string").str.lower().isin({"true", "1", "yes"})


def _owner_key(frame: pd.DataFrame) -> pd.Series:
    cik = frame["reporting_owner_cik"].astype("string")
    name = frame["Executive"].astype("string").str.strip()
    return cik.where(cik.notna() & cik.ne(""), "name:" + name)


def construct_events(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the published eligibility rules and collapse price tranches."""
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"Dataset is missing required columns: {', '.join(missing)}")

    work = frame.copy()
    work["Date"] = pd.to_datetime(work["Date"], errors="coerce")
    numeric_columns = [
        "Shares",
        "shares_owned_after",
        "calculated_total_value",
        "insider_return_30d",
        "insider_return_90d",
        "insider_return_180d",
    ]
    for column in numeric_columns:
        work[column] = pd.to_numeric(work[column], errors="coerce")

    work["owner_key"] = _owner_key(work)
    work["security_key"] = work["security_title"].fillna("<unknown>").astype(str)

    eligible = work.loc[
        work["Type"].eq("P")
        & work["Date"].ge(pd.Timestamp("2007-01-01"))
        & _as_boolean(work["is_current"])
        & work["transaction_table"].eq("non_derivative")
        & work["ownership_nature"].eq("D")
        & work["Shares"].gt(0)
        & work["shares_owned_after"].gt(0)
        & work[
            ["insider_return_30d", "insider_return_90d", "insider_return_180d"]
        ].notna().all(axis=1)
    ].copy()

    event_keys = [
        "Ticker",
        "owner_key",
        "Date",
        "security_key",
        "ownership_nature",
    ]
    events = (
        eligible.groupby(event_keys, dropna=False, as_index=False)
        .agg(
            purchased_shares=("Shares", "sum"),
            disclosed_value=("calculated_total_value", "sum"),
            shares_owned_after=("shares_owned_after", "max"),
            return_30d=("insider_return_30d", "median"),
            return_90d=("insider_return_90d", "median"),
            return_180d=("insider_return_180d", "median"),
            source_rows=("Type", "size"),
        )
    )
    events["purchase_fraction"] = (
        events["purchased_shares"] / events["shares_owned_after"]
    )
    events = events.loc[
        events["purchase_fraction"].gt(0) & events["purchase_fraction"].le(1)
    ].copy()

    conditions = [
        events["purchase_fraction"].lt(0.01),
        events["purchase_fraction"].lt(0.05),
        events["purchase_fraction"].lt(0.20),
        events["purchase_fraction"].lt(0.50),
    ]
    events["bucket"] = pd.Categorical(
        np.select(conditions, BUCKET_ORDER[:-1], default=BUCKET_ORDER[-1]),
        categories=BUCKET_ORDER,
        ordered=True,
    )
    return events.sort_values(event_keys).reset_index(drop=True)


def summarize_buckets(events: pd.DataFrame) -> pd.DataFrame:
    """Build the report's five predefined holdings-relative cohorts."""
    if events.empty:
        return pd.DataFrame(
            columns=[
                "bucket",
                "event_count",
                "issuer_count",
                "median_fraction_pct",
                "median_disclosed_value_usd",
                "median_return_30d_pct",
                "median_return_90d_pct",
                "median_return_180d_pct",
                "positive_return_180d_pct",
            ]
        )

    summary = (
        events.groupby("bucket", observed=False)
        .agg(
            event_count=("Ticker", "size"),
            issuer_count=("Ticker", "nunique"),
            median_fraction_pct=("purchase_fraction", lambda values: values.median() * 100),
            median_disclosed_value_usd=("disclosed_value", "median"),
            median_return_30d_pct=("return_30d", "median"),
            median_return_90d_pct=("return_90d", "median"),
            median_return_180d_pct=("return_180d", "median"),
            positive_return_180d_pct=("return_180d", lambda values: values.gt(0).mean() * 100),
        )
        .reset_index()
    )
    return summary


def _bootstrap_median_interval(
    values: pd.Series, *, iterations: int = 10_000, seed: int = 20260804
) -> tuple[float | None, float | None]:
    clean = values.dropna().to_numpy(dtype=float)
    if clean.size == 0:
        return None, None
    rng = np.random.default_rng(seed)
    medians = np.empty(iterations)
    for index in range(iterations):
        medians[index] = np.median(rng.choice(clean, size=clean.size, replace=True))
    lower, upper = np.percentile(medians, [2.5, 97.5])
    return float(lower), float(upper)


def build_diagnostics(events: pd.DataFrame) -> dict[str, Any]:
    """Calculate rank, broad-cohort and matched-issuer diagnostics."""
    if events.empty:
        return {
            "event_count": 0,
            "issuer_count": 0,
            "owner_count": 0,
            "spearman_fraction_vs_return_180d": None,
            "matched_issuers": 0,
        }

    low = events.loc[events["purchase_fraction"].lt(0.05)].copy()
    high = events.loc[events["purchase_fraction"].ge(0.20)].copy()
    broad = pd.concat(
        [low.assign(cohort="low"), high.assign(cohort="high")],
        ignore_index=True,
    )

    ticker_cohorts = (
        broad.groupby(["Ticker", "cohort"])["return_180d"]
        .agg(["size", "median"])
        .reset_index()
    )
    ticker_counts = (
        ticker_cohorts.pivot(index="Ticker", columns="cohort", values="size")
        .reindex(columns=["low", "high"], fill_value=0)
        .fillna(0)
    )
    eligible_tickers = ticker_counts.loc[
        ticker_counts["low"].ge(3) & ticker_counts["high"].ge(3)
    ].index
    matched = (
        ticker_cohorts.loc[ticker_cohorts["Ticker"].isin(eligible_tickers)]
        .pivot(index="Ticker", columns="cohort", values="median")
        .dropna()
    )
    matched_spread = matched["high"] - matched["low"] if not matched.empty else pd.Series(dtype=float)
    interval = _bootstrap_median_interval(matched_spread)

    ranked_fraction = events["purchase_fraction"].rank(method="average")
    ranked_return = events["return_180d"].rank(method="average")
    spearman = None
    if (
        len(events) >= 2
        and ranked_fraction.nunique() > 1
        and ranked_return.nunique() > 1
    ):
        spearman = float(ranked_fraction.corr(ranked_return))

    return {
        "event_count": int(len(events)),
        "issuer_count": int(events["Ticker"].nunique()),
        "owner_count": int(events["owner_key"].nunique()),
        "spearman_fraction_vs_return_180d": spearman,
        "low_event_count": int(len(low)),
        "low_median_fraction_pct": float(low["purchase_fraction"].median() * 100) if len(low) else None,
        "low_median_return_180d_pct": float(low["return_180d"].median()) if len(low) else None,
        "high_event_count": int(len(high)),
        "high_median_fraction_pct": float(high["purchase_fraction"].median() * 100) if len(high) else None,
        "high_median_return_180d_pct": float(high["return_180d"].median()) if len(high) else None,
        "matched_issuers": int(len(matched_spread)),
        "matched_issuer_median_spread_pct_points": float(matched_spread.median()) if len(matched_spread) else None,
        "matched_issuers_high_wins_pct": float(matched_spread.gt(0).mean() * 100) if len(matched_spread) else None,
        "matched_issuer_bootstrap_95_pct_points": list(interval),
    }


def analyze(frame: pd.DataFrame) -> AnalysisResult:
    events = construct_events(frame)
    return AnalysisResult(
        source_rows=len(frame),
        eligible_events=events,
        bucket_summary=summarize_buckets(events),
        diagnostics=build_diagnostics(events),
    )


def write_outputs(result: AnalysisResult, output_dir: str | Path) -> None:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    result.eligible_events.to_csv(destination / "eligible_events.csv", index=False)
    result.bucket_summary.to_csv(destination / "bucket_summary.csv", index=False)
    (destination / "diagnostics.json").write_text(
        json.dumps(result.diagnostics, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", help="Path to a release CSV or sample ZIP")
    parser.add_argument("--output-dir", default="output", help="Directory for result artifacts")
    args = parser.parse_args()

    frame = load_dataset(args.dataset)
    result = analyze(frame)
    write_outputs(result, args.output_dir)
    print(json.dumps({"source_rows": result.source_rows, **result.diagnostics}, indent=2))


if __name__ == "__main__":
    main()
