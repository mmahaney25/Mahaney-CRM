"""Text/SMS sync pipeline — reads macOS chat.db, updates Tracker."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from lib.state import get_text_watermark
from lib.excel_io import get_tracker_rows

CHAT_DB = Path.home() / "Library" / "Messages" / "chat.db"

# Apple Messages stores timestamps as nanoseconds since 2001-01-01
APPLE_EPOCH_OFFSET = 978307200  # seconds between 1970-01-01 and 2001-01-01


from lib.phone import normalize_phone as _normalize_phone


def _apple_ts_to_epoch(apple_ts: int) -> float:
    """Convert Apple Messages timestamp to Unix epoch seconds."""
    # chat.db uses nanoseconds since 2001-01-01 (on modern macOS)
    if apple_ts > 1e15:
        # Nanoseconds
        return (apple_ts / 1e9) + APPLE_EPOCH_OFFSET
    elif apple_ts > 1e12:
        # Microseconds
        return (apple_ts / 1e6) + APPLE_EPOCH_OFFSET
    elif apple_ts > 1e9:
        # Already epoch seconds (shouldn't happen, but handle it)
        return float(apple_ts)
    else:
        # Seconds since Apple epoch
        return float(apple_ts) + APPLE_EPOCH_OFFSET


def _epoch_to_datetime(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _query_messages(phone_numbers: list[str], since_ts: float | None) -> list[dict]:
    """Query chat.db for messages matching the given phone numbers."""
    if not CHAT_DB.exists():
        print(f"  [text] WARNING: chat.db not found at {CHAT_DB}")
        return []

    try:
        conn = sqlite3.connect(f"file:{CHAT_DB}?mode=ro", uri=True)
    except sqlite3.OperationalError as e:
        print(f"  [text] ERROR: Cannot open chat.db: {e}")
        print("  [text] Grant Full Disk Access to your terminal in System Settings → Privacy & Security.")
        return []
    conn.row_factory = sqlite3.Row

    # Build phone number filter
    placeholders = ",".join("?" for _ in phone_numbers)

    where_clause = f"h.id IN ({placeholders})"
    params = list(phone_numbers)

    if since_ts is not None:
        # Convert epoch back to Apple timestamp (nanoseconds)
        apple_since = int((since_ts - APPLE_EPOCH_OFFSET) * 1e9)
        where_clause += " AND m.date > ?"
        params.append(apple_since)

    query = f"""
        SELECT
            h.id AS phone,
            m.is_from_me,
            m.date AS apple_date,
            SUBSTR(m.text, 1, 80) AS preview
        FROM message m
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        JOIN chat_handle_join chj ON chj.chat_id = cmj.chat_id
        JOIN handle h ON h.ROWID = chj.handle_id
        WHERE {where_clause}
        ORDER BY m.date DESC
    """

    try:
        rows = conn.execute(query, params).fetchall()
    except sqlite3.OperationalError as e:
        print(f"  [text] ERROR querying chat.db: {e}")
        rows = []
    finally:
        conn.close()

    return [dict(r) for r in rows]


def run() -> tuple[dict[str, tuple[str, datetime]], float | None]:
    """Run the text sync pipeline.

    Returns (results_dict, newest_message_ts) where:
    - results_dict: {phone_number: (status, timestamp)}
    - newest_message_ts: epoch seconds of the newest message seen, or None
    The caller is responsible for advancing the watermark after a successful write.
    """
    watermark = get_text_watermark()
    print(f"  [text] Watermark: {watermark or 'first run'}")

    # Read phone numbers from spreadsheet
    rows = get_tracker_rows()

    phone_to_rows = {}
    for row_data in rows:
        raw_phone = row_data["phone"]
        if not raw_phone:
            continue
        normalized = _normalize_phone(raw_phone)
        if normalized:
            phone_to_rows[normalized] = row_data

    if not phone_to_rows:
        print("  [text] No phone numbers in spreadsheet. Skipping.")
        return {}, None

    phone_numbers = list(phone_to_rows.keys())
    print(f"  [text] Looking up {len(phone_numbers)} phone numbers in chat.db...")

    messages = _query_messages(phone_numbers, watermark)
    print(f"  [text] Found {len(messages)} messages")

    # Build lookup tables — newest message per phone, split by direction
    recv_map: dict[str, tuple[float, str]] = {}
    sent_map: dict[str, tuple[float, str]] = {}
    newest_ts = watermark or 0.0

    for msg in messages:
        phone = msg["phone"]
        ts = _apple_ts_to_epoch(msg["apple_date"])
        preview = msg["preview"] or ""

        if ts > newest_ts:
            newest_ts = ts

        if msg["is_from_me"]:
            if phone not in sent_map or ts > sent_map[phone][0]:
                sent_map[phone] = (ts, preview)
        else:
            if phone not in recv_map or ts > recv_map[phone][0]:
                recv_map[phone] = (ts, preview)

    # Match and update spreadsheet
    results = {}

    for phone, row_data in phone_to_rows.items():
        recv = recv_map.get(phone)
        sent = sent_map.get(phone)

        status = None
        timestamp = None

        if recv and sent:
            if recv[0] >= sent[0]:
                status = "Text Received"
                timestamp = _epoch_to_datetime(recv[0])
            else:
                status = "Text Sent"
                timestamp = _epoch_to_datetime(sent[0])
        elif recv:
            status = "Text Received"
            timestamp = _epoch_to_datetime(recv[0])
        elif sent:
            status = "Text Sent"
            timestamp = _epoch_to_datetime(sent[0])

        if status:
            results[phone] = (status, timestamp)
            print(f"  [text] {row_data['name']}: {status}")

    # Return the newest timestamp so the orchestrator can advance the watermark
    # after confirming the rollup wrote successfully.
    new_watermark = newest_ts if newest_ts > (watermark or 0.0) else None

    print("  [text] Done.")
    return results, new_watermark
