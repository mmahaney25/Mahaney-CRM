"""4-agent outreach generation pipeline.

Three of the four agents are pure Python (deterministic). Only the Industry
Reviewer makes an Anthropic API call. This makes template fidelity
architecturally enforceable and most of the pipeline immune to API errors.

See docs/prompt.md "Pipeline Rules (Hard Constraints)" — each rule is
enforced by a specific code path cited in the comments below.
"""

import json
import os
import time
from dataclasses import dataclass

from anthropic import Anthropic, APIStatusError, APIConnectionError, APITimeoutError

from lib.template_io import load_template


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODEL = "claude-sonnet-4-5"
TEMPERATURE = 0
MAX_REVISION_LOOPS = 2  # Enforces R7

# Enforces R5: retries exhaust with bounded backoff before escalation.
_RETRY_STATUS_CODES = {429, 500, 502, 503, 504, 529}
_RETRY_WAITS = [1, 2, 4, 8, 16, 32, 60, 60]  # 8 attempts, ~3 min worst-case
_REQUEST_TIMEOUT_SEC = 60.0


# ---------------------------------------------------------------------------
# Legal-suffix normalization (R2)
# ---------------------------------------------------------------------------

LEGAL_SUFFIXES = [
    ", Inc.", " Inc.", ", Inc", " Inc",
    ", LLC", " LLC",
    ", Ltd.", " Ltd.", ", Ltd", " Ltd",
    ", Co.", " Co.",
    ", Corp.", " Corp.", ", Corporation", " Corporation",
    ", PBC", " PBC",
    ", P.C.", " P.C.", ", PC", " PC",
    ", LP", " LP", ", LLP", " LLP",
    ", GmbH", " GmbH",
    ", S.A.", " S.A.", ", SA", " SA",
    ", Pte Ltd", " Pte Ltd", ", Pty Ltd", " Pty Ltd",
    ", Sdn Bhd", " Sdn Bhd",
]
# Sort longest-first so ", Inc." wins over ", Inc"
_SORTED_SUFFIXES = sorted(LEGAL_SUFFIXES, key=len, reverse=True)


def strip_legal_suffix(company: str) -> str:
    """Remove one trailing legal-entity suffix if present. R2 enforcement."""
    for suffix in _SORTED_SUFFIXES:
        if company.lower().endswith(suffix.lower()):
            return company[:-len(suffix)].rstrip()
    return company


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class GenerateResult:
    body: str | None        # wire-format body (literal \n), None on ESCALATE
    action: str             # "FINALIZE" or "ESCALATE"
    loops: int              # which loop ended the run (0, 1, or 2)
    reason: str | None = None  # non-None only on ESCALATE


# ---------------------------------------------------------------------------
# Agent 1 — Drafter (pure Python, R1 + R2 + R3)
# ---------------------------------------------------------------------------

def drafter(first_name: str, company: str) -> dict:
    """Substitute {first_name} and normalized {company} into the canonical template.
    Zero LLM calls. Zero judgment. Deterministic."""
    subject, body_template = load_template()
    company_norm = strip_legal_suffix(company)
    body = (
        body_template
        .replace("{first_name}", first_name)
        .replace("{company}", company_norm)
    )
    return {"subject": subject, "body": body}


def _expected_variants(first_name: str, company: str) -> tuple[dict, dict]:
    """Return the two body strings Auditor accepts: normalized company, or
    original (unstripped) company. The Reviewer's only legitimate edit is
    switching between these two — Auditor must allow either."""
    subject, body_template = load_template()
    normalized = strip_legal_suffix(company)
    body_norm = (
        body_template
        .replace("{first_name}", first_name)
        .replace("{company}", normalized)
    )
    body_orig = (
        body_template
        .replace("{first_name}", first_name)
        .replace("{company}", company)
    )
    return (
        {"subject": subject, "body": body_norm},
        {"subject": subject, "body": body_orig},
    )


# ---------------------------------------------------------------------------
# Agent 2 — Template Auditor (pure Python, R1 + R4)
# ---------------------------------------------------------------------------

def auditor(draft: dict, first_name: str, company: str) -> dict:
    """Verify draft equals an acceptable expected body. Zero LLM calls.
    Accepts two forms: normalized company (default), or original company
    (after Reviewer-approved suffix restore)."""
    norm_expected, orig_expected = _expected_variants(first_name, company)
    if draft == norm_expected or draft == orig_expected:
        return {"status": "PASS", "edits": []}

    # Any other state is a tamper or bug. Reset to the normalized form.
    edits = []
    if draft["subject"] != norm_expected["subject"]:
        edits.append({
            "field": "subject",
            "issue": "subject differs from canonical",
            "old": draft["subject"],
            "new": norm_expected["subject"],
        })
    if draft["body"] != norm_expected["body"] and draft["body"] != orig_expected["body"]:
        edits.append({
            "field": "body",
            "issue": "body differs from expected substitution of canonical template",
            "old": draft["body"],
            "new": norm_expected["body"],
        })
    return {"status": "FLAG", "edits": edits}


# ---------------------------------------------------------------------------
# Agent 3 — Industry Reviewer (LLM, scoped to company plausibility only)
# ---------------------------------------------------------------------------

REVIEWER_SYS = """You are a company-name plausibility reviewer. You evaluate ONE thing: whether the company name, as currently substituted into the email body, reads plausibly as a real company in the recipient's industry context.

You will receive JSON with:
  - body: the email body (line breaks shown as literal \\n)
  - company_in_body: the exact company substring currently in the body
  - original_company: the unstripped company name from the spreadsheet
  - industry: the recipient's industry (may be blank)
  - first_name: the recipient's first name

Your job is narrowly scoped. PASS unless ONE specific problem applies:
  The `company_in_body` reads as a generic service category, practice area, or descriptive phrase (e.g., "Integrated Decision Engineering Analysis", "Strategic Business Solutions") rather than a distinct company/brand. If `original_company` contains a trailing legal suffix (", Inc.", " LLC", ", Ltd.", etc.) that gave the name clarity, FLAG and propose restoring the original form.

If PASS, return exactly:
{ "status": "PASS", "edits": [] }

If FLAG, return exactly one edit with the exact substring to replace and the exact replacement:
{ "status": "FLAG", "edits": [
  { "field": "body", "issue": "<brief reason>", "old": "<company_in_body exactly>", "new": "<original_company exactly>" }
] }

STRICT SCOPE — You MUST NOT flag any of the following, ever:
  - Grammar, punctuation, or capitalization choices (periods, question marks, commas).
  - Stylistic preferences or tone.
  - Wording of the greeting, affiliation, ask, or sign-off.
  - Anything that isn't specifically the company name reading as a generic category.
  - Template content in general — the template is sacred and not your concern.

If the company_in_body reads as a real company (even a small or unusual one), PASS.

Return only the JSON object — no prose, no markdown code fences."""


def _call_reviewer(client: Anthropic, user_content: str) -> str:
    """Call Anthropic with robust retries (R5)."""
    last_exc: Exception | None = None
    for attempt, wait in enumerate(_RETRY_WAITS):
        try:
            resp = client.messages.create(
                model=MODEL,
                max_tokens=800,
                temperature=TEMPERATURE,
                system=REVIEWER_SYS,
                messages=[{"role": "user", "content": user_content}],
                timeout=_REQUEST_TIMEOUT_SEC,
            )
            return resp.content[0].text.strip()
        except APIStatusError as e:
            if e.status_code in _RETRY_STATUS_CODES and attempt < len(_RETRY_WAITS) - 1:
                print(f"  [gen] Anthropic {e.status_code} — retry {attempt + 1}/{len(_RETRY_WAITS)} in {wait}s")
                time.sleep(wait)
                last_exc = e
                continue
            last_exc = e
            break
        except (APIConnectionError, APITimeoutError) as e:
            if attempt < len(_RETRY_WAITS) - 1:
                print(f"  [gen] Anthropic connection/timeout — retry {attempt + 1}/{len(_RETRY_WAITS)} in {wait}s")
                time.sleep(wait)
                last_exc = e
                continue
            last_exc = e
            break
    raise RuntimeError(f"Anthropic retries exhausted: {type(last_exc).__name__}: {last_exc}")


def _parse_json_strict(text: str) -> dict:
    """Parse Claude JSON, tolerating optional ```json fence. Raises on bad JSON."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`").lstrip()
        if t.lower().startswith("json"):
            t = t[4:].lstrip()
        if t.endswith("```"):
            t = t[:-3].rstrip()
    return json.loads(t)


def reviewer(client: Anthropic, draft: dict, first_name: str, company: str, industry: str) -> dict:
    """The only LLM call in the pipeline. Returns {status, edits}."""
    company_in_body = strip_legal_suffix(company)  # what's currently in the drafted body
    payload = {
        "body": draft["body"],
        "company_in_body": company_in_body,
        "original_company": company,
        "industry": industry,
        "first_name": first_name,
    }
    raw = _call_reviewer(client, json.dumps(payload))
    result = _parse_json_strict(raw)
    # Normalize shape
    status = result.get("status", "PASS")
    edits = result.get("edits", []) if status == "FLAG" else []
    return {"status": status, "edits": edits}


# ---------------------------------------------------------------------------
# Agent 4 — Arbiter (pure Python, R3 + R7)
# ---------------------------------------------------------------------------

def arbiter(
    draft: dict,
    auditor_result: dict,
    reviewer_result: dict,
    loop_count: int,
) -> dict:
    """Apply edits or finalize/escalate. Zero LLM calls. Zero judgment."""
    if auditor_result["status"] == "PASS" and reviewer_result["status"] == "PASS":
        return {"action": "FINALIZE", "message": draft}

    if loop_count >= MAX_REVISION_LOOPS:
        reasons = []
        for e in list(auditor_result.get("edits", [])) + list(reviewer_result.get("edits", [])):
            reasons.append(e.get("issue", "(unspecified)"))
        return {
            "action": "ESCALATE",
            "message": {"subject": "", "body": ""},
            "reason": "; ".join(reasons) or "unresolved flags after max loops",
        }

    subject = draft["subject"]
    body = draft["body"]
    for e in auditor_result.get("edits", []):
        if e["field"] == "subject":
            subject = subject.replace(e["old"], e["new"], 1)
        else:
            body = body.replace(e["old"], e["new"], 1)
    for e in reviewer_result.get("edits", []):
        if e["field"] == "body":
            body = body.replace(e["old"], e["new"], 1)
        # Reviewer is not allowed to touch subject — per prompt, but we silently
        # drop any such edit here rather than apply it. Enforces scope.
    return {"action": "REVISE", "message": {"subject": subject, "body": body}}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _client() -> Anthropic:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set. Add it to .env and re-run.")
    return Anthropic(api_key=key)


def generate_body(
    first_name: str,
    company: str,
    industry: str = "",
) -> GenerateResult:
    """Run the 4-agent pipeline. See docs/prompt.md for rules R1-R7."""
    # R1 + R6: deterministic Python Drafter.
    draft = drafter(first_name, company)
    print(f"  [gen] Drafter OK — subject={draft['subject']!r}")

    # R6: deterministic Auditor self-check of Drafter output.
    init_audit = auditor(draft, first_name, company)
    if init_audit["status"] != "PASS":
        # Shouldn't happen — Drafter is Python. If it does, fix it fast.
        return GenerateResult(
            body=None, action="ESCALATE", loops=0,
            reason=f"Drafter produced a body Auditor rejected: {init_audit['edits']}",
        )
    print(f"  [gen] Auditor (initial) PASS")

    client = _client()

    for loop in range(MAX_REVISION_LOOPS + 1):  # 0, 1, 2
        # Reviewer is the only LLM call.
        try:
            rev = reviewer(client, draft, first_name, company, industry)
        except (json.JSONDecodeError, RuntimeError) as e:
            return GenerateResult(
                body=None, action="ESCALATE", loops=loop,
                reason=f"Reviewer error: {type(e).__name__}: {e}",
            )

        # Auditor re-verifies post-edit draft matches allowed forms.
        aud = auditor(draft, first_name, company)

        print(f"  [gen] Loop {loop}: Auditor={aud['status']} Reviewer={rev['status']}")
        for e in rev.get("edits", []):
            print(f"  [gen]   Reviewer flag: {e.get('issue')!r} old={e.get('old')!r} new={e.get('new')!r}")

        # Arbiter decides.
        arb = arbiter(draft, aud, rev, loop)
        action = arb["action"]
        if action == "FINALIZE":
            msg = arb["message"]
            return GenerateResult(body=msg["body"], action="FINALIZE", loops=loop)
        if action == "ESCALATE":
            return GenerateResult(
                body=None, action="ESCALATE", loops=loop,
                reason=arb.get("reason", "(unspecified)"),
            )
        # REVISE: update draft and continue.
        draft = arb["message"]

    # Unreachable — Arbiter escalates on loop 2.
    return GenerateResult(
        body=None, action="ESCALATE", loops=MAX_REVISION_LOOPS,
        reason="Loop cap exceeded without resolution",
    )
