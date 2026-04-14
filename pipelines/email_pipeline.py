"""Email sync pipeline — fetches Outlook mail via Microsoft Graph, updates Tracker."""

from datetime import datetime, timezone

import requests

from lib.auth import get_token
from lib.state import get_email_watermark
from lib.excel_io import get_tracker_rows

GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _fetch_messages(token: str, folder: str, since: str | None) -> list[dict]:
    """Fetch messages from a mail folder, optionally filtered by date."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH_BASE}/me/mailFolders/{folder}/messages"
    params = {
        "$select": "from,toRecipients,receivedDateTime,subject",
        "$top": "200",
        "$orderby": "receivedDateTime desc",
    }
    if since:
        # $filter and $orderby together require ConsistencyLevel + $count
        params["$filter"] = f"receivedDateTime ge {since}"
        headers["ConsistencyLevel"] = "eventual"
        params["$count"] = "true"

    all_messages = []
    while url:
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.exceptions.Timeout:
            print(f"    Timeout fetching {folder}")
            break

        if resp.status_code != 200:
            print(f"    Graph API error ({resp.status_code}): {resp.text[:500]}")
            # If filter combo fails, retry without filter and sort client-side
            if since and "$filter" in params:
                print("    Retrying without date filter...")
                params.pop("$filter", None)
                params.pop("$count", None)
                headers.pop("ConsistencyLevel", None)
                continue
            break

        data = resp.json()
        all_messages.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
        params = {}  # nextLink includes params already
    return all_messages


def _build_lookup(messages: list[dict], extract_email_fn) -> dict[str, tuple[datetime, str]]:
    """Build {email_address: (newest_datetime, subject)} from a list of messages."""
    lookup = {}
    for msg in messages:
        addr = extract_email_fn(msg)
        if not addr:
            continue
        addr = addr.lower()
        dt = datetime.fromisoformat(msg["receivedDateTime"].replace("Z", "+00:00"))
        subj = msg.get("subject", "")
        if addr not in lookup or dt > lookup[addr][0]:
            lookup[addr] = (dt, subj)
    return lookup


def _extract_sender(msg: dict) -> str | None:
    """Extract sender email from a message."""
    try:
        return msg["from"]["emailAddress"]["address"]
    except (KeyError, TypeError):
        return None


def _build_sent_lookup(messages: list[dict]) -> dict[str, tuple[datetime, str]]:
    """Build {email_address: (newest_datetime, subject)} from sent messages, capturing all recipients."""
    lookup = {}
    for msg in messages:
        for addr in _extract_recipients(msg):
            addr = addr.lower()
            dt = datetime.fromisoformat(msg["receivedDateTime"].replace("Z", "+00:00"))
            subj = msg.get("subject", "")
            if addr not in lookup or dt > lookup[addr][0]:
                lookup[addr] = (dt, subj)
    return lookup


def _extract_recipients(msg: dict) -> list[str]:
    """Extract all recipient emails from a sent message."""
    try:
        return [r["emailAddress"]["address"] for r in msg.get("toRecipients", [])]
    except (KeyError, TypeError):
        return []


def run() -> dict[str, tuple[str, datetime]]:
    """Run the email sync pipeline.

    Returns a dict of {email_address: (status, timestamp)} for use by
    the General Status rollup.
    """
    print("  [email] Authenticating...")
    token = get_token(["Mail.Read"])

    watermark = get_email_watermark()
    print(f"  [email] Watermark: {watermark or 'first run'}")

    print("  [email] Fetching inbox...")
    inbox = _fetch_messages(token, "inbox", watermark)
    print(f"  [email] Fetched {len(inbox)} inbox messages")

    print("  [email] Fetching sent items...")
    sent = _fetch_messages(token, "sentitems", watermark)
    print(f"  [email] Fetched {len(sent)} sent messages")

    recv_map = _build_lookup(inbox, _extract_sender)
    sent_map = _build_sent_lookup(sent)

    # Read tracker rows and match
    rows = get_tracker_rows()
    results = {}

    for row_data in rows:
        email = row_data["email"]
        if not email:
            continue

        recv = recv_map.get(email)
        sent_info = sent_map.get(email)

        status = None
        timestamp = None

        if recv and sent_info:
            if recv[0] >= sent_info[0]:
                status = "Replied"
                timestamp = recv[0]
            else:
                status = "Sent"
                timestamp = sent_info[0]
        elif recv:
            status = "Replied"
            timestamp = recv[0]
        elif sent_info:
            status = "Sent"
            timestamp = sent_info[0]

        if status:
            results[email] = (status, timestamp)
            print(f"  [email] {row_data['name']}: {status}")

    # Watermark is NOT advanced here — the orchestrator advances it
    # after confirming the rollup wrote successfully to the spreadsheet.
    print("  [email] Done.")
    return results
