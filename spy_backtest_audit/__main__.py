"""Single entry point for the research workflow."""
import argparse
from decimal import Decimal
from urllib.error import URLError

from .acquire import acquire_snapshot
from pathlib import Path

from .data import DataValidationError, load_snapshot
from .calendar import audit_calendar
from .protocol import verify_validation_freeze
from .validation import write_validation_artifacts
from .uncertainty import write_uncertainty_artifacts
from .family import write_family_artifacts
from .workflow import write_signal_artifacts, write_backtest_artifacts, write_control_artifacts
def main(argv=None):
    parser = argparse.ArgumentParser(description="SPY Backtest Audit: reproduce development research and frozen temporal validation.")
    parser.add_argument("--data", type=Path, help="Daily CSV; default: data/raw/spy.csv")
    parser.add_argument("--manifest", type=Path, help="Snapshot manifest; default: data/raw/spy.manifest.json")
    parser.add_argument("--fetch", action="store_true", help="Acquire free 2000-2021 data once; reuse the frozen archive thereafter")
    args = parser.parse_args(argv)
    if args.fetch and (args.data is not None or args.manifest is not None):
        parser.error("--fetch cannot be combined with explicit paths")
    if (args.data is None) != (args.manifest is None):
        parser.error("Supply --data and --manifest together")
    root = Path(__file__).resolve().parents[1]
    if not (root / "research" / "protocol.md").is_file():
        parser.error("Research protocol not found")
    if args.fetch:
        try:
            acquire_snapshot(root)
        except (DataValidationError, OSError, ValueError, URLError) as exc:
            parser.exit(1, f"Acquisition failed: {exc}\n")
    csv_path = args.data if args.data is not None else root / "data/raw/spy.csv"
    manifest_path = args.manifest if args.manifest is not None else root / "data/raw/spy.manifest.json"
    print("SPY Backtest Audit | Buying the Dip: Does Timing Add Value?")
    if args.data is None and not csv_path.exists() and not manifest_path.exists():
        print("Status: awaiting data. No provider or real snapshot selected.")
        print("Expected: data/raw/spy.csv and data/raw/spy.manifest.json")
        print("See research/data_contract.md. No backtest or report generated.")
        return 0
    if args.data is None:
        try:
            from .report import generate_report
        except ImportError as exc:
            parser.exit(1, "Report dependencies missing. Use the prepared .venv or install requirements.lock.\n")
    try:
        snapshot = load_snapshot(csv_path, manifest_path)
    except DataValidationError as exc:
        parser.exit(1, f"Data validation failed: {exc}\n")
    print(f"VALID SNAPSHOT | {snapshot.symbol} | {len(snapshot.bars)} daily bars")
    print(f"Coverage: {snapshot.bars[0].date} through {snapshot.bars[-1].date}")
    print(f"Source: {snapshot.source}")
    print(f"SHA-256: {snapshot.sha256}")
    print("Checks: file identity, manifest fields, dates, finite values and OHLC integrity.")
    print("Vendor price accuracy and usage permissions are not certified.")
    print(f"Corporate actions: {sum(b.dividend > 0 for b in snapshot.bars)} dividend sessions; {sum(b.split_factor != 1 for b in snapshot.bars)} split sessions.")
    if args.data is None:
        try:
            calendar = audit_calendar(root, snapshot)
            verify_validation_freeze(root)
        except (OSError, ValueError, KeyError) as exc:
            parser.exit(1, f"Calendar/protocol check failed: {exc}\n")
        print(f"Calendar PASS: {calendar['observed_sessions']} sessions match pinned XNYS reference.")
        print("Validation rules frozen; this command now evaluates the fixed temporal-validation method.")
        print("Final evaluation 2022-2025: not requested by this downloader.")
    if args.data is None:
        try:
            signals, output = write_signal_artifacts(root, snapshot)
        except (OSError, ValueError, KeyError) as exc:
            parser.exit(1, f"Signal generation failed: {exc}\n")
        print(f"Development signal events: {len(signals.events)}; accepted: {len(signals.trades)}")
        print(f"Signal artifacts: {output}")
        try:
            summaries, backtest_output = write_backtest_artifacts(root, snapshot, signals)
        except (OSError, ValueError, KeyError) as exc:
            parser.exit(1, f"Backtest failed: {exc}\n")
        for summary in summaries:
            if summary["primary"]:
                print(f"Development / {summary['strategy']} / 5 bps per side: return {Decimal(summary['total_return']):.2%}, close drawdown {Decimal(summary['max_close_drawdown']):.2%}")
        print(f"Backtest artifacts: {backtest_output}")
        print("Building 500 development-only random-entry references...", flush=True)
        try:
            controls, control_output = write_control_artifacts(root, snapshot, signals)
        except (OSError, ValueError, KeyError) as exc:
            parser.exit(1, f"Random-reference failed: {exc}\n")
        print(f"Control artifacts: {control_output}")
        print(f"Temporal and risk diagnostics: {root / 'outputs/diagnostics'}")
        print("Descriptive development results only. Random references are not risk-matched or a significance test.")
        print("Running frozen 2016-2021 temporal validation...", flush=True)
        try:
            validation, validation_output = write_validation_artifacts(root, snapshot)
        except (OSError, ValueError, KeyError) as exc:
            parser.exit(1, f"Temporal validation failed: {exc}\n")
        print(f"Validation screen: {validation['classification']}")
        print(f"Validation artifacts: {validation_output}")
        print("Computing exploratory paired block-bootstrap intervals...", flush=True)
        try:
            uncertainty, uncertainty_output = write_uncertainty_artifacts(root, snapshot)
        except (OSError, ValueError, KeyError) as exc:
            parser.exit(1, f"Uncertainty calculation failed: {exc}\n")
        print(f"Uncertainty artifacts: {uncertainty_output}")
        print("Computing exploratory 27-cell parameter family...", flush=True)
        try:
            family, family_output = write_family_artifacts(root, snapshot)
        except (OSError, ValueError, KeyError) as exc:
            parser.exit(1, f"Parameter family failed: {exc}\n")
        print(f"Parameter family artifacts: {family_output}")
        try:
            pdf_path = generate_report(root)
        except (OSError, ValueError, KeyError) as exc:
            parser.exit(1, f"Report generation failed: {exc}\n")
        print(f"Research PDF: {pdf_path}")
    print("No 2022-2025 final-evaluation results generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
