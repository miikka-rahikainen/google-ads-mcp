# Copyright 2026 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Restricts the hosted server to Google accounts of allowed Workspace domains."""

import logging
import os
from typing import Any, Mapping

from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider

logger = logging.getLogger(__name__)

ALLOWED_DOMAINS_ENV_VAR = "GOOGLE_ADS_MCP_ALLOWED_DOMAINS"
DEFAULT_ALLOWED_DOMAINS = ("dagmar.fi",)


def get_allowed_domains() -> tuple[str, ...]:
    """Returns the allowed domains from the environment, or the default.

    A blank value falls back to the default so that a misconfigured
    deployment never ends up open to every Google account.
    """
    raw = os.environ.get(ALLOWED_DOMAINS_ENV_VAR, "")
    domains = tuple(
        d.strip().lower().lstrip("@") for d in raw.split(",") if d.strip()
    )
    return domains or DEFAULT_ALLOWED_DOMAINS


def _is_true(value: Any) -> bool:
    # tokeninfo returns "true" as a string, userinfo returns a boolean.
    return value is True or (isinstance(value, str) and value.lower() == "true")


def is_allowed_identity(
    claims: Mapping[str, Any] | None, allowed_domains: tuple[str, ...]
) -> bool:
    """Checks that the token belongs to a verified account of an allowed domain.

    Both the e-mail domain and the Workspace hosted domain (``hd``) must match.
    ``hd`` is only present for accounts managed by a Google Workspace, so a
    consumer Google account registered with a company address is rejected.
    Missing data fails closed.
    """
    if not claims:
        return False

    email = (claims.get("email") or "").strip().lower()
    _, at, domain = email.rpartition("@")
    if not at or domain not in allowed_domains:
        return False

    if not _is_true(claims.get("email_verified")):
        return False

    user_data = claims.get("google_user_data") or {}
    hosted_domain = (user_data.get("hd") or "").strip().lower()
    return hosted_domain == domain


class DomainRestrictedGoogleProvider(GoogleProvider):
    """GoogleProvider that only accepts accounts of the allowed domains."""

    def __init__(self, *, allowed_domains: tuple[str, ...], **kwargs: Any):
        if len(allowed_domains) == 1:
            # Hint Google's account chooser to the company domain. This is only
            # a convenience; the check in load_access_token is what enforces it.
            extra = dict(kwargs.pop("extra_authorize_params", None) or {})
            extra.setdefault("hd", allowed_domains[0])
            kwargs["extra_authorize_params"] = extra
        super().__init__(**kwargs)
        self._allowed_domains = allowed_domains

    async def load_access_token(self, token: str) -> AccessToken | None:  # type: ignore[override]
        access_token = await super().load_access_token(token)
        if access_token is None:
            return None
        if not is_allowed_identity(access_token.claims, self._allowed_domains):
            logger.warning(
                "Rejected access token for an account outside the allowed domains."
            )
            return None
        return access_token
