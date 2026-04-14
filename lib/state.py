"""Watermark state persistence for sync pipelines."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

EMAIL_STATE_PATH = Path(".outreach_state.json")
TEXT_STATE_PATH = Path(".texts_state.json")


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
            print(f"  [state] WARNING: {path.name} contains non-dict data, resetting.", file=sys.stderr)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"  [state] WARNING: {path.name} is corrupted ({e}), resetting.", file=sys.stderr)
    return {}


def save_state(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, default=str))


def get_email_watermark() -> str | None:
    """Return ISO timestamp of last email sync, or None if first run."""
    state = load_state(EMAIL_STATE_PATH)
    return state.get("last_sync")


def set_email_watermark(timestamp: str | None = None) -> None:
    """Save current time (or provided timestamp) as the email watermark."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    save_state(EMAIL_STATE_PATH, {"last_sync": ts})


def get_text_watermark() -> float | None:
    """Return the newest message timestamp (epoch seconds) from last text sync."""
    state = load_state(TEXT_STATE_PATH)
    return state.get("newest_message_ts")


def set_text_watermark(timestamp: float) -> None:
    """Save the newest message timestamp for the text pipeline."""
    save_state(TEXT_STATE_PATH, {"newest_message_ts": timestamp})


def reset_email_watermark() -> None:
    """Clear the email watermark so the next run does a full re-sync."""
    save_state(EMAIL_STATE_PATH, {})
    print("  [state] Email watermark reset — next run will fetch all emails.")


def reset_text_watermark() -> None:
    """Clear the text watermark so the next run does a full re-sync."""
    save_state(TEXT_STATE_PATH, {})
    print("  [state] Text watermark reset — next run will fetch all messages.")
