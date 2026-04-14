# Outreach Generation — 4-Agent Pipeline

## Purpose

Generate outreach emails for the Outreach sheet. Three of the four agents are
pure Python (deterministic); only the Industry Reviewer makes an LLM call, and
its scope is narrowly constrained. This design makes template fidelity
architecturally enforceable and the pipeline robust to API failures.

---

## Pipeline Rules (Hard Constraints)

Every rule below has a specific code enforcement point, cited. These rules are
invariants of the system — if any rule is broken in code or practice, it's a
bug, not a stylistic preference.

**R1. The template body is sacred.** The body of every sent email equals the
canonical body in `docs/page-specs/Template.md` with exactly two substitutions:
`{first_name}` → the contact's first name, `{company}` → the contact's company
(after R2 normalization). No other changes are permitted by any pipeline
stage, for any reason.
→ Enforced by `pipelines/generate_pipeline.py:drafter` (deterministic Python
substitution) and `pipelines/generate_pipeline.py:auditor` (character-for-character
comparison against the expected substituted template).

**R2. The only allowed modification to `{company}` is legal-suffix stripping.**
The Drafter strips at most one trailing legal-entity suffix (`, Inc.`, `LLC`,
`Ltd.`, etc. — full list in code). The Reviewer may, in one specific case,
propose restoring the original unstripped name if the stripped form reads as
a generic service category. No other company edits are allowed.
→ Enforced by `pipelines/generate_pipeline.py:strip_legal_suffix` and the
narrowly-scoped Reviewer prompt.

**R3. Only the Arbiter modifies text.** The Drafter produces the initial text.
The Reviewer proposes edits as structured `{field, old, new}` JSON pairs; it
never rewrites the message. The Arbiter applies edits by exact string
replacement. No other agent ever writes text.
→ Enforced by `pipelines/generate_pipeline.py:arbiter` using `str.replace(old, new, 1)`.

**R4. No grammar, style, tone, or aesthetic judgment anywhere.** The pipeline
performs two types of check, and only these two: (a) mechanical template-fidelity
comparison (Auditor), and (b) company-name-vs-industry plausibility (Reviewer).
The Reviewer's prompt explicitly forbids flagging anything else, including
punctuation choices like the intentional period after `{company}`.
→ Enforced by the STRICT SCOPE section of `REVIEWER_SYS` in
`pipelines/generate_pipeline.py`.

**R5. Anthropic API failures never crash the pipeline.** Up to 8 retries with
exponential backoff (1s, 2s, 4s, 8s, 16s, 32s, 60s, 60s) on retryable errors
(429, 500, 502, 503, 504, 529, connection, timeout). If retries exhaust, the
generator returns a clean ESCALATE result. The send pipeline wraps the
generator in a try/except so any unexpected exception becomes a single-line
error message — never a Python traceback in the CLI.
→ Enforced by `pipelines/generate_pipeline.py:_call_reviewer` (retry loop) and
`pipelines/send_pipeline.py:send_row` (try/except around `generate_body`).

**R6. Deterministic by default.** Drafter, Auditor, and Arbiter are pure
Python — given the same inputs they produce byte-identical outputs. The only
non-deterministic step is the Reviewer's LLM call, which runs at temperature 0
against Claude Sonnet 4.5. At temp 0 with identical inputs, the Reviewer
should return consistent outputs; if it doesn't, re-running once typically
resolves the variance.
→ Enforced by architecture: three of four agents are Python functions with
no randomness.

**R7. Two-loop cap.** Maximum of 2 revision cycles per row. If after loop 2
any FLAG remains, the pipeline returns ESCALATE with a reason string and the
caller abandons the send. Runaway loops are impossible.
→ Enforced by `pipelines/generate_pipeline.py:arbiter` check on `loop_count >= MAX_REVISION_LOOPS`.

---

## Pipeline Overview

```
Row  →  Drafter (Python)  →  Auditor (Python, self-check)
             │
             └─→  Reviewer (LLM, company scope only)  ─→  Arbiter (Python)  ─→  generated_message
                                                              │
                                                              └─ (up to 2 revision loops) ──┐
                                                                                            │
                                                        If still flagged after loop 2 ──────┘
                                                        → ESCALATE: no send, reason logged
```

- Drafter, Auditor, Arbiter: Python functions, zero LLM calls, zero variance.
- Reviewer: one Claude Sonnet 4.5 call at temperature 0 per loop.
- Total API calls per row: 1–3 (usually 1; up to 3 if revisions happen).

## Shared Conventions

### Spacing marker
The pipeline uses the **literal two-character sequence `\n`** (backslash +
lowercase n) as its line-break marker in the `generated_message` cell. The
send step (`pipelines/send_pipeline.py:_render_newlines`) converts `\n` to
real newlines before handing the body to Microsoft Graph.

### Canonical subject
```
Fellow Badger Looking To Learn
```
Defined in `docs/page-specs/Template.md` line 9 and parsed live on every send
by `lib/template_io.py:load_template`. Never cached, never hardcoded in code.

### Canonical body template
Parsed live from `docs/page-specs/Template.md` on every send. Placeholders:
`{first_name}`, `{company}`. Line breaks encoded as literal `\n` after parsing.

### Input schema (per row)
```
{
  "first_name":   required — substituted into body
  "company":      required — substituted into body (after legal-suffix strip)
  "industry":     optional — Reviewer context only
}
```

---

## Agent 1 — Drafter (Python)

**Role.** Substitute `{first_name}` and normalized `{company}` into the
canonical template. Return `{"subject": ..., "body": ...}`.

**Rules enforced.** R1 (template fidelity), R2 (company normalization is the
only allowed transform), R6 (determinism).

**Implementation.** `pipelines/generate_pipeline.py:drafter`.

**Not an LLM call.** Pure string substitution. Zero API cost. Zero variance.

---

## Agent 2 — Template Auditor (Python)

**Role.** Verify the current draft is one of exactly two acceptable body
strings: the template with normalized company, or the template with original
(unstripped) company. Anything else FLAGs.

**Rules enforced.** R1 (catches any tamper), R4 (no style judgment — pure
string equality), R6 (determinism).

**Output shape.**
```
{ "status": "PASS" | "FLAG",
  "edits": [ { "field": "subject" | "body", "issue": string, "old": string, "new": string } ] }
```

**Implementation.** `pipelines/generate_pipeline.py:auditor`.

**Not an LLM call.** String comparison only.

---

## Agent 3 — Industry Reviewer (LLM — the only LLM in the pipeline)

**Role.** Check exactly one thing: whether the company name (as currently in
the body) reads as a plausible company in the recipient's industry, or
whether it reads as a generic service category that should have kept its
legal suffix.

**Rules enforced.** R2 (legitimate use of suffix restore), R4 (strictly no
style/grammar/tone feedback), R6 (runs at temperature 0).

**Inputs.**
```
{
  body:              the current body (literal \n line breaks),
  company_in_body:   the exact company substring currently in the body,
  original_company:  the unstripped company name from the sheet,
  industry:          recipient's industry (may be blank),
  first_name:        recipient's first name
}
```

**Output.** Same JSON shape as the Auditor. FLAG contains at most one edit,
and that edit swaps `company_in_body` for `original_company`.

**Strict scope (reinforced in the prompt).** The Reviewer MUST NOT flag
grammar, punctuation, capitalization, greeting wording, affiliation wording,
ask wording, sign-off, or anything that isn't "the stripped company name
reads as a generic category." If uncertain, PASS.

**Implementation.** `pipelines/generate_pipeline.py:reviewer` +
`REVIEWER_SYS`.

---

## Agent 4 — Arbiter (Python)

**Role.** Decide and apply.

- If Auditor and Reviewer both PASS → FINALIZE.
- Else if `loop_count < 2` → apply every edit via `str.replace(old, new, 1)`
  and return REVISE.
- Else (loop cap hit with outstanding flags) → ESCALATE with reason string.

**Rules enforced.** R3 (only agent that modifies text), R7 (loop cap).

**Output.** `{"action": "FINALIZE"|"REVISE"|"ESCALATE", "message": {...}, "reason"?: string}`.

**Implementation.** `pipelines/generate_pipeline.py:arbiter`.

**Not an LLM call.** Structured edit application.

---

## Escalation behavior

On ESCALATE, the pipeline writes nothing to the sheet and nothing is sent.
`send_row` prints a one-line reason and returns. The row remains in its
pre-generation state (empty Message cell) so the operator can intervene.

---

## Reliability & retries (R5 in detail)

The Reviewer's Anthropic call is the only failure point.

- Retryable errors: HTTP 429, 500, 502, 503, 504, 529; `APIConnectionError`;
  `APITimeoutError`.
- Retry waits: `1, 2, 4, 8, 16, 32, 60, 60` seconds — up to 8 attempts.
- Worst-case total wait before ESCALATE: ~3 minutes.
- Per-request timeout: 60 seconds.
- If retries exhaust, `generate_body` returns `GenerateResult(action="ESCALATE", reason="Anthropic retries exhausted: ...")`.
- `send_row` wraps the generator in `try/except Exception` (belt-and-suspenders) so no traceback can reach the CLI.

---

## Example end-to-end (Adam, Aston Educational Group, Education)

Inputs: `first_name="Adam"`, `company="Aston Educational Group"`, `industry="Education"`.

- **Drafter (Python):** returns
  ```json
  {"subject": "Fellow Badger Looking To Learn",
   "body": "Hi Adam,\n\nI hope you're having a good day! ... chat about Aston Educational Group. ..."}
  ```
- **Auditor (Python):** PASS. Draft equals the expected substituted template.
- **Reviewer (LLM):** PASS. `Aston Educational Group` reads as a real company in Education.
- **Arbiter (Python):** FINALIZE. Returns draft unchanged.
- **Send pipeline:** renders `\n` → real newlines, sets subject, sends via Graph.
