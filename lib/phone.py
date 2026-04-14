"""Shared phone number normalization utility."""

import re


def normalize_phone(raw: str) -> str:
    """Normalize a phone number to +1XXXXXXXXXX format.

    Handles common US formats: (555) 123-4567, 555-123-4567, 5551234567, etc.
    Returns the original with + prefix if the format is unrecognized.
    """
    digits = re.sub(r"[^\d]", "", raw)
    if len(digits) == 10:
        digits = "1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if raw.startswith("+"):
        return raw
    return f"+{digits}" if digits else ""
