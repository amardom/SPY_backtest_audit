"""Compare snapshot dates with the pinned XNYS session calendar."""
import csv
from datetime import date
import hashlib
import io
import json

from .data import DataValidationError
def compare_session_dates(observed, expected):
    observed, expected = tuple(observed), tuple(expected)
    if any(observed[i] <= observed[i-1] for i in range(1, len(observed))):
        raise DataValidationError("Observed sessions must be unique and strictly increasing")
    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    return dict(passed=not missing and not unexpected, observed_sessions=len(observed),
                expected_sessions=len(expected), missing=[str(d) for d in missing],
                unexpected=[str(d) for d in unexpected])
def audit_calendar(root, snapshot):
    directory = root / "research/calendar"
    raw = (directory / "xnys_2000_2021.csv").read_bytes()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    digest = hashlib.sha256(raw).hexdigest()
    if manifest.get("schema_version") != 1 or manifest.get("calendar") != "XNYS" or manifest.get("sha256") != digest:
        raise DataValidationError("Calendar identity or hash mismatch")
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8")))
    if reader.fieldnames != ["date"]:
        raise DataValidationError("Invalid calendar header")
    expected = tuple(date.fromisoformat(row["date"]) for row in reader)
    if not expected or len(expected) != manifest["sessions"] or any(expected[i] <= expected[i-1] for i in range(1, len(expected))):
        raise DataValidationError("Invalid calendar session sequence")
    plan = json.loads((root / "research/data_plan.json").read_text())
    if manifest["start"] != plan["development"]["start"] or manifest["end_exclusive"] != plan["acquisition_end_exclusive"]:
        raise DataValidationError("Calendar coverage must match the acquired research window")
    result = compare_session_dates((b.date for b in snapshot.bars), expected)
    result.update(calendar="XNYS", reference_sha256=digest, snapshot_sha256=snapshot.sha256,
                  packages=manifest["packages"], scope="2000-2021 dates only; no validation performance",
                  limitations=["Agreement with a library calendar model, not official exchange certification.",
                               "Does not validate prices, dividend accuracy, exchange opening fills or data usage rights.",
                               "Early-close days count as sessions; intraday hours are not audited."])
    output = root / "outputs/data"
    output.mkdir(parents=True, exist_ok=True)
    (output / "session_audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if not result["passed"]:
        raise DataValidationError(f"Calendar mismatch: {len(result['missing'])} missing and {len(result['unexpected'])} unexpected sessions; see outputs/data/session_audit.json")
    return result
