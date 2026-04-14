"""Core update logic — orchestrates all sync pipelines, rollup, and sorting."""

from datetime import datetime, timezone

from lib.excel_io import (
    get_tracker_rows, write_tracker_cell, write_tracker_range,
    read_used_range,
    TR_GENERAL, TR_AGE, TRACKER_SHEET,
)
from lib.state import set_email_watermark, set_text_watermark
from pipelines import email_pipeline, text_pipeline, linkedin_pipeline


def _format_age(dt: datetime) -> str:
    """Format a timestamp as age string: '14h' or '4d'."""
    now = datetime.now(timezone.utc)
    delta = now - dt
    hours = delta.total_seconds() / 3600

    if hours <= 72:
        return f"{int(hours)}h"
    else:
        days = int(hours / 24)
        return f"{days}d"


def _rollup_and_sort(
    email_results: dict[str, tuple[str, datetime]],
    text_results: dict[str, tuple[str, datetime]],
    linkedin_results: dict[str, tuple[str, datetime]],
) -> None:
    """Calculate General Status + Age from pipeline results, then sort rows."""
    rows = get_tracker_rows()

    # Build per-contact event lists from all pipelines
    for row_data in rows:
        # Never overwrite a user-set "Done" status
        if str(row_data.get("general_status") or "").strip().lower() == "done":
            continue

        events = []  # list of (status_category, timestamp)

        # Email events
        email = row_data["email"]
        if email and email in email_results:
            status, ts = email_results[email]
            if status == "Replied":
                events.append(("Reply", ts))
            elif status == "Sent":
                events.append(("Sent", ts))

        # Text events — keyed by phone
        phone = row_data["phone"]
        if phone:
            from lib.phone import normalize_phone
            norm_phone = normalize_phone(phone)
            if norm_phone in text_results:
                status, ts = text_results[norm_phone]
                if status == "Text Received":
                    events.append(("Reply", ts))
                elif status == "Text Sent":
                    events.append(("Sent", ts))

        # LinkedIn events — keyed by name
        name = row_data["name"]
        if name in linkedin_results:
            status, ts = linkedin_results[name]
            events.append(("Reply", ts))  # LI Received = they contacted you

        if not events:
            continue

        # Most recent event determines General Status
        events.sort(key=lambda e: e[1], reverse=True)
        newest_category, newest_ts = events[0]

        write_tracker_cell(row_data["row"], TR_GENERAL, newest_category)
        write_tracker_cell(row_data["row"], TR_AGE, _format_age(newest_ts))

    # Sort: Reply rows first (age desc), then Sent rows (age asc)
    _sort_tracker()


def _sort_tracker() -> None:
    """Sort tracker rows in-place: Reply (oldest first) above Sent (newest first).

    Reads the full sheet once, sorts in memory, writes back once.
    """
    # Read the full used range (header + data) in a single API call
    all_values = read_used_range(TRACKER_SHEET)
    if len(all_values) < 2:
        return

    header = all_values[0]
    data_rows = all_values[1:]

    # Filter out empty rows (no name in column A)
    non_empty = [row for row in data_rows if row[0]]
    empty = [row for row in data_rows if not row[0]]

    if not non_empty:
        return

    # Column indices in the values array (0-based)
    gen_col = TR_GENERAL - 1  # B = index 1
    age_col = TR_AGE - 1      # D = index 3

    def sort_key(row):
        # Pad row if needed
        while len(row) <= max(gen_col, age_col):
            row.append(None)

        gen_status = str(row[gen_col] or "").strip()
        age_str = str(row[age_col] or "").strip()

        # Parse age to hours for sorting
        age_hours = 0
        if age_str.endswith("h"):
            try:
                age_hours = int(age_str[:-1])
            except ValueError:
                pass
        elif age_str.endswith("d"):
            try:
                age_hours = int(age_str[:-1]) * 24
            except ValueError:
                pass

        if gen_status == "Reply":
            return (0, -age_hours)
        elif gen_status == "Sent":
            return (1, age_hours)
        elif gen_status.lower() == "done":
            return (3, 0)
        else:
            return (2, 0)

    non_empty.sort(key=sort_key)

    # Combine sorted non-empty + empty rows
    sorted_data = non_empty + empty

    # Ensure all rows have the same width as the header
    ncols = len(header)
    for row in sorted_data:
        while len(row) < ncols:
            row.append("")

    # Write the entire data block back in one API call (row 2 onward)
    end_row = len(sorted_data) + 1  # +1 because data starts at row 2
    write_tracker_range(2, end_row, sorted_data)


def run_update() -> None:
    """Run the full sync pipeline: email → text → LinkedIn → rollup + sort.

    Watermarks are only advanced after the rollup writes succeed, preventing
    messages from being permanently skipped if a write fails.
    """
    print("Starting outreach update...\n")

    text_new_watermark = None

    print("[1/4] Email pipeline")
    try:
        email_results = email_pipeline.run()
    except Exception as e:
        print(f"  [email] ERROR: {e}")
        email_results = {}

    print("\n[2/4] Text pipeline")
    try:
        text_results, text_new_watermark = text_pipeline.run()
    except Exception as e:
        print(f"  [text] ERROR: {e}")
        text_results = {}

    print("\n[3/4] LinkedIn pipeline")
    try:
        linkedin_results = linkedin_pipeline.run()
    except Exception as e:
        print(f"  [linkedin] ERROR: {e}")
        linkedin_results = {}

    print("\n[4/4] Rollup + Sort")
    try:
        _rollup_and_sort(email_results, text_results, linkedin_results)
        print("  Rollup and sorting complete.")

        # Advance watermarks ONLY after successful rollup write
        if email_results:
            set_email_watermark()
            print("  Email watermark advanced.")
        if text_new_watermark is not None:
            set_text_watermark(text_new_watermark)
            print("  Text watermark advanced.")
    except Exception as e:
        print(f"  [rollup] ERROR: {e}")
        print("  Watermarks NOT advanced — will retry these messages next run.")

    print("\nUpdate complete.")
