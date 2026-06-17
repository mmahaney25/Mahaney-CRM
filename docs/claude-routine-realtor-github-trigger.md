# Claude Routine Prompt: Create 7 AM Realtor Send Trigger and Smoke Test

You are Claude Code running inside `/Users/mm/MAHANEY CRM` for Malcolm.

Goal: create and verify the GitHub Actions trigger for the California realtor outreach send.

Hard constraints:
- Do not print, copy, or expose Outlook token values.
- Do not use local sendmail.
- Do not invent recipients.
- Do not send production recipients during smoke test.
- Smoke test may send only the 3 recipients in `data/github_realtor_smoke_test_3.csv`.
- Production send must only use `data/github_realtor_production_450.csv`.
- Production trigger time is 2026-06-17 07:00 America/Los_Angeles, which is 2026-06-17 14:00 UTC.

Files to verify:
- `.github/workflows/realtor-outreach-claude-routine.yml`
- `scripts/github_realtor_outreach_sender.py`
- `data/github_realtor_smoke_test_3.csv`
- `data/github_realtor_production_450.csv`

Step-by-step routine:
1. Run `git status --short` and confirm the four files above exist.
2. Run `python3 -m py_compile scripts/github_realtor_outreach_sender.py`.
3. Parse `.github/workflows/realtor-outreach-claude-routine.yml` enough to confirm:
   - it has `workflow_dispatch`.
   - it has schedule cron `0 14 17 6 *`.
   - it has the date guard `2026-06-17`.
   - scheduled mode uses `data/github_realtor_production_450.csv`.
   - scheduled expected count is `450`.
   - manual smoke default uses `data/github_realtor_smoke_test_3.csv`.
   - manual smoke expected count is `3`.
4. Verify CSV counts and uniqueness:
   - `data/github_realtor_smoke_test_3.csv` has exactly 3 rows and 3 unique nonempty emails.
   - `data/github_realtor_production_450.csv` has exactly 450 rows and 450 unique nonempty emails.
   - the two CSVs have zero email overlap.
5. Verify GitHub CLI auth has workflow permission by running `gh auth status`.
6. Verify the repository has these secrets configured. Do not print secret values:
   - `OUTLOOK_TOKEN_JSON` is required.
   - `OUTLOOK_CLIENT_ID` is optional.
   - `OUTLOOK_TENANT_ID` is optional.
   Use `gh secret list` and report only names present/missing.
7. If `OUTLOOK_TOKEN_JSON` is missing, stop and report the exact command Malcolm must run:
   `gh secret set OUTLOOK_TOKEN_JSON < ~/.outlook-email-token.json`
8. If secrets are ready and the workflow file is committed/pushed, run a smoke test:
   `gh workflow run realtor-outreach-claude-routine.yml -f mode=smoke -f recipient_csv=data/github_realtor_smoke_test_3.csv -f expected_count=3 -f send_delay_seconds=4`
9. Identify the new run with `gh run list --workflow realtor-outreach-claude-routine.yml --limit 5`, wait for completion with `gh run watch`, then fetch logs with `gh run view --log`.
10. PASS only if logs contain `RESULT PASS` and `sent_count": 3`.
11. After smoke PASS, verify the scheduled trigger exists for 14:00 UTC in the workflow and report that GitHub Actions owns the 7 AM Pacific trigger.
12. Final response must include:
   - workflow file path
   - smoke run id and conclusion
   - exact RESULT line from logs
   - whether production schedule is armed
   - any blockers

If any step fails, do not claim readiness. Report the blocker and exact fix.
