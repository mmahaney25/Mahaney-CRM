# Executive Plan: Mahaney CRM Outreach Tool

## What It Is

A centralized outreach management system built on a single Microsoft Excel workbook (OneDrive). It unifies three communication channels -- Email, Text/SMS, and LinkedIn -- into one spreadsheet so all outreach activity can be tracked, prioritized, and acted on from one place for Malcolms networking tracker for his business.

## Purpose

Eliminate the need to check multiple platforms to know where each contact stands. The tool answers one question at a glance: **who needs attention and through which channel?**

## Workbook Structure

The workbook has three pages:

- **Tracker** -- The master view. Every contact lives here with their name, general status, channel-specific statuses (email/text/LinkedIn), priority, and contact info. Data is anchored to the name row/column so the layout is rotatable.
- **Outreach** -- The action page. Enter a contact's info manually, compose a message, and trigger sends. Tracks sent/failed/replied states per message. **Outreach is independent from Tracker** -- all contact data on this sheet is entered by hand, not copied or synced from Tracker.
- **Templates** -- Fill-text templates that feed into the outreach page for consistent messaging.

## How the Channels Connect

Each channel has its own data pipeline that syncs external data into the Tracker:

- **Email**: Authenticates via MSAL through Azure AD, hits Microsoft Graph API to read mail and write status back to the spreadsheet.
- **Text/SMS**: Reads the local macOS iMessage database (chat.db via SQLite), syncs message history into the spreadsheet using a watermark timestamp to track what's already been processed.
- **LinkedIn**: Scrapes outlook for notifcations of recived linked in message. NOT ABLE TO CHECK IF SENT THATS MANUAL

All three pipelines write back to the same Tracker page, keeping one unified view per contact.



## API Pattern

All external data flows use HTTP semantics: GET to read, POST to create, PATCH to update existing spreadsheet cells and sync watermarks.

