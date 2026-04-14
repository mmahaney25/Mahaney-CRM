"""Send pipeline — sends outreach via email (Graph API) and iMessage (osascript).

Single-row (`send_row`) and bulk (`bulk_send`) entry points.
Bulk defaults to email-only, requires typed `YES` confirmation, paces at 2s
per row, and caps at 50 rows per invocation.
"""

import subprocess
import time

import requests

from lib.auth import get_token
from lib.excel_io import (
    get_outreach_rows, write_outreach_cell,
    OR_MESSAGE, OR_STATUS, OUTREACH_SHEET,
)
from lib.phone import normalize_phone as _normalize_phone
from lib.template_io import load_template

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Hard safety constants — intentionally not configurable from the CLI.
BULK_PACING_SECONDS = 2.0
BULK_BATCH_CAP = 50
BULK_CONFIRM_PHRASE = "YES"  # exact, case-sensitive


# ---------------------------------------------------------------------------
# Channel implementations
# ---------------------------------------------------------------------------

def _render_newlines(message_body: str) -> str:
    """Convert the pipeline's literal `\\n` spacing marker to real newlines."""
    return message_body.replace("\\n", "\n")


def _send_email(token: str, to_address: str, subject: str, message_body: str) -> bool:
    """Send an email via Microsoft Graph API."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "message": {
            "toRecipients": [{"emailAddress": {"address": to_address}}],
            "subject": subject,
            "body": {
                "contentType": "Text",
                "content": _render_newlines(message_body),
            },
        }
    }

    resp = requests.post(
        f"{GRAPH_BASE}/me/sendMail",
        headers=headers,
        json=payload,
    )

    if resp.status_code == 202:
        return True
    print(f"    Email send failed ({resp.status_code}): {resp.text}")
    return False


def _send_imessage(phone: str, message_body: str) -> bool:
    """Send an iMessage via osascript (macOS AppleScript)."""
    phone = _normalize_phone(phone)
    message_body = _render_newlines(message_body)
    escaped = message_body.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        f'tell application "Messages" to send "{escaped}" '
        f'to buddy "{phone}" of (1st account whose service type = iMessage)'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return True
        print(f"    iMessage send failed: {result.stderr.strip()}")
        return False
    except subprocess.TimeoutExpired:
        print("    iMessage send timed out")
        return False


# ---------------------------------------------------------------------------
# Single-row send
# ---------------------------------------------------------------------------

def send_row(row_num: int, *, email_only: bool = True, dry_run: bool = False) -> None:
    """Send outreach for a specific row.

    `email_only` (default True) skips iMessage even if a phone is present —
    the safe default for both single-row and bulk. Pass `email_only=False`
    (or `--with-imessage` on the CLI) to enable dual-channel.
    `dry_run` prints the plan without sending or writing anything.
    """
    rows = get_outreach_rows()
    target = next((r for r in rows if r["row"] == row_num), None)

    if not target:
        print(f"  [send] No data found at row {row_num}")
        return

    email_contact = target["email_contact"]
    messages_contact = target["messages_contact"]

    if not email_contact and not (messages_contact and not email_only):
        print(
            f"  [send] ERROR: row {row_num} has no Email Contact"
            + (" (iMessage disabled by email_only=True)" if messages_contact else "")
            + "."
        )
        return

    # Auto-generate message if Message cell is empty. Rows that already have a
    # message (manually written or previously generated) are sent as-is.
    if not target["message"]:
        if not target["name"]:
            print(f"  [send] ERROR: row {row_num} has no Name — cannot generate.")
            return
        if not target["company"]:
            print(f"  [send] ERROR: row {row_num} has no Company — cannot generate.")
            return

        first_name = str(target["name"]).split()[0]
        company = str(target["company"])

        if dry_run:
            print(
                f"  [send] DRY-RUN row {row_num}: would auto-generate body for "
                f"{first_name}/{company} and send to {email_contact}."
            )
            return

        from pipelines.generate_pipeline import generate_body  # deferred import

        print(f"  [send] Message empty for row {row_num}. Running 4-agent generator...")
        try:
            result = generate_body(first_name=first_name, company=company)
        except Exception as e:
            print(f"  [send] ERROR: generator crashed — {type(e).__name__}: {e}")
            print(f"  [send] NOT sending row {row_num}.")
            return

        if result.action == "ESCALATE" or result.body is None:
            print(f"  [send] Generator ESCALATED at loop {result.loops}: {result.reason}")
            print(f"  [send] NOT sending row {row_num}.")
            return

        write_outreach_cell(row_num, OR_MESSAGE, result.body)
        target["message"] = result.body
        print(f"  [send] Wrote generated body to row {row_num} col F.")

    # Pull the canonical subject fresh from Template.md on every send.
    subject, _ = load_template()

    if dry_run:
        print(
            f"  [send] DRY-RUN row {row_num}: would send to {email_contact} "
            f"with subject={subject!r}."
        )
        return

    print(f"  [send] Sending to {target['name']}...")

    email_ok = None
    imessage_ok = None

    if email_contact:
        print(f"  [send] Sending email to {email_contact}...")
        token = get_token(["Mail.Send"])
        email_ok = _send_email(token, email_contact, subject, target["message"])
        print(f"  [send] Email: {'OK' if email_ok else 'FAILED'}")

    if messages_contact and not email_only:
        print(f"  [send] Sending iMessage to {messages_contact}...")
        imessage_ok = _send_imessage(messages_contact, target["message"])
        print(f"  [send] iMessage: {'OK' if imessage_ok else 'FAILED'}")

    successes = [r for r in [email_ok, imessage_ok] if r is True]
    failures = [r for r in [email_ok, imessage_ok] if r is False]

    if successes:
        status = "Sent"
    elif failures:
        status = "Failed"
    else:
        return

    write_outreach_cell(row_num, OR_STATUS, status)
    print(f"  [send] {target['name']}: {status}")


# ---------------------------------------------------------------------------
# Bulk send
# ---------------------------------------------------------------------------

def _bulk_eligibility(row: dict) -> tuple[bool, str]:
    """Return (eligible_for_bulk, plan_tag_or_reason).

    Bulk is email-only, so we require Email Contact regardless of phone.
    Rows with non-empty Message → "as-is". Rows with empty Message require
    Name + Company to be auto-generatable → "auto-gen". Otherwise rejected.
    """
    if not row["email_contact"]:
        return False, "no Email Contact"
    if row["message"]:
        return True, "as-is"
    if not row["name"]:
        return False, "empty Message, no Name"
    if not row["company"]:
        return False, "empty Message, no Company"
    return True, "auto-gen"


def bulk_send(*, email_only: bool = True, dry_run: bool = False) -> None:
    """Send every sendable row, with preview + YES confirmation + pacing.

    `email_only` is True by default and should almost always stay True in bulk.
    `dry_run` prints the preview and exits without sending anything.
    """
    rows = get_outreach_rows()

    eligible = []
    rejected = []
    for r in rows:
        ok, tag = _bulk_eligibility(r)
        if ok:
            eligible.append((r, tag))
        else:
            rejected.append((r, tag))

    if not eligible:
        print("  [bulk] No rows eligible for bulk send.")
        if rejected:
            print(f"  [bulk] {len(rejected)} rows rejected — most common reason: {rejected[0][1]!r}")
        return

    capped = eligible[:BULK_BATCH_CAP]
    overflow = len(eligible) - len(capped)

    print()
    print(f"  [bulk] {len(capped)} row(s) will be processed "
          f"(cap={BULK_BATCH_CAP}{'  — {} more eligible beyond cap'.format(overflow) if overflow else ''}):")
    print(f"  {'Row':>4}  {'Name':<25}  {'Company':<30}  {'Email':<35}  Plan")
    print(f"  {'-'*4}  {'-'*25}  {'-'*30}  {'-'*35}  {'-'*8}")
    for r, tag in capped:
        name = (r["name"] or "")[:25]
        comp = (str(r["company"] or ""))[:30]
        email = (r["email_contact"] or "")[:35]
        print(f"  {r['row']:>4}  {name:<25}  {comp:<30}  {email:<35}  {tag}")

    if dry_run:
        print(f"\n  [bulk] DRY-RUN — no sends performed.")
        return

    print()
    print(f"  [bulk] Email-only: {email_only}.  Pacing: {BULK_PACING_SECONDS}s between rows.")
    print(f"  [bulk] Type exactly {BULK_CONFIRM_PHRASE!r} (uppercase) to proceed. Anything else aborts.")
    confirm = input("  > ")
    if confirm != BULK_CONFIRM_PHRASE:
        print(f"  [bulk] Aborted — confirmation was {confirm!r}, expected {BULK_CONFIRM_PHRASE!r}.")
        return

    print()
    for i, (r, tag) in enumerate(capped, start=1):
        print(f"\n  [bulk] ({i}/{len(capped)}) row {r['row']} — {r['name']}  [{tag}]")
        send_row(r["row"], email_only=email_only)
        if i < len(capped):
            time.sleep(BULK_PACING_SECONDS)

    print()
    print(f"  [bulk] Done — processed {len(capped)} row(s).")
    if overflow:
        print(f"  [bulk] {overflow} more eligible row(s) remain — re-run `send` → `all` to continue.")


# ---------------------------------------------------------------------------
# Interactive dispatcher (run_outreach.py entry point)
# ---------------------------------------------------------------------------

def run(*, email_only: bool = True) -> None:
    """Interactive send — lets the user pick a row number or `all`."""
    rows = get_outreach_rows()
    eligible = [r for r in rows if _bulk_eligibility(r)[0]]

    if not eligible:
        print("  [send] No rows eligible (need Email Contact + message OR Name+Company for auto-gen).")
        return

    print("\n  Eligible rows:")
    for r in eligible[:20]:
        tag = _bulk_eligibility(r)[1]
        print(f"    Row {r['row']}: {r['name']}  ({r['email_contact']})  [{tag}]")
    if len(eligible) > 20:
        print(f"    ... and {len(eligible) - 20} more.")

    print()
    choice = input("  Enter row number to send, or 'all' for bulk: ").strip()

    if choice.lower() == "all":
        bulk_send(email_only=email_only)
        return

    try:
        send_row(int(choice), email_only=email_only)
    except ValueError:
        print(f"  [send] Invalid row number: {choice}")
