# Outreach

The Outreach page is the "Outreach" sheet (separate tab) inside `Email_Outreach_Manager.xlsx` on OneDrive. This is the action page — you compose a message, enter your contacts, and hit Send.

> **Outreach is independent from Tracker.** All contact info on this sheet (name, email, phone, company) is entered manually by you. It does not pull from, copy from, or sync with the Tracker sheet. The two sheets share the same workbook but operate on their own data. You may have contacts on Outreach that aren't on Tracker, or vice versa.

---

## Spreadsheet Layout

| Col | Header | Type | Who writes it | Description |
|-----|--------|------|---------------|-------------|
| A | Name | Manual | You | Contact's full name |
| B | Status | Auto (overridable) | Script | `"Sent"` after the Send button fires. `"Replied"` when a reply is detected on the next sync run |
| C | Email Contact | Manual | You | Contact's email address — if filled, Send will email this address |
| D | Messages Contact | Manual | You | Contact's phone number — if filled, Send will iMessage this number |
| E | Company | Manual | You | Contact's company |
| F | Message | Manual | You | The message body to send. Write it directly or paste from the Templates tab |
| G | Send | Button | You (click) | Fires the send pipeline for that row |

> **Channel targeting:** The Send button looks at which contact columns are filled in. If only Email Contact has a value, it sends email only. If only Messages Contact has a value, it sends iMessage only. If both are filled, it sends to both channels.

---

## Status Logic

| Value | Meaning | When it's set |
|-------|---------|---------------|
| `"Sent"` | Message was sent | Immediately after the Send button fires and at least one channel succeeds |
| `"Failed"` | Send failed | Immediately after the Send button fires and ALL channels failed |
| `"Replied"` | They responded | On the next `/update` sync run, when the Tracker pipeline detects a reply via email or text |

- Status starts **blank** for new rows
- After Send fires:
  - If **at least one channel succeeds** → `"Sent"`
  - If **all channels fail** → `"Failed"` (the row stays in place so you can retry or fix the contact info)
- Reply detection reuses the existing Tracker pipelines (email via Microsoft Graph inbox scan, text via chat.db read) — no new reply-detection logic needed
- Status is overridable — you can manually type into it at any time
- A `"Failed"` status does not block future sends — you can fix the contact info and click Send again

---

## Send Pipeline

### Email Send — Microsoft Graph (extends existing MSAL pipeline)

Uses the same MSAL authentication flow and token cache (`.msal_cache.bin`) already proven in the Tracker email pipeline. The only addition is the `Mail.Send` scope.

- **Auth:** MSAL device flow → Azure/Entra ID → Bearer token (same as Tracker)
- **Scope:** `Mail.Send` (in addition to existing `Mail.Read` + `Files.ReadWrite`)
- **API:** `POST /me/sendMail` via Microsoft Graph
- **Payload:** `to` = Email Contact column, `body` = Message column (plain text)

### iMessage Send — osascript (macOS AppleScript)

The existing text pipeline reads from `~/Library/Messages/chat.db` via SQLite. For **sending**, the standard macOS approach is AppleScript executed via `osascript`. This pairs with the existing read pipeline — you send via AppleScript, and the Tracker's chat.db reader picks up the reply.

- **Method:** `osascript -e 'tell application "Messages" to send "<message>" to buddy "<phone>" of service "iMessage"'`
- **Input:** `phone` = Messages Contact column (normalized to E.164), `message` = Message column
- **Fallback:** If iMessage delivery fails (e.g. contact not on iMessage), the script logs the error and Status stays blank — it does not fall back to SMS automatically

---

## Send Pipeline Diagram

```
┌─────────────────────────────────────────────────────────┐
│              YOU CLICK SEND (row N)                      │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  1. READ ROW                                            │
│     Read columns C, D, F from the clicked row           │
│     → email_contact, messages_contact, message_body     │
│                                                         │
│     If Message (F) is empty → abort, show error         │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  2. DETERMINE CHANNELS                                  │
│                                                         │
│     Email Contact filled?  ──→  send_email = true       │
│     Messages Contact filled? → send_imessage = true     │
│     Neither filled? → abort, show error                 │
└────────────────────────┬────────────────────────────────┘
                         │
                    ┌────┴─────┐
                    │          │
          ┌─────────▼──┐  ┌───▼───────────┐
          │ EMAIL PATH │  │ iMESSAGE PATH │
          └─────────┬──┘  └───┬───────────┘
                    │         │
                    ▼         ▼
┌──────────────────────┐  ┌──────────────────────────────┐
│  3a. LOG IN (MSAL)   │  │  3b. BUILD APPLESCRIPT       │
│  Reuse cached token  │  │  tell application "Messages" │
│  from .msal_cache.bin│  │    to send <message>         │
│                      │  │    to buddy <phone>          │
│  Scope: Mail.Send    │  │    of service "iMessage"     │
└──────────┬───────────┘  └──────────────┬───────────────┘
           │                             │
           ▼                             ▼
┌──────────────────────┐  ┌──────────────────────────────┐
│  4a. SEND EMAIL      │  │  4b. SEND iMESSAGE           │
│  POST /me/sendMail   │  │  Execute via osascript       │
│  via Microsoft Graph │  │                              │
│                      │  │  macOS handles delivery      │
│  to: Email Contact   │  │  to: Messages Contact        │
│  body: Message col   │  │  body: Message col           │
└──────────┬───────────┘  └──────────────┬───────────────┘
           │                             │
           └──────────┬──────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│  5. UPDATE STATUS                                       │
│     If at least one channel succeeded:                  │
│       → Status (B) = "Sent"                             │
│     If ALL channels failed:                             │
│       → Status (B) = "Failed"                           │
│       → Row stays in place so you can fix + retry       │
└─────────────────────────────────────────────────────────┘
```

## Personalization & Generated Message Columns

The outreach generation pipeline (see `docs/prompt.md`) reads personalization inputs from the Outreach sheet and writes its result back into the last column. The `generated_message` column must remain the final column on the sheet — any future columns should be added before it.

| Column | Type | Description | Example |
|---|---|---|---|
| first_name | Manual | First name only, used in the greeting. | `Adam` |
| company | Manual | Reuses the existing **Company** column (E). Substituted verbatim into the template. | `Aston Educational Group` |
| industry | Manual | Reuses the existing **Industry** column (J). Reviewer context only; NOT substituted into the message body. | `Education` |
| grad_year | Manual | UW-Madison graduation year if known. Reviewer context only; not substituted into the body. | `2008` |
| business_detail | Manual | One-phrase fact about the contact's role or business (role title, sub-industry, city). Reviewer context only; not substituted into the body. | `CEO - Aston (China)` |
| subject | Auto (pipeline) | Email subject emitted by the Drafter. Always the canonical value `Fellow Badger Looking To Learn` defined in `Template.md`; this string never changes. Placed immediately before `generated_message`. | `Fellow Badger Looking To Learn` |
| generated_message | Auto (pipeline) | Final body output of the 4-agent pipeline. Must be the last column on the sheet. Line breaks are encoded as the literal two-character sequence `\n`. | `Hi Adam,\n\nI hope you're having a good day! ...\n\nBest,\nMalcolm` |

### Spacing convention

All values in `generated_message` use the **literal two-character sequence `\n`** (backslash + lowercase n) to mark a line break. The sheet stores this string as-is; the send step converts `\n` to real newlines before handing the body to Microsoft Graph. This marker is the single source of truth for line breaks throughout the pipeline — no `<br>`, no real newlines, no `\r\n`.

Before (as stored in the `generated_message` cell):
```
Hi Adam,\n\nI hope you're having a good day! ...\n\nBest,\nMalcolm
```

After (as rendered for send):
```
Hi Adam,

I hope you're having a good day! ...

Best,
Malcolm
```

---

### Reply Detection (reuses Tracker pipelines)

```
┌─────────────────────────────────────────────────────────┐
│              NEXT TIME YOU RUN /update                   │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Tracker email pipeline scans Outlook inbox             │
│  Tracker text pipeline scans chat.db                    │
│                                                         │
│  If a reply is found matching a contact on the          │
│  Outreach tab → Status (B) = "Replied"                  │
└─────────────────────────────────────────────────────────┘
```
