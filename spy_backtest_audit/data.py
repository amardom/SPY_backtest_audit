"""Validate daily prices and snapshot metadata."""
import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path


COLUMNS = ("date", "open", "high", "low", "close", "adjusted_close", "volume", "dividend", "split_factor")
class DataValidationError(ValueError):
    """The snapshot or its provenance failed validation."""
@dataclass(frozen=True)
class DailyBar:
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal
    volume: int
    dividend: Decimal
    split_factor: Decimal
@dataclass(frozen=True)
class Snapshot:
    bars: tuple[DailyBar, ...]
    sha256: str
    source: str
    symbol: str
def load_snapshot(csv_path: Path, manifest_path: Path) -> Snapshot:
    """Check identity, provenance and row integrity; never repair input silently."""
    try:
        raw = Path(csv_path).read_bytes()
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise DataValidationError(f"Cannot read snapshot or manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise DataValidationError("Manifest must be a JSON object")
    for key in ("source", "retrieved_at", "sha256", "adjustment_notes", "usage_notes"):
        if not isinstance(manifest.get(key), str) or not manifest[key].strip():
            raise DataValidationError(f"Manifest requires non-empty {key}")
    if type(manifest.get("schema_version")) is not int or manifest["schema_version"] != 1:
        raise DataValidationError("Unsupported manifest schema_version; expected 1")
    if manifest.get("symbol") != "SPY" or manifest.get("currency") != "USD":
        raise DataValidationError("This study currently accepts only SPY in USD")
    if manifest.get("price_basis") not in ("unadjusted", "split_adjusted"):
        raise DataValidationError("Declare OHLC as unadjusted or split_adjusted; preserve adjusted_close separately")
    try:
        retrieved = datetime.fromisoformat(manifest["retrieved_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise DataValidationError("retrieved_at must be an ISO timestamp with timezone") from exc
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise DataValidationError("retrieved_at must include a timezone")
    digest = hashlib.sha256(raw).hexdigest()
    if manifest["sha256"] != digest:
        raise DataValidationError("SHA-256 mismatch: the CSV differs from the recorded snapshot")
    try:
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), strict=True)
        if tuple(reader.fieldnames or ()) != COLUMNS:
            raise DataValidationError("CSV header must be: " + ",".join(COLUMNS))
        bars = []
        for row_number, row in enumerate(reader, 2):
            if None in row or any(value is None or not value.strip() for value in row.values()):
                raise DataValidationError(f"Row {row_number}: missing or extra fields")
            try:
                day = date.fromisoformat(row["date"])
                if day.isoformat() != row["date"]:
                    raise ValueError("date must use YYYY-MM-DD")
                values = {key: Decimal(row[key]) for key in COLUMNS[1:]}
            except (ValueError, InvalidOperation) as exc:
                raise DataValidationError(f"Row {row_number}: invalid date or number") from exc
            if bars and day <= bars[-1].date:
                raise DataValidationError(f"Row {row_number}: dates must be unique and strictly increasing")
            if not all(value.is_finite() for value in values.values()):
                raise DataValidationError(f"Row {row_number}: all numbers must be finite")
            if any(values[key] <= 0 for key in ("open", "high", "low", "close", "adjusted_close", "split_factor")):
                raise DataValidationError(f"Row {row_number}: prices and split_factor must be positive")
            if not values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]:
                raise DataValidationError(f"Row {row_number}: inconsistent OHLC range")
            volume = values.pop("volume")
            if volume < 0 or volume != volume.to_integral_value():
                raise DataValidationError(f"Row {row_number}: volume must be a nonnegative integer")
            if values["dividend"] < 0:
                raise DataValidationError(f"Row {row_number}: dividend must be nonnegative")
            bars.append(DailyBar(date=day, volume=int(volume), **values))
    except (UnicodeError, csv.Error) as exc:
        raise DataValidationError(f"Invalid UTF-8 CSV: {exc}") from exc
    if not bars:
        raise DataValidationError("CSV must contain at least one daily bar")
    return Snapshot(tuple(bars), digest, manifest["source"], manifest["symbol"])
