#!/usr/bin/env python3
"""CLI entry point for the MAHANEY CRM outreach tool."""

import argparse
import sys
from pathlib import Path

# Ensure project root is on the path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env file (python-dotenv handles quoting, escapes, multiline, etc.)
from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")


def main():
    parser = argparse.ArgumentParser(
        description="MAHANEY CRM — Multi-channel outreach management tool"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # update command — runs all sync pipelines
    update_parser = subparsers.add_parser("update", help="Run full sync pipeline (email + text + LinkedIn)")
    update_parser.add_argument(
        "--reset", action="store_true",
        help="Reset all watermarks before running (full re-sync of emails and texts)"
    )

    # send command — send outreach from the Outreach sheet
    send_parser = subparsers.add_parser("send", help="Send outreach messages")
    send_parser.add_argument(
        "--row", type=int,
        help="Row number on the Outreach sheet to send (omit for interactive mode)"
    )
    send_parser.add_argument(
        "--with-imessage", action="store_true",
        help="Also send via iMessage if a phone is present. Default is email-only."
    )
    send_parser.add_argument(
        "--dry-run", action="store_true",
        help="Print the plan without sending or writing to the sheet."
    )
    send_parser.add_argument(
        "--all", action="store_true",
        help="Bulk send to every eligible row (with preview + YES confirmation + pacing)."
    )

    # email-only command
    subparsers.add_parser("email-only", help="Run only the email sync pipeline")

    # text-only command
    subparsers.add_parser("text-only", help="Run only the text sync pipeline")

    # linkedin-only command
    subparsers.add_parser("linkedin-only", help="Run only the LinkedIn sync pipeline")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "update":
        if args.reset:
            from lib.state import reset_email_watermark, reset_text_watermark
            reset_email_watermark()
            reset_text_watermark()
        from update_outreach import run_update
        run_update()

    elif args.command == "send":
        from pipelines.send_pipeline import send_row, bulk_send, run as send_interactive
        email_only = not args.with_imessage
        if args.all:
            bulk_send(email_only=email_only, dry_run=args.dry_run)
        elif args.row:
            send_row(args.row, email_only=email_only, dry_run=args.dry_run)
        else:
            send_interactive(email_only=email_only)

    elif args.command == "email-only":
        from pipelines.email_pipeline import run as run_email
        print("Running email pipeline only...\n")
        run_email()

    elif args.command == "text-only":
        from pipelines.text_pipeline import run as run_text
        print("Running text pipeline only...\n")
        run_text()

    elif args.command == "linkedin-only":
        from pipelines.linkedin_pipeline import run as run_linkedin
        print("Running LinkedIn pipeline only...\n")
        run_linkedin()


if __name__ == "__main__":
    main()
