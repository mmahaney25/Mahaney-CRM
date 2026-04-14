"""LinkedIn sync pipeline — parses LinkedIn notification emails, updates Tracker."""

import re
from datetime import datetime, timezone
from difflib import SequenceMatcher

import requests

from lib.auth import get_token
from lib.excel_io import get_tracker_rows
from lib.state import get_email_watermark

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
LINKEDIN_SENDER = "messages-noreply@linkedin.com"
FUZZY_THRESHOLD = 0.75  # minimum similarity score to accept a name match


def _fetch_linkedin_emails(token: str, since: str | None) -> list[dict]:
    """Fetch LinkedIn notification emails from Outlook inbox."""
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{GRAPH_BASE}/me/messages"

    filter_parts = [f"from/emailAddress/address eq '{LINKEDIN_SENDER}'"]
    if since:
        filter_parts.append(f"receivedDateTime ge {since}")

    params = {
        "$filter": " and ".join(filter_parts),
        "$select": "subject,receivedDateTime",
        "$top": "200",
    }

    all_messages = []
    while url:
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.exceptions.Timeout:
            print("    Timeout fetching LinkedIn notifications")
            break

        if resp.status_code != 200:
            print(f"    Graph API error ({resp.status_code}): {resp.text[:500]}")
            break

        data = resp.json()
        all_messages.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
        params = {}
    return all_messages


def _extract_name_from_subject(subject: str) -> str | None:
    """Extract the contact name from a LinkedIn notification subject."""
    patterns = [
        r"^(.+?) sent you a message",
        r"new message from (.+?)$",
        r"^(.+?) wants to connect",
        r"^(.+?) sent you an invitation",
        r"^(.+?) accepted your invitation",
    ]
    for pattern in patterns:
        match = re.search(pattern, subject, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            if len(name) > 2 and len(name) < 60:
                return name
    return None


def _fuzzy_match(name: str, candidates: list[str]) -> tuple[str | None, float]:
    """Find the best fuzzy match for a name among candidates."""
    name_lower = name.lower()
    best_match = None
    best_score = 0.0

    for candidate in candidates:
        score = SequenceMatcher(None, name_lower, candidate.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = candidate

    if best_score >= FUZZY_THRESHOLD:
        return best_match, best_score
    return None, 0.0


def run() -> dict[str, tuple[str, datetime]]:
    """Run the LinkedIn sync pipeline.

    Returns a dict of {contact_name: (status, timestamp)} for use by
    the General Status rollup.
    """
    print("  [linkedin] Authenticating...")
    token = get_token(["Mail.Read"])

    # Reuse email watermark — LinkedIn emails come from the same inbox
    watermark = get_email_watermark()
    print(f"  [linkedin] Watermark: {watermark or 'first run'}")

    print("  [linkedin] Fetching LinkedIn notifications...")
    emails = _fetch_linkedin_emails(token, watermark)
    print(f"  [linkedin] Found {len(emails)} LinkedIn notifications")

    if not emails:
        print("  [linkedin] No notifications to process.")
        return {}

    # Parse notifications into name → (timestamp) map
    name_map: dict[str, datetime] = {}
    for email in emails:
        subject = email.get("subject", "")
        name = _extract_name_from_subject(subject)
        if not name:
            continue
        dt = datetime.fromisoformat(email["receivedDateTime"].replace("Z", "+00:00"))
        if name not in name_map or dt > name_map[name]:
            name_map[name] = dt

    if not name_map:
        print("  [linkedin] No names extracted from notifications.")
        return {}

    print(f"  [linkedin] Extracted {len(name_map)} unique contact names")

    # Read tracker rows and fuzzy-match
    rows = get_tracker_rows()
    tracker_names = [r["name"] for r in rows]
    results = {}

    for li_name, timestamp in name_map.items():
        matched_name, score = _fuzzy_match(li_name, tracker_names)
        if matched_name:
            for row_data in rows:
                if row_data["name"] == matched_name:
                    results[matched_name] = ("LI Received", timestamp)
                    print(f"  [linkedin] {matched_name}: LI Received (matched '{li_name}', score={score:.2f})")
                    break
        else:
            print(f"  [linkedin] No match for '{li_name}' (best score below {FUZZY_THRESHOLD})")

    print("  [linkedin] Done.")
    return results
