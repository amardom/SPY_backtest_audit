"""Generate the research report from recorded results."""
import csv
from datetime import date
from decimal import Decimal
import hashlib
from html import escape
from importlib.metadata import version
import json
from pathlib import Path
from functools import partial

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image


INK = "#173047"
TEAL = "#20776E"
RED = "#AD514B"
MUTED = "#617582"
LINE = "#DCE5EA"
PALE = "#F1F5F7"
WIDTH = 174 * mm
def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))
def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))
def pct(value):
    return f"{Decimal(str(value)):.2%}"
def scenario(summary, name="dip", fee="5"):
    return next(row for row in summary["scenarios"]
                if row["strategy"] == name and row["cost_bps_per_side"] == fee)
def collect_facts(root):
    """Keep every displayed headline traceable to one computed result."""
    development = read_json(root / "outputs/backtest/summary.json")
    controls = read_json(root / "outputs/controls/summary.json")
    validation = read_json(root / "outputs/validation/summary.json")
    audit = read_json(root / "outputs/data/session_audit.json")
    observation = read_json(root / "research/validation_first_observation.json")["evidence"]
    for key in ("snapshot_sha256", "freeze_sha256", "classification", "scenarios", "primary_control_contrast", "control_return_quantiles"):
        if observation[key] != validation[key]:
            raise ValueError(f"Report differs from first validation observation: {key}")
    if not audit["passed"] or development["signal_run"]["snapshot_sha256"] != validation["snapshot_sha256"]:
        raise ValueError("Report inputs do not share a validated snapshot")
    if validation["controls_count"] != controls["config"]["calendars"]:
        raise ValueError("Report requires matching control draw counts")
    uncertainty = read_json(root / "outputs/uncertainty/summary.json")
    if uncertainty["snapshot_sha256"] != validation["snapshot_sha256"]:
        raise ValueError("Uncertainty snapshot differs from validation")
    for relative, expected in uncertainty["source_sha256"].items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Uncertainty inputs changed; regenerate the extension")
    family = read_json(root / "outputs/parameter_family/summary.json")
    if family["snapshot_sha256"] != validation["snapshot_sha256"]:
        raise ValueError("Family snapshot differs from validation")
    for relative, expected in family["source_sha256"].items():
        if hashlib.sha256((root / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Parameter family inputs changed; regenerate the extension")
    return dict(family=family, development=development, development_controls=controls, validation=validation, audit=audit, uncertainty=uncertainty,
                headline=dict(validation_return=pct(scenario(validation)["total_return"]),
                              control_median=pct(validation["control_return_quantiles"]["p50"]),
                              contrast_pp=f"{Decimal(validation['primary_control_contrast'])*100:+.2f} pp",
                              trades=scenario(validation)["trades"],
                              classification=validation["classification"]))
def style_axis(ax, percent=True):
    ax.spines[["top", "right"]].set_visible(False)
    for spine in ("bottom", "left"):
        ax.spines[spine].set_color(LINE)
    ax.tick_params(colors=MUTED, labelsize=8.5, length=0)
    ax.grid(axis="y", color=LINE, linewidth=.6)
    ax.set_axisbelow(True)
    if percent:
        ax.yaxis.set_major_formatter(PercentFormatter(1, decimals=0))
def make_figures(root, output, facts):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlecolor": INK,
                         "text.color": INK, "axes.labelcolor": MUTED, "svg.hashsalt": "spy_backtest_audit-v1"})
    output.mkdir(parents=True, exist_ok=True)
    figures = {}
    def save(name, fig):
        png = output / f"{name}.png"
        fig.savefig(png, dpi=220, facecolor="white", metadata={"Software": "SPY Backtest Audit"})
        fig.savefig(output / f"{name}.svg", metadata={"Date": None, "Creator": "SPY Backtest Audit"})
        plt.close(fig)
        figures[name] = png

    dev, val = facts["development"], facts["validation"]
    control = facts["development_controls"]
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.65), sharey=True, layout="constrained")
    for ax, label, summary, median in ((axes[0], "Development | 2000-2015", dev, control["control_return_quantiles_nearest_rank"]["p50"]),
                                       (axes[1], "Validation | 2016-2021", val, val["control_return_quantiles"]["p50"])):
        values = [float(scenario(summary)["total_return"]), float(median)]
        ax.bar(["Dip rule", "Random median"], values, color=[INK, TEAL], width=.55)
        ax.axhline(0, color=MUTED, lw=.7)
        style_axis(ax)
        ax.set_title(label, loc="left", pad=12, fontsize=10)
        ax.set_ylim(-.06, max(float(scenario(dev)["total_return"]), float(scenario(val)["total_return"]),
                                   float(control["control_return_quantiles_nearest_rank"]["p50"]),
                                   float(val["control_return_quantiles"]["p50"])) + .13)
        for i, value in enumerate(values):
            ax.annotate(f"{value:.2%}", (i, value), xytext=(0, 7 if value>=0 else -14),
                        textcoords="offset points", ha="center", fontsize=10, weight="bold", color=INK)
    save("headline", fig)

    fig, axes = plt.subplots(2, 2, figsize=(6.8, 7.1), layout="constrained", gridspec_kw={"height_ratios": [1.5, 1]})
    for column, (folder, label) in enumerate((("backtest", "Development | 2000-2015"), ("validation", "Validation | 2016-2021"))):
        for name, text, color in (("dip", "Dip rule", INK), ("buy_and_hold", "Buy and hold", TEAL)):
            rows = read_csv(root / f"outputs/{folder}/{name}_5bps_equity.csv")
            days = [date.fromisoformat(r["date"]) for r in rows]
            capital = float((dev if folder == "backtest" else val)["initial_capital_usd"])
            wealth = [float(r["equity"])/capital*100 for r in rows]
            dd = [float(r["drawdown"]) for r in rows]
            axes[0, column].plot(days, wealth, color=color, lw=1.3, label=text)
            axes[1, column].plot(days, dd, color=color, lw=1.1)
        axes[0, column].set_title(label, loc="left", pad=12, fontsize=10)
        axes[0, column].set_ylabel("Wealth index | initial capital = 100")
        axes[1, column].set_ylabel("Daily-close drawdown")
        axes[0, column].legend(frameon=False, fontsize=8, loc="upper left")
        for row in (0, 1):
            style_axis(axes[row, column], percent=row == 1)
            axes[row, column].tick_params(axis="x", rotation=35)
            axes[row, column].set_xlim(days[0], days[-1])
    save("paths", fig)

    fig, axes = plt.subplots(1, 2, figsize=(6.8, 4.1), layout="constrained")
    for ax, folder, label, summary in ((axes[0], "controls", "Development", dev), (axes[1], "validation", "Validation", val)):
        filename = "draws.csv" if folder == "controls" else "control_draws.csv"
        draws = [float(r["total_return"]) for r in read_csv(root / f"outputs/{folder}/{filename}")]
        actual = float(scenario(summary)["total_return"])
        ax.hist(draws, bins=25, color="#BDD2CE", edgecolor="white", lw=.5)
        ax.axvline(actual, color=RED, lw=2, label="Dip rule")
        ax.axvline(sorted(draws)[len(draws)//2-1], color=TEAL, lw=1.2, linestyle="--", label="Control median")
        ax.set_title(label, loc="left", pad=12)
        ax.set_xlabel("Cumulative net return")
        ax.set_ylabel("Random calendars")
        ax.xaxis.set_major_formatter(PercentFormatter(1, decimals=0))
        style_axis(ax, percent=False)
        ax.legend(frameon=False, fontsize=8, loc="upper right")
    save("controls", fig)

    fig, axes = plt.subplots(2, 1, figsize=(6.8, 4.8), layout="constrained")
    development_rows = read_csv(root / "outputs/diagnostics/primary_periods.csv")
    validation_rows = read_csv(root / "outputs/validation/primary_periods.csv")
    diagnostic = read_json(root / "outputs/diagnostics/summary.json")
    dev_median = {c["period"]: float(c["control_quantiles"]["total_return"]["p50"])
                  for c in diagnostic["comparisons"] if c["period_kind"] == "year"}
    from .diagnostics import quantiles
    val_controls = read_csv(root / "outputs/validation/control_periods.csv")
    for ax, rows, medians, label in ((axes[0], development_rows, dev_median, "Development | annual returns"),
                                     (axes[1], validation_rows, None, "Validation | annual returns")):
        years = [r for r in rows if r["strategy"] == "dip" and r["period_kind"] == "year"]
        values = [float(r["total_return"]) for r in years]
        baseline = [medians[r["period"]] if medians is not None else
                    float(quantiles(c["total_return"] for c in val_controls if c["period_kind"] == "year" and c["period"] == r["period"])["p50"])
                    for r in years]
        ax.bar(range(len(years)), values, color=[INK if v>=0 else RED for v in values], width=.65, label="Dip rule")
        ax.plot(range(len(years)), baseline, color=TEAL, marker="o", markersize=3, lw=1, label="Control median")
        ax.axhline(0, color=MUTED, lw=.6)
        ax.set_xticks(range(len(years)), [r["period"] for r in years], rotation=45)
        ax.set_title(label, loc="left", pad=10)
        style_axis(ax)
        ax.margins(y=.28)
        if ax is axes[0]:
            ax.legend(frameon=False, fontsize=8, ncols=2, loc="upper right", bbox_to_anchor=(1, 1.22))
    save("stability", fig)

    fig, axes = plt.subplots(1, 2, figsize=(6.8, 3.4), layout="constrained")
    for ax, summary, label in ((axes[0], dev, "Development"), (axes[1], val, "Validation")):
        fees = [float(r["cost_bps_per_side"]) for r in summary["scenarios"] if r["strategy"] == "dip"]
        returns = [float(r["total_return"]) for r in summary["scenarios"] if r["strategy"] == "dip"]
        ax.plot(fees, returns, color=INK, lw=1.6, marker="o", markersize=6)
        ax.axhline(0, color=MUTED, lw=.8)
        ax.axvline(float(summary["primary_cost_bps_per_side"] if "primary_cost_bps_per_side" in summary else summary["execution"]["primary_cost_bps_per_side"]), color=TEAL, linestyle="--", lw=1)
        ax.set_xticks(fees)
        ax.set_xlabel("Cost per side | basis points")
        ax.set_title(label, loc="left", pad=12)
        style_axis(ax)
        ax.margins(x=.15, y=.25)
    save("costs", fig)
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 3.2), layout="constrained")
    for ax, period, label in ((axes[0], "development", "Development"), (axes[1], "validation", "Validation")):
        records = [r for r in facts["uncertainty"]["results"] if r["period"] == period]
        for index, row in enumerate(records):
            color = INK if row["primary"] else MUTED
            ax.hlines(index, row["lower_bps_per_session"], row["upper_bps_per_session"], color=color, lw=2 if row["primary"] else 1)
            ax.scatter(row["point_bps_per_session"], index, color=color, s=35 if row["primary"] else 18, zorder=3)
        ax.axvline(0, color=RED, linestyle="--", lw=1)
        ax.set_yticks(range(len(records)), [str(r["mean_block_sessions"])+( " (primary)" if r["primary"] else "") for r in records])
        ax.set_ylim(-.65, len(records)-.35)
        ax.invert_yaxis()
        ax.set_title(label, loc="left", pad=12)
        ax.set_xlabel("Log-growth difference | bps per session")
        ax.set_ylabel("Mean block length | sessions")
        style_axis(ax, percent=False)
        ax.grid(False, axis="y")
        ax.grid(True, axis="x", color=LINE, lw=.6)
    save("uncertainty", fig)
    family = facts["family"]
    config = family["config"]
    for metric, label in (("contrast_pp", "Dip minus matched-control median | percentage points"),
                          ("net_return", "Net cumulative return | percent")):
        fig, axes = plt.subplots(2,3,figsize=(6.8,5.1),layout="constrained")
        values = [abs(float(r[metric]) * (100 if metric=="net_return" else 1)) for r in family["results"] if r[metric] is not None]
        bound = max(values) or 1
        for i,period in enumerate(config["periods"]):
            for j,lookback in enumerate(config["lookback_sessions"]):
                ax=axes[i,j]
                cells=[r for r in family["results"] if r["period"]==period and r["lookback_sessions"]==lookback]
                grid=[[next(r[metric] for r in cells if r["threshold_sigma"]==threshold and r["holding_open_intervals"]==holding)
                       for holding in config["holding_open_intervals"]] for threshold in config["threshold_sigma"]]
                import numpy as np
                array=np.array([[np.nan if v is None else float(v)*(100 if metric=="net_return" else 1) for v in row] for row in grid])
                mesh=ax.imshow(array,cmap="RdBu",vmin=-bound,vmax=bound,aspect="equal")
                for y in range(3):
                    for x in range(3):
                        v=array[y,x]
                        ax.text(x,y,"N/A" if np.isnan(v) else (f"{v:+.2f}" if abs(v)<.1 else f"{v:+.1f}"),ha="center",va="center",fontsize=8,
                                color="white" if not np.isnan(v) and abs(v)>.55*bound else INK)
                ax.set_xticks(range(3),config["holding_open_intervals"])
                ax.set_yticks(range(3),config["threshold_sigma"])
                ax.tick_params(length=0,labelsize=8)
                ax.set_xlabel("Holding sessions",fontsize=8)
                ax.set_ylabel("Threshold (sigma)",fontsize=8)
                ax.set_title(f"{period.title()} | L={lookback}",fontsize=9,loc="left")
                if lookback==20:
                    from matplotlib.patches import Rectangle
                    ax.add_patch(Rectangle((.5,.5),1,1,fill=False,edgecolor="#E6B34A",lw=2.2))
        fig.colorbar(mesh,ax=axes.ravel().tolist(),shrink=.8,label=label,pad=.02)
        save("family_"+metric,fig)
    return figures
def generate_report(root):
    facts = collect_facts(root)
    output = root / "outputs/report"
    figures = make_figures(root, output / "figures", facts)
    fonts = Path(matplotlib.get_data_path()) / "fonts/ttf"
    for name, filename in (("AuditSans", "DejaVuSans.ttf"), ("AuditBold", "DejaVuSans-Bold.ttf"),
                           ("AuditSerif", "DejaVuSerif.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
    pdfmetrics.registerFontFamily("AuditSans", normal="AuditSans", bold="AuditBold")
    styles = dict(
        body=ParagraphStyle("body", fontName="AuditSans", fontSize=9.4, leading=14, textColor=colors.HexColor(INK), spaceAfter=8),
        small=ParagraphStyle("small", fontName="AuditSans", fontSize=8, leading=11.5, textColor=colors.HexColor(MUTED), spaceAfter=6),
        title=ParagraphStyle("title", fontName="AuditSerif", fontSize=32, leading=37, textColor=colors.HexColor(INK), spaceAfter=13),
        h=ParagraphStyle("h", fontName="AuditBold", fontSize=22, leading=28, textColor=colors.HexColor(INK), spaceAfter=12),
        sub=ParagraphStyle("sub", fontName="AuditBold", fontSize=12, leading=17, textColor=colors.HexColor(INK), spaceAfter=8),
        kicker=ParagraphStyle("kicker", fontName="AuditBold", fontSize=8.2, leading=13, textColor=colors.HexColor(TEAL), spaceAfter=9),
    )
    P = lambda text, style="body": Paragraph(text, styles[style])
    story = []
    def add(text, style="body"):
        story.append(P(text, style))
    def gap(height=3):
        story.append(Spacer(1, height * mm))
    def table(headers, rows, widths=None, compact=False):
        cell_style = ParagraphStyle("table_cell", parent=styles["small"], fontSize=8.5, leading=12,
                                    textColor=colors.HexColor(INK))
        header_style = ParagraphStyle("table_header", parent=cell_style, fontName="AuditBold")
        contents = [[Paragraph(escape(str(v)), header_style if i == 0 else cell_style) for v in row]
                    for i, row in enumerate([headers] + rows)]
        t = Table(contents, colWidths=widths or [WIDTH/len(headers)]*len(headers), hAlign="LEFT", repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor(PALE)),
                               ("LINEBELOW", (0,0), (-1,0), .7, colors.HexColor(LINE)),
                               ("LINEBELOW", (0,1), (-1,-1), .35, colors.HexColor(LINE)),
                               ("VALIGN", (0,0), (-1,-1), "TOP"),
                               ("LEFTPADDING", (0,0), (-1,-1), 8), ("RIGHTPADDING", (0,0), (-1,-1), 8),
                               ("TOPPADDING", (0,0), (-1,-1), 4 if compact else 7), ("BOTTOMPADDING", (0,0), (-1,-1), 3 if compact else 6)]))
        story.append(t)
        gap(3)
    def image(name, height):
        story.append(Image(str(figures[name]), width=WIDTH, height=height*mm))
    def chapter(number, label, title, subtitle):
        if number > 1:
            story.append(PageBreak())
        add(f"{number:02d} / {label.upper()}", "kicker")
        add(title, "h")
        add(subtitle)
    def band(text, favorable=False):
        style = ParagraphStyle("band", parent=styles["sub"], textColor=colors.HexColor(TEAL if favorable else RED), spaceAfter=0)
        t = Table([[Paragraph(text, style)]], colWidths=[WIDTH])
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#EDF5F1" if favorable else "#F8EFED")),
                               ("LEFTPADDING",(0,0),(-1,-1),12), ("TOPPADDING",(0,0),(-1,-1),11),
                               ("BOTTOMPADDING",(0,0),(-1,-1),11)]))
        story.append(t)
        gap(4)

    dev, val, control = facts["development"], facts["validation"], facts["development_controls"]
    diagnosis = read_json(root / "outputs/diagnostics/summary.json")
    h = facts["headline"]
    positive = h["classification"] == "PROMISING_MORE_RESEARCH"
    decision = "PROMISING, REQUIRES MORE RESEARCH" if positive else "NOT SUPPORTED BY THE VALIDATION SCREEN" if h["classification"] == "NOT_SUPPORTED_BY_VALIDATION_SCREEN" else "INCONCLUSIVE UNDER THE FROZEN SCREEN"

    add("INDEPENDENT QUANTITATIVE RESEARCH / SPY / DAILY DATA", "kicker")
    add("Buying the Dip:<br/>Does Timing Add Value?", "title")
    add("A fixed-rule test on daily SPY data, 2000-2021.")
    band(decision, positive)
    cards = []
    for value, label in ((h["validation_return"], "Dip net return"), (h["control_median"], "Random-entry median"),
                         (h["contrast_pp"], "Dip minus control median")):
        cards.append(Paragraph(f'<font size="23" color="{INK}">{escape(value)}</font><br/><font size="8" color="{MUTED}">{label}</font>',
                               ParagraphStyle("card", fontName="AuditBold", leading=23)))
    t = Table([cards], colWidths=[WIDTH/3]*3)
    t.setStyle(TableStyle([("TOPPADDING",(0,0),(-1,-1),10), ("BOTTOMPADDING",(0,0),(-1,-1),15)]))
    story.append(t)
    add(f"Validation: 2016-2021 | {h['trades']} completed trades | 5 bps per side | {val['controls_count']} random calendars", "small")
    image("headline", 70)
    add("Separate historical windows; cumulative returns are not annualized. Random controls match trade counts and holding intervals, not risk or regimes.", "small")
    add("Conclusion", "sub")
    add("The fixed rule fails the validation screen. Its advantage over random-entry controls in development did not persist in 2016-2021." if not positive else
        "Retain the fixed specification for further research. A positive descriptive screen does not establish statistical significance or support deployment.")
    add("The primary rule has not been retuned. The reserved 2022-2025 sample has not been acquired.", "small")

    chapter(2, "Testable hypothesis", "Trading rule",
            "Question: does entering after an unusually negative day add value beyond entering without that price signal?")
    table(["Component", "Fixed primary specification"], [
        ["Instrument / direction", "SPY / long only / one position / no leverage"],
        ["Daily signal return", "Close-to-close return including the ex-date cash dividend"],
        ["Volatility reference", "Sample standard deviation of the previous 20 returns; exclude the signal day"],
        ["Trigger", "Daily return <= -2 times the prior daily volatility; zero-volatility windows do not trigger"],
        ["Entry / exit", "Next session open / exit five open-to-open intervals after entry"],
        ["Position overlap", "Ignore new signals while invested; do not extend the exit"],
        ["Allocation", "All available cash, fractional shares; cash earns zero"],
        ["Validation tail", "Stop new entries that cannot finish the full holding horizon before the fixed end"],
    ], [45*mm,129*mm])
    gap(3)
    add("Signal construction", "sub")
    add("r[t] = (close[t] + dividend[t]) / close[t-1] - 1<br/>signal[t] = r[t] &lt;= -2 x stdev(r[t-20], ..., r[t-1])")
    add("A negative volatility-scaled return, not a mean-centered z-score. Provider adjusted close is not used to create the signal.", "small")
    add("Possible explanations", "sub")
    add("Temporary selling pressure could reverse. Alternatively, a decline may reflect new information or compensation for risk. This price study does not identify which mechanism causes subsequent returns.")
    add("The signal is evaluated only after the close; no same-close execution is assumed. Dividend dates follow vendor history and are not a point-in-time corporate-action archive.", "small")

    chapter(3, "Data and design", "Data and temporal split",
            "Calendar cutoffs and the primary specification were recorded before examining temporal-validation performance.")
    table(["Stage", "Window", "Role / access"], [
        ["Development", "2000-2015", "Exploratory signal, accounting and control diagnostics"],
        ["Temporal validation", "2016-2021", "Fixed rules; results now observed and preserved"],
        ["Reserved final sample", "2022-2025", "Not acquired or evaluated"],
    ], [36*mm,33*mm,105*mm])
    table(["Data check", "Recorded result"], [
        ["Source / sampling", "Yahoo Finance public chart endpoint / daily SPY"],
        ["Snapshot coverage", "2000-01-03 through 2021-12-31"],
        ["Session membership", f"{facts['audit']['observed_sessions']:,} sessions; no missing or extra dates versus pinned XNYS model"],
        ["Integrity", "SHA-256 identity, strictly ordered dates, finite positive prices and OHLC checks"],
        ["Price convention", "Split-adjusted OHLC; provider-adjusted close retained separately"],
        ["Corporate actions", "Cash dividends explicit; split-event accounting is unsupported and rejected"],
    ], [45*mm,129*mm])
    add("Validation boundaries", "sub")
    add("Start flat. Use 21 prior sessions only for return warmup. First eligible entry is the second validation session. Do not borrow 2022 prices to finish trades. Carry positions continuously across year boundaries.")
    add("Configuration and first-observation records", "sub")
    add("Configuration and data hashes are checked before execution. The original pre-execution freeze is retained; the first observed validation result is recorded separately and discrepancies on rerun are errors.")
    add("Retrospective temporal validation is not a prospective experiment. The session audit checks a versioned calendar model, not official exchange certification, price accuracy or executable opening fills.", "small")

    chapter(4, "Portfolio paths", "Equity and drawdown",
            "Primary cost assumption: 5 bps on each entry and exit. Both strategies start from the same capital and evaluation dates within each window.")
    image("paths", 183)
    add("Buy and hold is a descriptive reference. It spends substantially more time invested and is not exposure- or risk-matched. Daily-close drawdown misses intraday extremes. Dividends are credited to cash without intraposition reinvestment.", "small")

    chapter(5, "Random-entry reference", "Random-entry controls",
            f"{val['controls_count']} calendars per window, fixed seed {control['config']['seed']}. All calendar outcomes are included.")
    image("controls", 106)
    table(["At 5 bps per side", "Development", "Validation"], [
        ["Dip net return", pct(scenario(dev)["total_return"]), h["validation_return"]],
        ["Random-entry median", pct(control["control_return_quantiles_nearest_rank"]["p50"]), h["control_median"]],
        ["Controls strictly below dip", pct(control["fraction_controls_strictly_below_dip"]), pct(val["fraction_controls_strictly_below_dip"])],
        ["Trades per calendar", control["matched_trades"], h["trades"]],
    ], [72*mm,51*mm,51*mm])
    add("Matched: trade count, holding intervals, one-position constraint, evaluation window and cost rate. Unmatched: volatility, market regimes, calendar-day exposure and dollar turnover.")
    add("The draw counts are conditioned on the observed strategy. These are retrospective reference calendars, not live policies. The fraction below dip is not a p-value or a probability of future outperformance.", "small")

    chapter(6, "Stability and composition", "Returns by year and period",
            "All calendar years are shown. Positions and capital carry over year boundaries; the portfolio is not restarted for each bar.")
    image("stability", 110)
    block_rows = [[c["period"], pct(c["dip"]["total_return"]), pct(c["control_quantiles"]["total_return"]["p50"])]
                  for c in diagnosis["comparisons"] if c["period_kind"] == "block"]
    table(["Development block", "Dip return", "Control median"], block_rows, [72*mm,51*mm,51*mm])
    table(["Mean daily volatility known before entry", "Dip", "Control median"], [
        ["Development", pct(control["dip_mean_entry_daily_volatility"]), pct(diagnosis["entry_risk"]["control_mean_entry_daily_volatility_quantiles"]["p50"])],
        ["Validation", pct(val["dip_mean_entry_daily_volatility"]), pct(val["control_mean_entry_daily_volatility_quantiles"]["p50"])],
    ], [102*mm,36*mm,36*mm])
    add("Calendar blocks are not identified economic regimes. Entry volatility is descriptive, not a matching rule. Overlapping annual/block summaries are not independent tests, and comparable average volatility would not establish equal risk.", "small")

    chapter(7, "Execution sensitivity", "Returns after trading costs",
            "The primary cost assumption is illustrative. It is not fitted to a broker, order size or historical spread series.")
    image("costs", 90)
    table(["Cost per side", "Development dip", "Validation dip"],
          [[f"{row['cost_bps_per_side']} bps", pct(row["total_return"]),
            pct(scenario(val, fee=row["cost_bps_per_side"])["total_return"])]
           for row in dev["scenarios"] if row["strategy"] == "dip"], [72*mm,51*mm,51*mm])
    add("Accounting assumptions", "sub")
    add("Buy shares using open x (1 + cost); sell at open x (1 - cost). Cash is not remunerated. A dividend belongs to shares held before the ex-date open: buying that morning receives none, selling that morning retains entitlement.")
    add("Dividends are assumed available as cash on the ex-date rather than the payment date. Fractional shares and high-precision arithmetic avoid broker rounding. These are modeling simplifications, not a production execution model.")
    add("Development liquidates pending positions at its final close. Validation uses the predeclared no-late-entry cutoff instead. No spread history, capacity, market impact or financing model is claimed.", "small")

    chapter(8, "Sampling uncertainty", "Uncertainty in relative log growth",
            "This analysis was added after validation results were observed. The original screen is unchanged.")
    add("Estimand: mean daily net log growth of the dip minus the average log growth of the 500 fixed control portfolios. This is not the median cumulative-return contrast used on page 1, an investable portfolio return, or risk-adjusted alpha.")
    image("uncertainty", 76)
    u = facts["uncertainty"]
    rows = [[row["period"].title(), str(row["mean_block_sessions"])+( " (primary)" if row["primary"] else ""),
             f"{row['point_bps_per_session']:+.3f}",
             f"[{row['lower_bps_per_session']:+.3f}, {row['upper_bps_per_session']:+.3f}]"] for row in u["results"]]
    table(["Window", "Mean block", "Estimate", "Approx. 95% interval"], rows, [36*mm,35*mm,30*mm,73*mm], compact=True)
    add("All estimates and interval endpoints are basis points of log growth per observed session. 5,000 stationary-bootstrap resamples; paired dates, circular blocks, geometric lengths. Primary mean block: 20 sessions; sensitivity: 5 and 60.", "small")
    add("Assumptions and limits", "sub")
    add("Intervals are approximate under weak-dependence/stationarity assumptions; financial regime changes can invalidate coverage. They condition on the realized portfolios and calendar ensemble, without rerunning trading on new price paths. No parameter-selection or ensemble Monte Carlo uncertainty is included.", "small")
    add("A zero-containing interval does not prove no effect. Excluding zero is not confirmatory evidence after observing the study's results. The original validation classification remains unchanged.", "small")
    add('Method: Politis and Romano (1994), <link href="https://doi.org/10.1080/01621459.1994.10476870" color="'+TEAL+'">The Stationary Bootstrap</link>. Full specification and provenance: research/uncertainty_rules.md and outputs/uncertainty/.', "small")

    chapter(9, "Parameter neighborhood / reference contrast", "Parameter sensitivity",
            "All 27 recorded combinations are evaluated in development and validation. Both periods had already been observed; the primary rule is unchanged.")
    image("family_contrast_pp", 128)
    add("Columns within each map: holding horizon. Rows: negative-return threshold. Panels: volatility lookback L. Gold outline: original 20 / 2 / 5 rule. One symmetric color scale across both windows; values are percentage points.", "small")
    counts = facts["family"]["positive_counts"]
    table(["Window", "Positive contrast", "Positive net return"],
          [[p.title(), str(counts[p]["contrast"])+" / 27", str(counts[p]["net_return"])+" / 27"] for p in ("development","validation")],
          [64*mm,55*mm,55*mm], compact=True)
    add("Each cell uses 500 seeded calendars matched to its trade count and nominal holding horizon. Contrast = dip net cumulative return minus nearest-rank control median, at 5 bps per side. References are not risk/regime matched. Cells share data and are not independent tests.", "small")
    add("The family was specified after observing validation. Positive cells do not establish an edge; no replacement rule is selected. Full metrics, control draws and entry indices are exported.", "small")

    chapter(10, "Parameter neighborhood / net outcomes", "Returns across parameter sets",
            "Net cumulative returns for the same 27 combinations, at 5 bps per side.")
    image("family_net_return", 128)
    add("Net cumulative returns; separate historical windows, not annualized or risk matched. Gold outline: original rule. All combinations are shown.", "small")
    family_rows = facts["family"]["results"]
    table(["Window", "Trade count range", "Close drawdown range", "Terminal exits"],
          [[p.title(), f"{min(r['trades'] for r in family_rows if r['period']==p)}-{max(r['trades'] for r in family_rows if r['period']==p)}",
            f"{min(float(r['max_close_drawdown']) for r in family_rows if r['period']==p):.1%} to {max(float(r['max_close_drawdown']) for r in family_rows if r['period']==p):.1%}",
            str(sum(r['terminal_liquidations'] for r in family_rows if r['period']==p))] for p in ("development","validation")],
          [39*mm,43*mm,58*mm,34*mm], compact=True)
    add("Development starts after each lookback's warmup and retains the original terminal-close policy; any truncated trades are recorded and are not duration-matched by full-horizon controls. Validation starts flat after warmup and excludes entries unable to complete their horizon. Dates and per-cell drawdown/activity are in metrics.csv.", "small")
    add("No replacement parameter set, no multiple-testing-adjusted inference, and no access to 2022-2025. Specification: research/parameter_family_rules.md. Detailed artifacts: outputs/parameter_family/.", "small")

    chapter(11, "Decision and reproduction", "Conclusion and reproducibility",
            "The fixed strategy fails its descriptive validation screen. Later uncertainty and parameter analyses do not change that result." if not positive else
            "The fixed strategy clears its descriptive screen, while statistical evidence and risk matching remain unresolved.")
    band(decision, positive)
    add("Interpretation", "sub")
    add("For this specification, dataset and cost model, the temporal-validation result does not justify advancing toward deployment. It does not prove that every dip strategy fails or that the market has no reversal effect." if not positive else
        "Further research only. A descriptive screen cannot establish an exploitable risk-adjusted edge or justify deployment.")
    add("One command after environment setup", "sub")
    add('<font face="Courier">python3 -m spy_backtest_audit</font>')
    table(["Reproduction anchor", "Recorded identity"], [
        ["Input snapshot SHA-256", val["snapshot_sha256"][:24] + "..."],
        ["Validation method freeze SHA-256", val["freeze_sha256"][:24] + "..."],
        ["Calendar model", "XNYS / exchange_calendars " + facts["audit"]["packages"]["exchange_calendars"]],
        ["Python / seed", val["python"] + " / " + str(val["control_seed"])],
        ["Evidence files", "Data manifest, frozen configurations, all calendars, trade ledgers, daily equity and first-observation record"],
    ], [65*mm,109*mm])
    add("Limits and remaining work", "sub")
    add("Approximate post-observation intervals are conditional on fixed portfolios and are not selection-adjusted. No formal hypothesis test, factor-adjusted alpha or risk-matched control. The final 2022-2025 period is unacquired. Exact reproduction needs the included archived snapshot and pinned environment; vendor revisions may change fresh downloads.", "small")
    add("Sources and method references", "sub")
    add('Market data: Yahoo Finance public chart API (acquisition URL and hashes in the manifest). Adjustment conventions: <link href="https://ranaroussi.github.io/yfinance/advanced/price_adjustment.html" color="'+TEAL+'">yfinance documentation</link>. Calendar: <link href="https://github.com/gerrymanoim/exchange_calendars" color="'+TEAL+'">exchange_calendars</link>. Full trading, control and screening rules are versioned in research/. This is an independent portfolio study, not prior client work.', "small")
    def frame(c, doc):
        c.saveState()
        c.setFillColor(colors.HexColor(INK))
        c.setFont("AuditBold", 8.5)
        c.drawString(18*mm, A4[1]-13*mm, "SPY BACKTEST AUDIT")
        c.setFont("AuditSans", 7.2)
        c.setFillColor(colors.HexColor(MUTED))
        c.drawRightString(A4[0]-18*mm, A4[1]-13*mm, "INDEPENDENT RESEARCH / EQUITY MEAN REVERSION")
        c.setStrokeColor(colors.HexColor(LINE))
        c.line(18*mm, 16*mm, A4[0]-18*mm, 16*mm)
        c.setFont("AuditSans", 7)
        c.drawString(18*mm, 11*mm, "Frozen temporal validation | No post-validation retuning")
        c.drawRightString(A4[0]-18*mm, 11*mm, f"{doc.page:02d} / 11")
        c.restoreState()

    pdf = output / "spy-backtest-audit-research.pdf"
    document = SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
                                 topMargin=25*mm, bottomMargin=23*mm, invariant=1,
                                 title="Buying the Dip: Does Timing Add Value?", author="SPY Backtest Audit / Independent research")
    document.build(story, onFirstPage=frame, onLaterPages=frame, canvasmaker=partial(canvas.Canvas, invariant=1))
    from pypdf import PdfReader
    reader = PdfReader(pdf)
    if len(reader.pages) != 11:
        raise ValueError(f"Report layout changed: expected 11 pages, found {len(reader.pages)}")
    first_page = reader.pages[0].extract_text()
    if any(str(h[key]) not in first_page for key in ("validation_return", "control_median", "contrast_pp")):
        raise ValueError("PDF headline numbers do not match the computed facts")
    input_paths = [p for directory in ("backtest", "controls", "diagnostics", "validation", "data", "uncertainty", "parameter_family")
                   for p in sorted((root / "outputs" / directory).glob("*")) if p.is_file()]
    facts["report_provenance"] = dict(inputs={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in input_paths},
                                     packages={name:version(name) for name in ("matplotlib", "reportlab", "pillow")},
                                     pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                                     report_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output / "report_facts.json").write_text(json.dumps(facts, indent=2) + "\n", encoding="utf-8")
    public_report = root / "reports/spy-backtest-audit.pdf"
    public_report.parent.mkdir(parents=True, exist_ok=True)
    public_report.write_bytes(pdf.read_bytes())
    return pdf
