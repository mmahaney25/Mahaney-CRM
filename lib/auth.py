"""MSAL authentication wrapper — token acquire, cache, and refresh."""

import json
import os
import sys
from pathlib import Path

import msal

# Defaults — override via environment variables
CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
AUTHORITY = os.environ.get("AZURE_AUTHORITY", "https://login.microsoftonline.com/common")
CACHE_PATH = Path(os.environ.get("MSAL_CACHE_PATH", ".msal_cache.bin"))

SCOPES = ["Mail.Read", "Mail.Send", "Files.ReadWrite"]

# Module-level cache so we authenticate once per run, not once per pipeline
_cached_token: str | None = None


def _build_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if CACHE_PATH.exists():
        try:
            data = CACHE_PATH.read_text()
            if data.strip():
                cache.deserialize(data)
                print("  [auth] Loaded token cache from disk.", file=sys.stderr)
            else:
                print("  [auth] Token cache file is empty — starting fresh.", file=sys.stderr)
        except Exception as e:
            print(f"  [auth] WARNING: Could not read token cache: {e}", file=sys.stderr)
    else:
        print("  [auth] No token cache found — will authenticate from scratch.", file=sys.stderr)
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        try:
            CACHE_PATH.write_text(cache.serialize())
            print("  [auth] Token cache saved to disk.", file=sys.stderr)
        except Exception as e:
            print(f"  [auth] WARNING: Could not save token cache: {e}", file=sys.stderr)


def get_token(scopes: list[str] | None = None) -> str:
    """Acquire a valid access token, using cache when possible.

    Always requests the full scope set (Mail.Read + Mail.Send + Files.ReadWrite)
    so the token works across all pipelines. The scopes parameter is ignored —
    kept for call-site compatibility.

    Returns the raw Bearer token string.
    """
    global _cached_token
    if _cached_token:
        return _cached_token

    if not CLIENT_ID:
        print("ERROR: Set AZURE_CLIENT_ID environment variable.", file=sys.stderr)
        sys.exit(1)

    cache = _build_cache()

    app = msal.PublicClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        token_cache=cache,
    )

    # Try silent acquisition first (cached / refresh token)
    accounts = app.get_accounts()
    if accounts:
        print(f"  [auth] Found {len(accounts)} cached account(s). Trying silent acquisition...", file=sys.stderr)
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_cache(cache)
            _cached_token = result["access_token"]
            print("  [auth] Silent acquisition succeeded — no login needed.", file=sys.stderr)
            return _cached_token
        # Log why silent acquisition failed
        if result:
            error = result.get("error", "unknown")
            desc = result.get("error_description", "no description")
            print(f"  [auth] Silent acquisition failed: {error} — {desc}", file=sys.stderr)
        else:
            print("  [auth] Silent acquisition returned None — token may be expired.", file=sys.stderr)
    else:
        print("  [auth] No cached accounts found in token cache.", file=sys.stderr)

    # Fall back to device-code flow
    print("  [auth] Starting device-code login flow...", file=sys.stderr)
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        print(f"ERROR: Could not create device flow: {flow}", file=sys.stderr)
        sys.exit(1)

    print(flow["message"])  # tells user to open browser and enter code
    result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        print(f"ERROR: Authentication failed: {result.get('error_description', result)}", file=sys.stderr)
        sys.exit(1)

    _save_cache(cache)
    _cached_token = result["access_token"]
    return _cached_token
