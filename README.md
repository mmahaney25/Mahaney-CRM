# MAHANEY CRM

Multi-channel outreach management tool (Email, Text/SMS, LinkedIn) built on a Microsoft Excel/OneDrive spreadsheet.

See [`docs/executive-plan.md`](docs/executive-plan.md) for the product overview. Component specs live under [`docs/product-specs/`](docs/product-specs) and [`docs/page-specs/`](docs/page-specs).

## Requirements

- macOS (text sync reads the local iMessage `chat.db`)
- Python 3.11+
- A Microsoft 365 account with OneDrive + Outlook
- An Azure AD app registration (public client) with delegated scopes: `Mail.Read`, `Mail.Send`, `Files.ReadWrite`
- An Anthropic API key (used by the generate pipeline)

## Install

```bash
# 1. Clone
git clone <repo-url> "MAHANEY CRM"
cd "MAHANEY CRM"

# 2. Create a virtualenv and install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure

Create a `.env` file in the project root:

```bash
AZURE_CLIENT_ID=<your-azure-app-client-id>
AZURE_AUTHORITY=https://login.microsoftonline.com/<your-tenant-id>
ONEDRIVE_PATH=Email_Outreach_Manager.xlsx
ANTHROPIC_API_KEY=<your-anthropic-key>
```

`ONEDRIVE_PATH` is the path to the workbook relative to the root of your OneDrive.

### Grant Terminal access to Messages

Text sync reads `~/Library/Messages/chat.db` directly. In **System Settings → Privacy & Security → Full Disk Access**, add your terminal app (Terminal.app, iTerm, etc.).

### Create the workbook

If you don't already have the workbook, generate one with the correct schema:

```bash
python create_workbook.py
```

This writes `~/Downloads/Email_Outreach_Manager.xlsx`. Move it into OneDrive at the path set in `ONEDRIVE_PATH`.

## Usage

```bash
# Sync email + text + LinkedIn into the workbook
python run_outreach.py update

# Full re-sync (resets watermarks)
python run_outreach.py update --reset

# Sync one channel only
python run_outreach.py email-only
python run_outreach.py text-only
python run_outreach.py linkedin-only

# Send outreach (interactive picker)
python run_outreach.py send

# Send a specific row on the Outreach sheet
python run_outreach.py send --row 5

# Preview without sending or writing
python run_outreach.py send --row 5 --dry-run

# Also send via iMessage when a phone number is present
python run_outreach.py send --row 5 --with-imessage

# Bulk send to every eligible row (prompts for confirmation)
python run_outreach.py send --all
```

On first run, MSAL will open a browser for Microsoft sign-in. The token is cached in `.msal_cache.bin` so subsequent runs are silent.

## Project layout

```
run_outreach.py        # CLI entry point
update_outreach.py     # Orchestrates the full sync pipeline
create_workbook.py     # One-shot workbook generator
lib/                   # auth, excel_io, phone, state, template_io
pipelines/             # email, text, linkedin, generate, send
docs/                  # product and page specs
```
