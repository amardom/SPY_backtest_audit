"""Regenerate the versioned offline calendar using the pinned tool environment."""
import csv
import hashlib
from importlib.metadata import version
import io
import json
from pathlib import Path
import platform

import exchange_calendars as calendars

ROOT = Path(__file__).resolve().parents[1]
if version("exchange_calendars") != "4.13.2":
    raise SystemExit("Install research/calendar/requirements.lock in the calendar tool environment")
calendar = calendars.get_calendar("XNYS", start="2000-01-01", end="2021-12-31")
sessions = calendar.sessions
stream = io.StringIO(newline="")
writer = csv.writer(stream, lineterminator="\n")
writer.writerow(("date",))
writer.writerows((stamp.date().isoformat(),) for stamp in sessions)
raw = stream.getvalue().encode("utf-8")
directory = ROOT / "research/calendar"
(directory / "xnys_2000_2021.csv").write_bytes(raw)
packages = ("exchange_calendars", "pandas", "numpy", "tzdata", "python-dateutil", "pyluach", "korean_lunar_calendar", "toolz", "six")
manifest = dict(schema_version=1, calendar="XNYS", start="2000-01-01", end_exclusive="2022-01-01",
                source="https://github.com/gerrymanoim/exchange_calendars", python=platform.python_version(),
                packages={name: version(name) for name in packages}, sessions=len(sessions),
                sha256=hashlib.sha256(raw).hexdigest(),
                generator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                notes="Offline model calendar, not an official exchange certification. Early closes remain sessions. No prices or strategy returns.")
(directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(f"Recorded {len(sessions)} XNYS sessions; calendar SHA-256 {manifest['sha256']}")
