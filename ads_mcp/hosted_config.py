"""Explicit hosted safety boundary; local stdio remains separately supported."""

import os
from urllib.parse import urlparse

CANONICAL_ORIGIN = "https://google-ads-mcp.dagmar.app"


def is_hosted() -> bool:
    mode = os.environ.get("GOOGLE_ADS_MCP_MODE", "local")
    if mode not in {"local", "hosted"}:
        raise ValueError("Invalid execution mode")
    return mode == "hosted"


def requires_user_credentials() -> bool:
    return is_hosted() or bool(
        os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID")
        or os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
    )


def validate_hosted_configuration() -> None:
    if not is_hosted():
        return
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        raise ValueError("Hosted storage must use the approved Native database")
    required = (
        "GOOGLE_ADS_MCP_OAUTH_CLIENT_ID",
        "GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET",
        "GOOGLE_ADS_MCP_JWT_SIGNING_KEY",
        "GOOGLE_ADS_MCP_STORAGE_ENCRYPTION_KEY",
        "GOOGLE_ADS_MCP_HTTP_HOST",
    )
    if any(not os.environ.get(key, "").strip() for key in required):
        raise ValueError("Hosted authentication configuration is incomplete")
    if os.environ.get("GOOGLE_ADS_MCP_BASE_URL") != CANONICAL_ORIGIN:
        raise ValueError("Hosted OAuth issuer must remain canonical")
    if (
        os.environ.get("GOOGLE_ADS_MCP_STORAGE_TYPE") != "firestore"
        or os.environ.get("GOOGLE_ADS_MCP_STORAGE_FIRESTORE_PROJECT")
        != "dagmar-mcp"
        or os.environ.get("GOOGLE_ADS_MCP_STORAGE_FIRESTORE_DATABASE")
        != "google-ads-mcp-cutover-north1-20261110"
        or os.environ.get("GOOGLE_ADS_MCP_STORAGE_LEGACY_PROFILE")
        != "filetree-passthrough"
        or os.environ.get(
            "GOOGLE_ADS_MCP_STORAGE_DISABLE_ENCRYPTION", ""
        ).lower()
        in {"true", "1", "yes"}
    ):
        raise ValueError(
            "Hosted storage must use encrypted migration Firestore"
        )
    host = os.environ["GOOGLE_ADS_MCP_HTTP_HOST"]
    if (
        urlparse("https://" + host).hostname != host
        or not host.endswith(".run.app")
        or any(c in host for c in "/:* ")
    ):
        raise ValueError("An exact Cloud Run hostname is required")
