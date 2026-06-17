#!/usr/bin/env python3
"""GitHub Actions-compatible Outlook Graph sender for CA realtor outreach.

Secrets expected:
- OUTLOOK_TOKEN_JSON: JSON object containing refresh_token and optionally access_token
- OUTLOOK_CLIENT_ID: optional, defaults to Hermes Outlook client id
- OUTLOOK_TENANT_ID: optional, defaults to Hermes Outlook tenant id

Inputs/env:
- MODE=smoke or production
- RECIPIENT_CSV=path to CSV
- EXPECTED_COUNT=3 for smoke, 450 for production
- DRY_RUN=1 to validate without sending
"""
from __future__ import annotations

import csv
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CLIENT_ID = os.environ.get("OUTLOOK_CLIENT_ID", "b0a2bb2b-4833-4d35-9da0-b7dd23be3141")
TENANT_ID = os.environ.get("OUTLOOK_TENANT_ID", "2ca68321-0eda-4908-88b2-424a8cb4b0f9")
SCOPES = "Mail.Send Mail.Read Mail.ReadWrite openid profile offline_access"
TOKEN_PATH = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "outlook-token.json"

SUBJECTS = [
    "Quick student research question about real estate AI",
    "Student research project on AI in real estate",
    "Looking for real-estate operator input on AI tools",
    "Fellow Badger looking to connect about a student research project",
    "UW-Madison student looking to learn from real-estate operators",
    "Student project on AI tools for real-estate work",
    "Quick question from a UW-Madison student",
    "Student research request about real estate operations",
    "Real-estate AI research question from a student",
    "Looking to learn from California real-estate operators",
    "Student research project and real-estate AI",
    "Quick 20-minute research chat?",
    "UW student researching AI tools for real estate",
    "Question about AI in real-estate workflows",
    "Student business org research on real estate AI",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def result(status: str, **payload) -> None:
    print(f"RESULT {status} " + json.dumps({"status": status, "timestamp": utc_now(), **payload}, sort_keys=True))


def fail(message: str, **payload) -> None:
    result("FAIL", message=message, **payload)
    sys.exit(1)


def load_secret_token() -> dict:
    raw = os.environ.get("OUTLOOK_TOKEN_JSON", "").strip()
    if not raw:
        fail("missing OUTLOOK_TOKEN_JSON secret")
    token: dict = {}
    parsed = None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail("OUTLOOK_TOKEN_JSON is not valid JSON", error=str(exc))
    if not isinstance(parsed, dict):
        fail("OUTLOOK_TOKEN_JSON must be a JSON object")
        raise AssertionError("unreachable")
    token = parsed
    if not token.get("refresh_token"):
        fail("OUTLOOK_TOKEN_JSON lacks refresh_token")
    TOKEN_PATH.write_text(json.dumps(token))
    os.chmod(TOKEN_PATH, 0o600)
    return token


def refresh_access_token() -> str:
    token = load_secret_token()
    form = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
        "scope": SCOPES,
    }).encode()
    req = urllib.request.Request(
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    parsed = None
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            parsed = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:1000]
        fail("token refresh failed", http=exc.code, body=body)
    if not isinstance(parsed, dict):
        fail("token refresh response was not a JSON object")
        raise AssertionError("unreachable")
    refreshed = parsed
    if not refreshed.get("access_token"):
        fail("token refresh returned no access_token")
    TOKEN_PATH.write_text(json.dumps(refreshed))
    os.chmod(TOKEN_PATH, 0o600)
    return refreshed["access_token"]


def graph_json(method: str, url: str, access_token: str, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": f"Bearer {access_token}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode(errors="replace")
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = raw
        return exc.code, parsed


def read_rows(path: Path, expected: int) -> list[dict]:
    if not path.exists():
        fail("recipient CSV missing", csv=str(path))
    with path.open(newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    emails = [(r.get("email") or "").strip().lower() for r in rows]
    if len(rows) != expected:
        fail("unexpected recipient count", expected=expected, actual=len(rows))
    if any(not e for e in emails):
        fail("recipient CSV has empty emails")
    if len(set(emails)) != len(emails):
        fail("recipient CSV has duplicate emails")
    return rows


def first_name(row: dict) -> str:
    value = (row.get("first_name") or "").strip().split()[0:1]
    if not value:
        return "there"
    name = value[0]
    if len(name) < 2 or any(ch.isdigit() for ch in name):
        return "there"
    return name


def context(row: dict) -> str:
    if (row.get("source_context") or "").strip():
        return row["source_context"].strip()
    if (row.get("company") or "").strip():
        return f"{row['company'].strip()}'s website"
    return "your real-estate work in California"


def build_html(row: dict) -> str:
    first = html.escape(first_name(row))
    ctx = html.escape(context(row))
    return "".join([
        f"<p>Dear {first},</p>",
        "<p>My name is Malcolm Mahaney and I'm a student at the University of Wisconsin-Madison studying business.</p>",
        f"<p>I'm currently working on a research project on behalf of a student business org to help realtors and real-estate operators integrate AI into their work. I came across your work through {ctx} and wanted to reach out.</p>",
        "<p>Would you happen to have 20 minutes sometime this weekend or next week to chat?</p>",
        "<p>Thank you.</p>",
        "<p>Best,<br>Malcolm</p>",
    ])


def send_one(access_token: str, row: dict, subject: str):
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": build_html(row)},
            "toRecipients": [{"emailAddress": {"address": row["email"].strip()}}],
        },
        "saveToSentItems": True,
    }
    return graph_json("POST", "https://graph.microsoft.com/v1.0/me/sendMail", access_token, payload)


def main() -> int:
    mode = os.environ.get("MODE", "smoke")
    csv_path = Path(os.environ["RECIPIENT_CSV"])
    expected = int(os.environ.get("EXPECTED_COUNT", "3"))
    dry_run = os.environ.get("DRY_RUN", "0") == "1"
    delay = float(os.environ.get("SEND_DELAY_SECONDS", "24"))
    rows = read_rows(csv_path, expected)
    token = refresh_access_token()
    me_code, me = graph_json("GET", "https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName", token)
    if me_code != 200:
        fail("Graph /me failed", http=me_code, response=str(me)[:500])
    if not isinstance(me, dict):
        fail("Graph /me returned non-object response", http=me_code, response=str(me)[:500])
    if dry_run:
        result("DRY_RUN_PASS", mode=mode, rows=len(rows), csv=str(csv_path), mailbox=me.get("mail") or me.get("userPrincipalName"))
        return 0
    sent = []
    failed = []
    for i, row in enumerate(rows):
        subject = SUBJECTS[i % len(SUBJECTS)]
        code, resp = send_one(token, row, subject)
        if code == 401:
            token = refresh_access_token()
            code, resp = send_one(token, row, subject)
        email = row["email"].strip().lower()
        if code == 202:
            sent.append(email)
        else:
            failed.append({"email": email, "http": code, "response": str(resp)[:500]})
            break
        if i != len(rows) - 1:
            time.sleep(delay)
    status = "PASS" if not failed else "FAIL"
    result(status, mode=mode, rows=len(rows), sent_count=len(sent), failed_count=len(failed), sent=sent, failed=failed)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
