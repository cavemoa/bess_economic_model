"""Download and validate public Electricity Authority price inputs."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

import pandas as pd


EA_BLOB_ROOT = "https://emidatasets.blob.core.windows.net/publicdata/Datasets/Wholesale/DispatchAndPricing"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1_048_576), b""):
            digest.update(block)
    return digest.hexdigest()


def _download_if_missing(url: str, destination: Path) -> tuple[Path, bool]:
    """Fetch a public CSV once, retaining a byte-identical local cache."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return destination, False

    request = Request(url, headers={"User-Agent": "bess-economic-model/0.1"})
    with urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())
    return destination, True


def _source_record(path: Path, url: str, downloaded: bool) -> dict[str, Any]:
    return {
        "local_file": str(path.as_posix()),
        "source_url": url,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "downloaded_this_run": downloaded,
    }


def _month_dates(month: str) -> pd.DatetimeIndex:
    start = pd.Timestamp(f"{month}-01")
    end = start + pd.offsets.MonthEnd(0)
    return pd.date_range(start, end, freq="D")


def configured_months(data_config: dict[str, Any]) -> list[str]:
    """Return one explicit month or an inclusive calendar-month range."""
    if "month" in data_config:
        month = str(data_config["month"])
        try:
            return [str(pd.Period(month, freq="M"))]
        except ValueError as error:
            raise ValueError("data.month must use YYYY-MM format.") from error

    if "start_month" not in data_config or "end_month" not in data_config:
        raise ValueError("Specify either data.month or both data.start_month and data.end_month.")
    try:
        start = pd.Period(str(data_config["start_month"]), freq="M")
        end = pd.Period(str(data_config["end_month"]), freq="M")
    except ValueError as error:
        raise ValueError("data.start_month and data.end_month must use YYYY-MM format.") from error
    if start > end:
        raise ValueError("data.start_month must not be later than data.end_month.")
    return [str(period) for period in pd.period_range(start, end, freq="M")]


def configured_period_label(data_config: dict[str, Any]) -> str:
    """Return a stable output-directory label for the configured historic period."""
    months = configured_months(data_config)
    return months[0] if len(months) == 1 else f"{months[0]}_to_{months[-1]}"


def _validate_market_data(market: pd.DataFrame, expected_dates: pd.DatetimeIndex) -> None:
    """Validate final-settlement data, allowing 46/50-period daylight-saving days."""
    expected_date_strings = set(expected_dates.date.astype(str))
    actual_date_strings = set(market["TradingDate"])
    if actual_date_strings != expected_date_strings:
        missing = sorted(expected_date_strings - actual_date_strings)
        unexpected = sorted(actual_date_strings - expected_date_strings)
        raise ValueError(f"Market data dates do not match the requested period. Missing={missing}, unexpected={unexpected}.")
    if market[["sfd_price_nzd_per_mwh", "fir_price_nzd_per_mwh", "sir_price_nzd_per_mwh"]].isna().any().any():
        raise ValueError("Missing final energy or reserve prices after merging official datasets.")
    if market.duplicated(["TradingDate", "TradingPeriod"]).any():
        raise ValueError("Duplicate trading periods in market input.")

    periods_per_day = market.groupby("TradingDate")["TradingPeriod"].nunique()
    if not periods_per_day.isin([46, 48, 50]).all():
        bad_days = periods_per_day[~periods_per_day.isin([46, 48, 50])].to_dict()
        raise ValueError(f"Expected 46, 48 or 50 trading periods per day; found {bad_days}.")


def _load_month_market_data(
    month: str,
    node: str,
    island: str,
    raw_data_root: Path,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Load final settlement energy and reserve prices for one calendar month."""
    raw_dir = raw_data_root / month
    dates = _month_dates(month)

    energy_filename = f"{month.replace('-', '')}_FinalEnergyPrices.csv"
    energy_url = f"{EA_BLOB_ROOT}/FinalEnergyPrices/ByMonth/{energy_filename}"
    energy_path, downloaded = _download_if_missing(energy_url, raw_dir / energy_filename)
    source_records = [_source_record(energy_path, energy_url, downloaded)]

    energy = pd.read_csv(
        energy_path,
        usecols=["TradingDate", "TradingPeriod", "PointOfConnection", "DollarsPerMegawattHour"],
    )
    energy = energy.loc[energy["PointOfConnection"].eq(node)].copy()
    if energy.empty:
        raise ValueError(f"No final energy-price rows were found for {node} in {energy_filename}.")
    energy = energy.rename(columns={"DollarsPerMegawattHour": "sfd_price_nzd_per_mwh"})
    energy["TradingDate"] = pd.to_datetime(energy["TradingDate"]).dt.date.astype(str)

    # The daily folder is a rolling publication location. Use the EA's complete monthly
    # archive so historic annual runs do not fail once daily files roll off the listing.
    reserve_filename = f"{month.replace('-', '')}_FinalReservePrices.csv"
    reserve_url = f"{EA_BLOB_ROOT}/FinalReservePrices/ByMonth/{reserve_filename}"
    reserve_path, reserve_downloaded = _download_if_missing(reserve_url, raw_dir / reserve_filename)
    source_records.append(_source_record(reserve_path, reserve_url, reserve_downloaded))
    reserve = pd.read_csv(reserve_path)
    reserve = reserve.loc[reserve["Island"].eq(island)].copy()
    reserve["TradingDate"] = pd.to_datetime(reserve["TradingDate"]).dt.date.astype(str)
    reserve = reserve.rename(
        columns={
            "FIRDollarsPerMegawattHour": "fir_price_nzd_per_mwh",
            "SIRDollarsPerMegawattHour": "sir_price_nzd_per_mwh",
        }
    )
    reserve = reserve[["TradingDate", "TradingPeriod", "fir_price_nzd_per_mwh", "sir_price_nzd_per_mwh"]]

    market = energy.merge(reserve, on=["TradingDate", "TradingPeriod"], how="inner", validate="one_to_one")
    market = market.sort_values(["TradingDate", "TradingPeriod"]).reset_index(drop=True)
    _validate_market_data(market, dates)
    return market, source_records


def load_market_data(config: dict[str, Any], project_root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Return final SFD energy and NI reserve settlement prices for a historic period.

    The cash-flow model intentionally uses final settlement prices. Dispatch-price data is
    useful for future rolling-horizon analysis but is not a settlement-price substitute.
    """
    data_config = config["data"]
    months = configured_months(data_config)
    node = str(data_config["node"])
    island = str(data_config["island"])
    raw_data_root = project_root / data_config["raw_data_dir"]

    market_frames: list[pd.DataFrame] = []
    source_records: list[dict[str, Any]] = []
    for month in months:
        month_market, month_sources = _load_month_market_data(month, node, island, raw_data_root)
        market_frames.append(month_market)
        source_records.extend(month_sources)
    market = pd.concat(market_frames, ignore_index=True)
    market = market.sort_values(["TradingDate", "TradingPeriod"]).reset_index(drop=True)
    expected_dates = pd.DatetimeIndex([])
    for month in months:
        expected_dates = expected_dates.append(_month_dates(month))
    _validate_market_data(market, expected_dates)

    market["timestamp_nz"] = pd.to_datetime(market["TradingDate"]) + pd.to_timedelta(
        (market["TradingPeriod"] - 1) * 30, unit="min"
    )
    market = market[
        [
            "timestamp_nz",
            "TradingDate",
            "TradingPeriod",
            "sfd_price_nzd_per_mwh",
            "fir_price_nzd_per_mwh",
            "sir_price_nzd_per_mwh",
        ]
    ]

    manifest = {
        "created_at_utc": datetime.now(UTC).isoformat(),
        "market_node": node,
        "island": island,
        "months": months,
        "period_label": configured_period_label(data_config),
        "settlement_interval_minutes": 30,
        "sources": source_records,
    }
    return market, manifest


def write_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
