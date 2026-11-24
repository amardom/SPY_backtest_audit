# Daily data contract - version 1

The CSV validator checks the schema, manifest and exact file identity. The current
snapshot comes from Yahoo Finance; its acquisition settings are in `data_plan.json`.
Input records are not reordered, deduplicated or repaired.

## CSV

UTF-8 CSV, one daily regular-session bar per exchange session, oldest first.
Header order is exact:

```csv
date,open,high,low,close,adjusted_close,volume,dividend,split_factor
```

- `date`: exchange-local session date, `YYYY-MM-DD`, strictly increasing and unique.
- `open,high,low,close`: positive USD prices on the declared `price_basis`: `unadjusted`
  or `split_adjusted`. These conventions are never interchangeable. Yahoo OHLC
  are explicitly labeled `split_adjusted`, not as-traded execution prices.
- `adjusted_close`: positive provider-adjusted close, retained separately. Explain
  its dividend/split methodology in the manifest. It is not an execution price.
- `volume`: nonnegative whole shares. Zero is allowed, not proof of liquidity.
- `dividend`: nonnegative USD per share on the ex-dividend session; zero otherwise.
  Record the provider's split treatment and event conventions in adjustment_notes.
- `split_factor`: new shares per old share on the effective session. Use **1** when
  there is no split, **2** for a 2-for-1 split. Do not forward vendor zero placeholders.

All numeric fields must be present and finite. Low must not exceed either open or
close; high must not be below either. No inference or return calculation is performed.
The default workflow also compares session dates with the pinned XNYS calendar.
Blank lines are ignored by the CSV reader and are not treated as session records.

## Manifest

A separate UTF-8 JSON object accompanies the exact CSV bytes:

```json
{
  "schema_version": 1,
  "symbol": "SPY",
  "currency": "USD",
  "source": "Provider, endpoint and explicit acquisition parameters",
  "retrieved_at": "2026-10-20T12:00:00+00:00",
  "price_basis": "unadjusted",
  "adjustment_notes": "Describe adjusted_close and corporate-action conventions",
  "usage_notes": "Document license, intended use and identical-snapshot access",
  "sha256": "REPLACE_WITH_SHA256_OF_THE_EXACT_CSV_BYTES"
}
```

This is a schema example, not a real acquisition record. SHA-256 detects a change
against the supplied manifest; it does not authenticate the provider or prove the
recorded metadata true. Formatting changes to the CSV also change the hash.

## Commands

The included snapshot and manifest are `data/raw/spy.csv` and
`data/raw/spy.manifest.json`. After environment setup, run the recorded study with:

```bash
python3 run.py
```

To validate another pair without running a backtest:

```bash
python3 -m spy_backtest_audit --data /path/to/spy.csv --manifest /path/to/spy.manifest.json
```

Explicit paths invoke schema/identity checks only. They do not check those files
against the study's frozen dataset or run its trading rules.

The engine's `--fetch` flag acquires only the allowed window, archives the original
response and normalizes it. An existing archive is reused. Normal runs do not
request data, and the downloader does not request the reserved 2022-2025 period.
A revised vendor response requires a separate archive and recorded protocol;
changing a manifest hash is not a substitute for reproducing the original input.

Validation errors return exit code 1; argument errors return 2. The direct engine
reports awaiting data and exits 0 if both default input files are absent. The
launcher instead reports missing required inputs and returns 1. A partial pair
is an error in either path.
