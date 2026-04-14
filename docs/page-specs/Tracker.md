# Tracker

The Tracker is the "Outreach Tracker" sheet inside `Email_Outreach_Manager.xlsx` on OneDrive. It is the single view for all outreach contacts — automatically updated by Python scripts that sync email, text, and LinkedIn activity, and manually sortable/editable at any time.

---

## Update Button

Cell **A1** contains a button labeled **"Update"**. Clicking it runs the `run_outreach.py` script, which executes the full sync pipeline (email, then text, then LinkedIn). The button is an Excel Form Control button assigned to a macro that shells out to the Python script.

---

## Spreadsheet Layout

Row 1 is the header row (with the Update button in A1). Contact data starts in row 2. The migration code in `update_outreach.py` enforces this layout — if columns are out of order or missing, it rewrites the sheet to match.

| Col | Header | Type | Who writes it | Description |
|-----|--------|------|---------------|-------------|
| A | Name | Manual | You | Contact's full name |
| B | General Status | Auto (overridable) | Script | `"Sent"` or `"Reply"` — determined by the most recent event across all three channels (see derivation below) |
| C | Priority | Manual | You | `High`, `Medium`, or `Low`. Colorized: **High = red**, **Medium = yellow**, **Low = green** |
| D | Age | Auto (overridable) | Script | Time since most recent sent or received event across all channels. Displayed in **hours** (e.g. `"14h"`). If **>72 hours**, displayed in **days** instead (e.g. `"4d"`) |
| E | Email Status | Auto (overridable) | Email script | Status from the email pipeline (see email-component spec) |
| F | Text Status | Auto (overridable) | Text script | Status from the text pipeline (see text-component spec) |
| G | LinkedIn Status | Auto (overridable) | LinkedIn script | Status from the LinkedIn pipeline (see linkedin-component spec) |
| H | Email | Manual | You | Contact's email address — **match key for email pipeline** |
| I | Number | Manual | You | Contact's phone number — **match key for text pipeline** |

> **Manual override rule:** Every auto-calculated cell (General Status, Age, Email/Text/LinkedIn Status) can be typed into manually. If you manually set a value, the script will overwrite it on the next sync run. To preserve a manual override, don't run the update for that contact — or clear the match key (Email/Number) so the script skips the row.

---

## General Status Derivation

General Status (column B) is a rollup of the three channel statuses. The script determines it as follows:

1. Collect the most recent **sent** timestamp across all channels (email sent, text sent, LinkedIn sent if tracked)
2. Collect the most recent **received** timestamp across all channels (email received, text received, LinkedIn received)
3. Compare the two timestamps — whichever is more recent determines the status:
   - If the most recent event was **you sending** → General Status = `"Sent"`
   - If the most recent event was **them replying** → General Status = `"Reply"`

If no activity exists for a contact, General Status is blank.

---

## Age Calculation

Age (column D) is derived from the same "most recent event" timestamp used by General Status:

- Compute `now - most_recent_event_timestamp` in hours
- If the result is **≤72 hours**, display as hours (e.g. `"14h"`, `"72h"`)
- If the result is **>72 hours**, convert to days and display as days (e.g. `"4d"`, `"12d"`)

If no activity exists for a contact, Age is blank.

---

## Sorting / Ranking Rules

The spreadsheet is auto-sorted so the contacts most needing attention are at the top:

1. **Need to reply** — contacts where General Status = `"Reply"` (they messaged you and are waiting) are ranked above all `"Sent"` contacts
2. **Among "Reply" rows** — sorted by Age descending (longest-waiting first, so the person you've left hanging the longest is at the very top)
3. **Among "Sent" rows** — sorted by Age ascending (most recently sent first, since those are the freshest outreach attempts)

---

## Pipeline Diagrams

### Email Pipeline

```
┌─────────────────────────────────────────────────────────┐
│                    YOU RUN /update                       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  1. READ WATERMARK                                      │
│     "When did I last run?" (.outreach_state.json)       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  2. LOG IN                                              │
│     MSAL checks cached token (.msal_cache.bin)          │
│     If expired → opens browser for you to sign in       │
│     Result: a Bearer token for Microsoft Graph          │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  3. FETCH EMAIL FROM OUTLOOK (via Microsoft Graph)      │
│                                                         │
│     ┌──────────────┐       ┌──────────────┐            │
│     │    Inbox      │       │  Sent Items   │           │
│     │  (received)   │       │   (sent)      │           │
│     └──────┬───────┘       └──────┬───────┘            │
│            │                      │                     │
│            ▼                      ▼                     │
│     Who emailed you?      Who did you email?            │
│     + when + subject      + when + subject              │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  4. BUILD LOOKUP TABLES                                 │
│                                                         │
│     recv_map:  "jane@co.com" → (Apr 10, "Re: Hello")   │
│     sent_map:  "jane@co.com" → (Apr 9,  "Hello")       │
│                                                         │
│     Keeps only the NEWEST email per person              │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  5. OPEN SPREADSHEET (via Microsoft Graph → OneDrive)   │
│                                                         │
│     Email_Outreach_Manager.xlsx                         │
│     Read all rows from "Outreach Tracker" sheet         │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  6. MATCH + UPDATE ROWS                                 │
│                                                         │
│     For each row in the spreadsheet:                    │
│       - Read the Email column                           │
│       - Is that email in sent_map? → Status = "Sent"    │
│       - Is that email in recv_map? → Status = "Replied" │
│       - Write timestamps, subject, Last Updated         │
│                                                         │
│     (Replied wins if both exist)                        │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  7. SAVE WATERMARK                                      │
│     Write current time → .outreach_state.json           │
│     (So next run only checks new emails)                │
└─────────────────────────────────────────────────────────┘
```

### Text/SMS Pipeline

```
┌─────────────────────────────────────────────────────────┐
│              (runs right after email finishes)           │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  1. READ WATERMARK                                      │
│     "When did I last run?" (.texts_state.json)          │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  2. LOG IN                                              │
│     Same MSAL flow as email (reuses cached token)       │
│     Needed to read and write the spreadsheet            │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  3. READ PHONE NUMBERS FROM SPREADSHEET                 │
│     (via Microsoft Graph → OneDrive)                    │
│                                                         │
│     Opens the spreadsheet, reads the Phone column       │
│     Normalizes each to +1XXXXXXXXXX format              │
│     Result: a set of phone numbers to look for          │
│     (e.g. 4 numbers from 4 contacts)                    │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  4. READ TEXTS FROM YOUR MAC (NOT Microsoft Graph)      │
│                                                         │
│     ~/Library/Messages/chat.db  (local SQLite file)     │
│                                                         │
│     Query: messages since last run, BUT ONLY for        │
│            phone numbers found in step 3                │
│            (SQL WHERE h.id IN (+1555..., +1555...))     │
│                                                         │
│     Messages from everyone else are never read.         │
│                                                         │
│     Returns: phone number, sent-or-received,            │
│              timestamp, first 80 chars of message       │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  5. BUILD LOOKUP TABLES                                 │
│                                                         │
│     recv_map:  "+15551234567" → (Apr 11, "Hey sounds…") │
│     sent_map:  "+15551234567" → (Apr 10, "Are you fr…") │
│                                                         │
│     Now only contains your spreadsheet contacts         │
│     Keeps only the NEWEST text per person               │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  6. OPEN SPREADSHEET AGAIN + MATCH + UPDATE ROWS        │
│     (via Microsoft Graph → OneDrive)                    │
│                                                         │
│     New session — separate from step 3                  │
│                                                         │
│     For each row in the spreadsheet:                    │
│       - Read the Phone column, normalize it             │
│       - Is that phone in sent_map?                      │
│            → Text Status = "Text Sent"                  │
│       - Is that phone in recv_map?                      │
│            → Text Status = "Text Received"              │
│       - Write timestamps, preview, Last Updated         │
│                                                         │
│     (Text Received wins if both exist)                  │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  7. SAVE WATERMARK                                      │
│     Write the NEWEST MESSAGE's timestamp                │
│     → .texts_state.json                                 │
│     (Uses message time, not clock time,                 │
│      so no texts get skipped)                           │
└─────────────────────────────────────────────────────────┘
```

### LinkedIn Pipeline (planned)

```
┌─────────────────────────────────────────────────────────┐
│  LinkedIn Pipeline (runs inside update_outreach.py)     │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  1. FETCH INBOX (already happening for email)           │
│     Filter to: from = messages-noreply@linkedin.com     │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  2. PARSE NOTIFICATION EMAILS                           │
│     Extract: contact name + timestamp                   │
│     "John Smith sent you a message on Apr 11"           │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  3. BUILD LOOKUP TABLE                                  │
│     name_map: "john smith" → (Apr 11 timestamp)         │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│  4. MATCH + UPDATE ROWS                                 │
│     For each row, fuzzy-match the Name column           │
│     against name_map                                    │
│     → LinkedIn Status = "LI Received"                   │
│     → Last LI Received = timestamp                      │
└─────────────────────────────────────────────────────────┘
```

