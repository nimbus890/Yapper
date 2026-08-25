from __future__ import annotations

import json
import statistics

from aura_flow.config import DATA_DIR


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def main() -> int:
    path = DATA_DIR / "metrics.jsonl"
    if not path.exists():
        print("No metrics have been recorded yet.")
        return 0
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except ValueError:
            continue
    successful = [record for record in records if record.get("result") in {"inserted", "clipboard_fallback"}]
    print(f"Dictations: {len(records)} total, {len(successful)} transcribed")
    for field in ("queue_wait_ms", "asr_ms", "format_ms", "insert_ms", "total_ms"):
        values = [float(record.get(field, 0.0)) for record in successful]
        if values:
            print(
                f"{field:14} mean={statistics.fmean(values):8.1f}ms "
                f"p50={percentile(values, 0.50):8.1f}ms p95={percentile(values, 0.95):8.1f}ms"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

