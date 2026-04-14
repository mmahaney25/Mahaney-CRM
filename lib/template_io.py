"""Parse the canonical outreach template (docs/page-specs/Template.md).

Returns (subject, body_template) where body_template uses the literal two-character
sequence `\\n` as its line-break marker, matching the pipeline's spacing convention.
"""

import re
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "docs" / "page-specs" / "Template.md"


def load_template() -> tuple[str, str]:
    """Return (subject, body_template_wire) parsed live from Template.md.

    Raises RuntimeError with a clear message if either section cannot be found.
    """
    text = TEMPLATE_PATH.read_text()

    subj_match = re.search(r"\*\*Subject:\*\*\s*(.+?)\s*$", text, flags=re.MULTILINE)
    if not subj_match:
        raise RuntimeError(
            f"Could not find a '**Subject:**' line in {TEMPLATE_PATH}"
        )
    subject = subj_match.group(1).strip()

    body_match = re.search(
        r"(Hi \{first_name\},.*?Best,\s*\nMalcolm)\s*$",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    if not body_match:
        raise RuntimeError(
            f"Could not find body template (Hi {{first_name}}, ... Best,\\nMalcolm) in {TEMPLATE_PATH}"
        )
    body_real_newlines = body_match.group(1)
    body_wire = body_real_newlines.replace("\n", "\\n")

    return subject, body_wire
