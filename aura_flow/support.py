from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from html import escape
from pathlib import Path
import tempfile
import zipfile

from .usage_analysis import analyze_usage
from .version import VERSION


SENSITIVE_FRAGMENTS = ("key", "token", "secret", "password", "credential")


def sanitized_settings(config) -> dict[str, object]:
    """Return useful settings while excluding credentials and identifying paths."""
    clean: dict[str, object] = {}
    for key, value in asdict(config).items():
        if any(fragment in key.casefold() for fragment in SENSITIVE_FRAGMENTS):
            continue
        if key in {"model_path", "semantic_model_path", "partial_model_path"}:
            clean[key] = Path(value).name if value else None
        elif key in {
            "feedback_email", "paypal_url", "upi_id", "upi_display_name",
            "feedback_github_url", "feedback_data_form_url",
        }:
            continue
        else:
            clean[key] = value
    return clean


def diagnostics_preview(config, history) -> str:
    entries = history.all_entries()
    analysis = analyze_usage(entries, config.typing_wpm_baseline)
    return (
        f"Version: {VERSION}\n"
        f"Theme: {config.theme_mode}\n"
        f"Model: {config.model_name}\n"
        f"Recording mode: {config.recording_mode}\n"
        f"Stored dictations: {len(entries)}\n"
        f"Smart fallback rate: {analysis['smart_fallback_rate']}%\n"
        "No API keys, clipboard contents, cursor context, or unrelated files are included."
    )


def create_form_data_export(
    config, entries: list[dict[str, object]], destination: Path, scope: str,
) -> Path:
    """Create a safe, readable text export for the private Google Form."""
    destination.mkdir(parents=True, exist_ok=True)
    ordered_entries = list(reversed(entries))
    payload = {
        "format": "yapper-form-data-export",
        "version": VERSION,
        "created_at": datetime.now().astimezone().isoformat(),
        "scope": scope,
        "dictation_count": len(ordered_entries),
        "dictations": ordered_entries,
        "diagnostics": {
            "settings": sanitized_settings(config),
            "usage": analyze_usage(entries, config.typing_wpm_baseline),
        },
        "excluded": [
            "API keys and tokens", "clipboard contents", "cursor context",
            "personal vocabulary, replacements, and snippets", "audio files",
            "unrelated files",
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    if len(encoded) > 10 * 1024 * 1024:
        raise ValueError("This export is larger than the Google Form's 10 MB limit.")
    output = destination / f"yapper-data-{datetime.now():%Y-%m-%d-%H%M%S}.txt"
    output.write_bytes(encoded)
    return output


def create_testing_export(config, history, metrics_path: Path, destination: Path) -> Path:
    """Build a manual, privacy-scoped testing bundle in a user-chosen folder."""
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / f"yapper-testing-data-{datetime.now():%Y-%m-%d}.zip"
    entries = history.all_entries()
    stats = analyze_usage(entries, config.typing_wpm_baseline)
    manifest = {
        "format": "yapper-testing-export",
        "version": VERSION,
        "created_at": datetime.now().astimezone().isoformat(),
        "files": [
            "history.jsonl", "metrics.jsonl", "stats.json",
            "settings-sanitized.json", "report.html", "charts.svg", "manifest.json",
        ],
        "excluded": [
            "API keys and tokens", "clipboard contents", "cursor context",
            "personal vocabulary, replacements, and snippets", "unrelated files",
        ],
    }
    top_words = stats.get("top_words", [])
    maximum = max((int(item["count"]) for item in top_words), default=1)
    bars = "".join(
        f"<text x='20' y='{34 + index * 40}'>{escape(str(item['word']))}</text>"
        f"<rect x='150' y='{18 + index * 40}' width='{360 * int(item['count']) / maximum:.0f}' height='22' rx='7' fill='#78cbae'/>"
        f"<text x='520' y='{34 + index * 40}'>{int(item['count'])}</text>"
        for index, item in enumerate(top_words)
    )
    chart_svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='640' height='180' viewBox='0 0 640 180'>
<rect width='640' height='180' rx='18' fill='#f5f2eb'/><text x='20' y='155' font-family='system-ui' font-size='13' fill='#706d66'>Top meaningful words</text>
<g font-family='system-ui' font-size='14' fill='#292824'>{bars}</g></svg>"""
    report_rows = "".join(
        f"<tr><td>{escape(key.replace('_', ' ').title())}</td><td>{escape(str(value))}</td></tr>"
        for key, value in stats.items() if not isinstance(value, list)
    )
    report = f"""<!doctype html><meta charset='utf-8'>
<title>yapper_ testing report</title>
<style>body{{font:15px system-ui;max-width:840px;margin:48px auto;color:#292824}}
table{{border-collapse:collapse;width:100%}}td{{padding:9px;border-bottom:1px solid #ddd}}
h1{{font-size:32px}}img{{width:100%;max-width:640px}}</style><h1>yapper_ testing report</h1>
<p>Generated locally. This file is only shared if you attach and send the ZIP yourself.</p>
<img src='charts.svg' alt='Top words chart'><table>{report_rows}</table>"""
    with tempfile.TemporaryDirectory(prefix="yapper-export-") as temp_name:
        temp = Path(temp_name)
        (temp / "history.jsonl").write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in reversed(entries)),
            encoding="utf-8",
        )
        metrics = metrics_path.read_text(encoding="utf-8") if metrics_path.exists() else ""
        (temp / "metrics.jsonl").write_text(metrics, encoding="utf-8")
        (temp / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
        (temp / "settings-sanitized.json").write_text(
            json.dumps(sanitized_settings(config), indent=2), encoding="utf-8"
        )
        (temp / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        (temp / "report.html").write_text(report, encoding="utf-8")
        (temp / "charts.svg").write_text(chart_svg, encoding="utf-8")
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in manifest["files"]:
                archive.write(temp / name, name)
    return output
