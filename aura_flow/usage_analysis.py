from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
import re


WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")
FILLERS = {
    "uh", "um", "erm", "hmm", "ah", "okay", "ok", "yeah", "well",
    "basically", "literally", "actually",
}
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "been", "but",
    "by", "can", "do", "for", "from", "had", "has", "have", "he", "her",
    "here", "him", "his", "how", "i", "if", "in", "into", "is", "it",
    "its", "just", "me", "my", "not", "of", "on", "or", "our", "she",
    "so", "that", "the", "their", "them", "then", "there", "they", "this",
    "to", "up", "was", "we", "were", "what", "when", "where", "which",
    "who", "why", "will", "with", "would", "you", "your", "like", "yeah",
    "okay", "well", "really", "very", "gonna", "wanna",
    "number", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "first", "second", "third", "fourth", "fifth", "version",
    "it's", "i'm", "i've", "i'll", "i'd", "that's", "there's", "we're", "we've",
    "we'll", "you're", "you've", "you'll", "they're", "they've", "they'll",
}


def _words(value: object) -> list[str]:
    return [match.group(0).casefold() for match in WORD.finditer(str(value or ""))]


def _longest_streak(days: set) -> int:
    if not days:
        return 0
    longest = current = 1
    for previous, current_day in zip(sorted(days), sorted(days)[1:]):
        if current_day == previous + timedelta(days=1):
            current += 1
            longest = max(longest, current)
        else:
            current = 1
    return longest


def _current_streak(days: set, today=None) -> int:
    if not days:
        return 0
    cursor = today or datetime.now().date()
    if cursor not in days:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def _hour_label(hour: int | None) -> str:
    if hour is None:
        return "—"
    suffix = "AM" if hour < 12 else "PM"
    shown = hour % 12 or 12
    return f"{shown}:00 {suffix}"


def analyze_usage(
    entries: list[dict[str, object]],
    typing_wpm: int = 40,
    now: datetime | None = None,
) -> dict[str, object]:
    """Derive private, deterministic language insights from local history."""

    raw_words: list[str] = []
    final_words: list[str] = []
    lengths: list[int] = []
    active_days = set()
    dated: list[tuple[datetime, dict[str, object], list[str], list[str]]] = []
    app_counter: Counter[str] = Counter()
    hour_counter: Counter[int] = Counter()
    fallback_count = 0
    audio_seconds = 0.0
    longest_entry_id = ""
    longest_words = 0
    for entry in entries:
        current_raw = _words(entry.get("raw", ""))
        current_final = _words(entry.get("final", ""))
        raw_words.extend(current_raw)
        final_words.extend(current_final)
        lengths.append(len(current_final))
        if len(current_final) > longest_words:
            longest_words = len(current_final)
            longest_entry_id = str(entry.get("id", ""))
        app = str(entry.get("app", "")).strip()
        if app:
            app_counter[app] += 1
        fallback_count += bool(entry.get("formatter_fallback", False))
        try:
            audio_seconds += max(0.0, float(entry.get("audio_seconds", 0) or 0))
        except (TypeError, ValueError):
            pass
        try:
            timestamp = float(entry.get("timestamp", 0))
            if timestamp > 0:
                moment = datetime.fromtimestamp(timestamp)
                active_days.add(moment.date())
                dated.append((moment, entry, current_raw, current_final))
                hour_counter[moment.hour] += 1
        except (TypeError, ValueError, OSError):
            pass

    content = Counter(word for word in raw_words if word not in STOPWORDS and len(word) > 2)
    favorite_word, favorite_count = content.most_common(1)[0] if content else ("—", 0)
    top_words = [{"word": word, "count": count} for word, count in content.most_common(3)]
    filler_count = sum(word in FILLERS for word in raw_words)
    reduction = max(0, len(raw_words) - len(final_words))
    reference = now or datetime.now()
    this_week_start = reference - timedelta(days=7)
    previous_week_start = reference - timedelta(days=14)
    this_week = [item for item in dated if item[0] >= this_week_start]
    previous_week = [item for item in dated if previous_week_start <= item[0] < this_week_start]

    def count_final(items) -> int:
        return sum(len(item[3]) for item in items)

    def filler_rate(items) -> float:
        words = [word for item in items for word in item[2]]
        return sum(word in FILLERS for word in words) / max(1, len(words)) * 100

    this_week_words = count_final(this_week)
    previous_week_words = count_final(previous_week)
    week_change = (
        round((this_week_words - previous_week_words) / previous_week_words * 100)
        if previous_week_words
        else (100 if this_week_words else 0)
    )
    current_fillers = filler_rate(this_week)
    prior_fillers = filler_rate(previous_week)
    productive_hour = hour_counter.most_common(1)[0][0] if hour_counter else None
    top_app = app_counter.most_common(1)[0][0] if app_counter else "—"
    if top_app != "—":
        top_app = Path(top_app).stem.replace("-", " ").replace("_", " ").title()
    typing_seconds = len(final_words) / max(1, typing_wpm) * 60
    return {
        "dictations": len(entries),
        "favorite_word": favorite_word,
        "favorite_word_count": favorite_count,
        "average_words": round(sum(lengths) / len(lengths)) if lengths else 0,
        "top_words": top_words,
        "longest_dictation": max(lengths, default=0),
        "longest_entry_id": longest_entry_id,
        "filler_rate": round(filler_count / max(1, len(raw_words)) * 100, 1),
        "filler_trend": round(current_fillers - prior_fillers, 1),
        "cleanup_reduction": round(reduction / max(1, len(raw_words)) * 100, 1),
        "active_days": len(active_days),
        "longest_streak": _longest_streak(active_days),
        "current_streak": _current_streak(active_days, reference.date()),
        "most_productive_hour": _hour_label(productive_hour),
        "most_used_app": top_app,
        "words_this_week": this_week_words,
        "words_previous_week": previous_week_words,
        "week_change_percent": week_change,
        "smart_fallback_rate": round(fallback_count / max(1, len(entries)) * 100, 1),
        "lifetime_time_saved_minutes": max(0, round((typing_seconds - audio_seconds) / 60)),
    }
