#!/usr/bin/env python3
"""Outlook follow-up triage — reads the mailbox via Microsoft Graph and prints a
ranked list of real-estate / property-management contacts who need a follow-up.

It NEVER prints the token. The refresh token arrives as a write-only GitHub
Actions secret and is exchanged for a short-lived access token at runtime, the
same way scripts/github_realtor_outreach_sender.py does it.

Secrets / env expected:
- OUTLOOK_TOKEN_JSON : JSON object containing a refresh_token (required).
- OUTLOOK_CLIENT_ID  : optional, defaults to the Hermes Outlook client id.
- OUTLOOK_TENANT_ID  : optional, defaults to the Hermes Outlook tenant id.

Tunable env:
- LOOKBACK_DAYS  : how far back to scan SENT mail (default 35 ~ "last month").
- NO_REPLY_DAYS  : silence threshold before a sent mail counts as "needs nudge"
                   (default 4 business-ish days -> calendar days here).

Triage rules (locked with Malcolm 2026-06-19):
- Industry: ONLY real estate / property management. Non-RE/PM contacts are
  dropped from the ranked list; genuinely ambiguous ones go to a REVIEW bucket
  so nothing real is silently lost.
- Drop bots / automated senders (no-reply@, notifications@, mailer-daemon, ...).
- Drop pure auto-replies (out-of-office) UNLESS they state a return date / that
  the person is back — those are surfaced to follow up at/after that date.
- Include people who never replied (need a nudge) and people who replied and are
  now waiting on Malcolm (his turn).
- Flag bounces / NDRs as a possible switched/bad address.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

CLIENT_ID = os.environ.get("OUTLOOK_CLIENT_ID", "b0a2bb2b-4833-4d35-9da0-b7dd23be3141")
TENANT_ID = os.environ.get("OUTLOOK_TENANT_ID", "2ca68321-0eda-4908-88b2-424a8cb4b0f9")
SCOPES = "Mail.Read Mail.ReadWrite openid profile offline_access"
TOKEN_PATH = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "outlook-token.json"
GRAPH = "https://graph.microsoft.com/v1.0"

LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", "35"))
NO_REPLY_DAYS = int(os.environ.get("NO_REPLY_DAYS", "4"))

# ---- Classification vocabularies ------------------------------------------

# Automated / non-human local-parts and senders. Matched against the local part
# (before @) and against the full address for a couple of well-known systems.
BOT_LOCALPARTS = {
    "no-reply", "noreply", "no_reply", "donotreply", "do-not-reply",
    "notifications", "notification", "notify", "alerts", "alert", "mailer",
    "mailer-daemon", "postmaster", "bounce", "bounces", "system", "automated",
    "auto", "support", "newsletter", "news", "info", "hello", "team", "updates",
    "marketing", "noreply-calendar", "calendar", "invitations",
}
BOT_DOMAIN_HINTS = (
    "mailchimp", "sendgrid", "mailgun", "constantcontact", "hubspot", "marketo",
    "salesforce", "intuit", "docusign", "calendly", "eventbrite", "linkedin",
    "indeed", "ziprecruiter", "facebookmail", "google.com", "accounts.google",
    "amazonses", "postmarkapp", "zendesk",
)

# Bounce / non-delivery report signals (sender + subject).
NDR_SENDERS = ("mailer-daemon", "postmaster", "microsoftexchange")
NDR_SUBJECT = re.compile(
    r"undeliverable|delivery (has )?failed|delivery status notification|"
    r"address not found|recipient.*not found|returned mail|mail delivery",
    re.I,
)

# Auto-reply / out-of-office signals (subject + body).
AUTOREPLY_SUBJECT = re.compile(
    r"automatic reply|auto[- ]?reply|out of (the )?office|out of office|"
    r"away from (the )?office|on vacation|on holiday|annual leave|maternity|"
    r"paternity|currently away|i am away|ooo\b",
    re.I,
)

# "I'm back / will return on <date>" signals inside an OOO body.
RETURN_HINT = re.compile(
    r"(back (in|on|the)|return(ing)? (on|to the office|to work)|"
    r"will return|i return|until|through|am back|i'm back|now back|"
    r"resume.{0,20}(on|office))",
    re.I,
)

# Real-estate / property-management vocabulary. Hit on company, domain, subject,
# or body preview marks a contact as in-scope.
RE_PM_TERMS = (
    "real estate", "realestate", "realtor", "realty", "real-estate",
    "property management", "property manager", "properties", "property group",
    "brokerage", "broker", "homes", "home sales", "residential", "commercial real",
    "leasing", "landlord", "tenant", "apartments", "multifamily", "multi-family",
    "hoa", "condo", "mls", "listing agent", "buyer's agent", "real property",
    "keller williams", "re/max", "remax", "coldwell", "century 21", "compass real",
    "sotheby", "berkshire hathaway home", "exp realty", "cbre", "jll", "cushman",
    "colliers", "marcus & millichap", "real estate investment", "reit",
    "rentals", "rent", "escrow", "title company", "apprais",
)
RE_PM_DOMAIN_HINTS = (
    "realty", "realtor", "properties", "property", "homes", "realestate",
    "kw.com", "remax", "cbre", "compass.com", "exprealty", "century21",
    "coldwellbanker", "sothebysrealty",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def fail(message: str, **payload) -> None:
    print("RESULT FAIL " + json.dumps({"status": "FAIL", "message": message, **payload}, sort_keys=True))
    sys.exit(1)


# ---- Auth ------------------------------------------------------------------

def refresh_access_token() -> str:
    raw = os.environ.get("OUTLOOK_TOKEN_JSON", "").strip()
    if not raw:
        fail("missing OUTLOOK_TOKEN_JSON secret")
    try:
        token = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail("OUTLOOK_TOKEN_JSON is not valid JSON", error=str(exc))
    if not isinstance(token, dict) or not token.get("refresh_token"):
        fail("OUTLOOK_TOKEN_JSON lacks refresh_token")
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
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            refreshed = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        fail("token refresh failed", http=exc.code, body=exc.read().decode(errors="replace")[:500])
    if not refreshed.get("access_token"):
        fail("token refresh returned no access_token")
    return refreshed["access_token"]


def graph_get(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode(errors="replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        fail("Graph GET failed", http=exc.code, url=url.split("?")[0], body=exc.read().decode(errors="replace")[:400])


def fetch_folder(folder: str, token: str, since_iso: str) -> list[dict]:
    """Page through a mail folder, newest first, filtered to >= since_iso."""
    select = "from,toRecipients,subject,bodyPreview,receivedDateTime,sentDateTime"
    params = urllib.parse.urlencode({
        "$select": select,
        "$top": "100",
        "$orderby": "receivedDateTime desc",
        "$filter": f"receivedDateTime ge {since_iso}",
    })
    url = f"{GRAPH}/me/mailFolders/{folder}/messages?{params}"
    out: list[dict] = []
    while url and len(out) < 1000:
        data = graph_get(url, token)
        out.extend(data.get("value", []))
        url = data.get("@odata.nextLink")
    return out


# ---- Helpers ---------------------------------------------------------------

def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def addr_of(person: dict | None) -> str:
    try:
        return (person["emailAddress"]["address"] or "").strip().lower()
    except (KeyError, TypeError):
        return ""


def name_of(person: dict | None) -> str:
    try:
        return (person["emailAddress"].get("name") or "").strip()
    except (AttributeError, KeyError, TypeError):
        return ""


def is_bot(address: str) -> bool:
    if not address or "@" not in address:
        return True
    local, _, domain = address.partition("@")
    if local in BOT_LOCALPARTS:
        return True
    if any(hint in domain for hint in BOT_DOMAIN_HINTS):
        return True
    return False


def is_ndr(address: str, subject: str) -> bool:
    return any(s in address for s in NDR_SENDERS) or bool(NDR_SUBJECT.search(subject or ""))


def is_autoreply(subject: str, body: str) -> bool:
    return bool(AUTOREPLY_SUBJECT.search(subject or "") or AUTOREPLY_SUBJECT.search(body or ""))


def return_snippet(body: str) -> str | None:
    """Pull a short 'back on <date>' style snippet from an OOO body, if present."""
    body = (body or "").strip()
    if not body or not RETURN_HINT.search(body):
        return None
    m = RETURN_HINT.search(body)
    start = max(0, m.start() - 10)
    return re.sub(r"\s+", " ", body[start:start + 90]).strip()


def is_re_pm(*texts: str) -> bool:
    blob = " ".join(t.lower() for t in texts if t)
    if any(term in blob for term in RE_PM_TERMS):
        return True
    return False


def re_pm_domain(address: str) -> bool:
    domain = address.partition("@")[2]
    return any(h in domain for h in RE_PM_DOMAIN_HINTS)


# ---- Main triage -----------------------------------------------------------

def main() -> int:
    token = refresh_access_token()

    me = graph_get(f"{GRAPH}/me?$select=mail,userPrincipalName,displayName", token)
    mailbox = me.get("mail") or me.get("userPrincipalName") or "?"

    since = (utc_now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sent = fetch_folder("sentitems", token, since)
    inbox = fetch_folder("inbox", token, since)

    # Index inbound mail by sender address -> list of (datetime, subject, body).
    inbound: dict[str, list[tuple[datetime, str, str]]] = {}
    for msg in inbox:
        addr = addr_of(msg.get("from"))
        dt = parse_dt(msg.get("receivedDateTime"))
        if not addr or not dt:
            continue
        inbound.setdefault(addr, []).append((dt, msg.get("subject", ""), msg.get("bodyPreview", "")))

    # Latest outbound per recipient (capture name + a content blob for industry).
    sent_to: dict[str, dict] = {}
    for msg in sent:
        dt = parse_dt(msg.get("sentDateTime") or msg.get("receivedDateTime"))
        if not dt:
            continue
        blob = f"{msg.get('subject','')} {msg.get('bodyPreview','')}"
        for r in msg.get("toRecipients", []):
            addr = addr_of(r)
            if not addr:
                continue
            cur = sent_to.get(addr)
            if cur is None or dt > cur["dt"]:
                sent_to[addr] = {"dt": dt, "name": name_of(r), "blob": blob}

    now = utc_now()
    targets: list[dict] = []   # in-scope RE/PM follow-ups
    review: list[dict] = []    # ambiguous industry — surfaced for a human glance
    dropped = {"bot": 0, "ooo_no_return": 0, "non_re_pm": 0}

    for addr, info in sent_to.items():
        if is_bot(addr):
            dropped["bot"] += 1
            continue

        replies = sorted(inbound.get(addr, []), key=lambda t: t[0])
        after = [r for r in replies if r[0] >= info["dt"]]

        reason = None
        return_note = None
        bounced = False
        last_human_dt = info["dt"]

        # Classify the conversation state.
        real_reply = None
        for dt, subj, body in after:
            if is_ndr(addr, subj):
                bounced = True
                continue
            if is_autoreply(subj, body):
                snippet = return_snippet(body)
                if snippet:               # OOO but they said they're back / return date
                    return_note = snippet
                continue                  # pure auto-reply otherwise -> not a real reply
            real_reply = (dt, subj, body)  # a genuine human reply

        if real_reply:
            reason = "THEY REPLIED — your turn to respond"
            last_human_dt = real_reply[0]
        elif bounced:
            reason = "BOUNCED — possible switched/changed address (verify contact info)"
        elif return_note:
            reason = f"Auto-reply said they're back/returning — follow up ({return_note})"
        elif after:
            # only auto-replies with no return info -> per rules, drop
            dropped["ooo_no_return"] += 1
            continue
        else:
            age = (now - info["dt"]).days
            if age < NO_REPLY_DAYS:
                continue  # too fresh to chase
            reason = f"No reply in {age}d — send a nudge"

        # Industry gate: ONLY real estate / property management.
        scoped = is_re_pm(info["name"], info["blob"]) or re_pm_domain(addr)
        record = {
            "name": info["name"] or addr.split("@")[0],
            "email": addr,
            "reason": reason,
            "last_contact": info["dt"].strftime("%Y-%m-%d"),
            "_rank": (
                0 if real_reply else 1 if bounced else 2 if return_note else 3,
                last_human_dt,
            ),
        }
        if scoped:
            targets.append(record)
        else:
            dropped["non_re_pm"] += 1
            record["note"] = "industry unconfirmed from email content"
            review.append(record)

    # Rank: replies first, then bounces, then OOO-back, then oldest nudges.
    targets.sort(key=lambda r: (r["_rank"][0], r["_rank"][1]))
    for r in targets + review:
        r.pop("_rank", None)

    # ---- Human-readable report (this is what gets read from the run log) ----
    print("=" * 72)
    print(f"FOLLOW-UP TRIAGE  |  mailbox: {mailbox}")
    print(f"window: last {LOOKBACK_DAYS} days  |  sent scanned: {len(sent)}  inbox scanned: {len(inbox)}")
    print(f"dropped -> bots: {dropped['bot']}  pure-OOO: {dropped['ooo_no_return']}  non-RE/PM: {dropped['non_re_pm']}")
    print("=" * 72)
    print(f"\nRANKED RE/PM FOLLOW-UPS ({len(targets)}):\n")
    for i, r in enumerate(targets, 1):
        print(f"{i:>2}. {r['name']}  <{r['email']}>")
        print(f"    last contact {r['last_contact']}  |  {r['reason']}")
    if review:
        print(f"\nREVIEW — possible RE/PM but industry unconfirmed ({len(review)}):\n")
        for r in review:
            print(f"  - {r['name']} <{r['email']}>  (last {r['last_contact']}) — {r['reason']}")

    print("\nRESULT PASS " + json.dumps({
        "status": "PASS",
        "mailbox": mailbox,
        "window_days": LOOKBACK_DAYS,
        "ranked_count": len(targets),
        "review_count": len(review),
        "dropped": dropped,
        "targets": targets,
        "review": review,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
