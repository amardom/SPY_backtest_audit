"""Explicit, free acquisition of development/validation data only."""
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .data import COLUMNS, DataValidationError, load_snapshot
def query_url(plan):
    start = plan["development"]["start"]
    end = plan["acquisition_end_exclusive"]
    if not start < end <= plan["final_evaluation"]["start"] or end > "2022-01-01":
        raise DataValidationError("Acquisition must exclude the reserved final-evaluation period")
    stamp = lambda value: int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp())
    params = dict(period1=stamp(start), period2=stamp(end), interval="1d", events="div,splits")
    return "https://query1.finance.yahoo.com/v8/finance/chart/SPY?" + urlencode(params)
def normalize_yahoo(raw, plan):
    """Keep Yahoo's split-adjusted OHLC and adjusted close distinct."""
    try:
        envelope = json.loads(raw, parse_float=Decimal)
        chart = envelope["chart"]
        if chart.get("error"):
            raise ValueError(str(chart["error"]))
        data = chart["result"][0]
        meta = data["meta"]
        if meta["symbol"] != "SPY" or meta["currency"] != "USD" or meta["exchangeTimezoneName"] != "America/New_York":
            raise ValueError("Unexpected instrument, currency or exchange timezone")
        local = ZoneInfo(meta["exchangeTimezoneName"])
        session = lambda stamp: datetime.fromtimestamp(int(stamp), local).date().isoformat()
        events = data.get("events", {})
        dividends = {session(e["date"]): e["amount"] for e in events.get("dividends", {}).values()}
        splits = {session(e["date"]): Decimal(str(e["numerator"])) / Decimal(str(e["denominator"]))
                  for e in events.get("splits", {}).values()}
        timestamps = data["timestamp"]
        quote = data["indicators"]["quote"][0]
        adjusted = data["indicators"]["adjclose"][0]["adjclose"]
        if not timestamps or any(len(quote[k]) != len(timestamps) for k in ("open", "high", "low", "close", "volume")) or len(adjusted) != len(timestamps):
            raise ValueError("Empty or unequal price arrays")
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(COLUMNS)
        days = set()
        for i, stamp in enumerate(timestamps):
            day = session(stamp)
            if not plan["development"]["start"] <= day < plan["acquisition_end_exclusive"]:
                raise ValueError("Response contains a date outside the requested research window")
            days.add(day)
            values = [quote[k][i] for k in ("open", "high", "low", "close")]
            values += [adjusted[i], quote["volume"][i], dividends.get(day, 0), splits.get(day, 1)]
            if any(v is None for v in values):
                raise ValueError(f"Missing vendor value on {day}; not silently dropped")
            writer.writerow([day] + [str(v) for v in values])
        if not set(dividends).union(splits).issubset(days):
            raise ValueError("Corporate-action date has no corresponding daily bar")
        return buffer.getvalue().encode("utf-8")
    except (KeyError, IndexError, TypeError, ValueError, ArithmeticError) as exc:
        raise DataValidationError(f"Invalid Yahoo response: {exc}") from exc
def acquire_snapshot(root: Path):
    plan = json.loads((root / "research/data_plan.json").read_text(encoding="utf-8"))
    url = query_url(plan)
    directory = root / "data/raw"
    directory.mkdir(parents=True, exist_ok=True)
    original = directory / "spy.yahoo.json"
    receipt = directory / "spy.yahoo.acquisition.json"
    csv_path = directory / "spy.csv"
    manifest_path = directory / "spy.manifest.json"
    if original.exists() != receipt.exists():
        raise DataValidationError("Incomplete acquisition archive; refusing to overwrite it")
    if not original.exists():
        request = Request(url, headers={"User-Agent": "spy-backtest-audit/0.1 research"})
        with urlopen(request, timeout=30) as response:
            raw = response.read()
        # Validate structure and date boundaries before accepting the archive.
        normalize_yahoo(raw, plan)
        acquisition = dict(url=url, retrieved_at=datetime.now(timezone.utc).isoformat(),
                           sha256=hashlib.sha256(raw).hexdigest())
        original.write_bytes(raw)
        receipt.write_text(json.dumps(acquisition, indent=2) + "\n", encoding="utf-8")
    raw = original.read_bytes()
    acquisition = json.loads(receipt.read_text(encoding="utf-8"))
    if acquisition["url"] != url or acquisition["sha256"] != hashlib.sha256(raw).hexdigest():
        raise DataValidationError("Archived request or response hash mismatch")
    normalized = normalize_yahoo(raw, plan)
    manifest = dict(schema_version=1, symbol="SPY", currency="USD",
                    source="Yahoo Finance public chart endpoint / " + url,
                    retrieved_at=acquisition["retrieved_at"], price_basis="split_adjusted",
                    adjustment_notes="Yahoo OHLC are split-adjusted, not asserted as-traded. adjusted_close additionally reflects vendor dividend adjustments. Values are observed at retrieval time, not a point-in-time archive. Event amounts and volume are retained as supplied; split_factor is new/old shares, 1 on non-event sessions.",
                    usage_notes="Free provisional research source; no data redistribution or public-report usage permission has been established. Raw and normalized vendor data remain untracked.",
                    sha256=hashlib.sha256(normalized).hexdigest(),
                    original_sha256=acquisition["sha256"], source_url=url,
                    plan_version=plan["version"])
    # An existing frozen pair is immutable. A new provider revision requires a new archive.
    if csv_path.exists() or manifest_path.exists():
        if not csv_path.exists() or not manifest_path.exists():
            raise DataValidationError("Incomplete normalized snapshot; refusing to overwrite")
        if csv_path.read_bytes() != normalized or json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise DataValidationError("Frozen snapshot differs; refusing to overwrite")
    else:
        # Validate in a temporary directory before installing the normalized pair.
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            candidate = Path(temporary)
            (candidate / "prices.csv").write_bytes(normalized)
            (candidate / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            load_snapshot(candidate / "prices.csv", candidate / "manifest.json")
        csv_path.write_bytes(normalized)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return csv_path, manifest_path
