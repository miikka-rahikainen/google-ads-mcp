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

"""Unit tests for the allowed-domain restriction of the hosted server."""

import os
import unittest
from unittest.mock import AsyncMock, patch

from fastmcp.server.auth.auth import AccessToken
from fastmcp.server.auth.providers.google import GoogleProvider
from key_value.aio.stores.memory import MemoryStore

from ads_mcp.domain_restriction import (
    ALLOWED_DOMAINS_ENV_VAR,
    DomainRestrictedGoogleProvider,
    get_allowed_domains,
    is_allowed_identity,
)

ALLOWED = ("dagmar.fi",)


def _claims(email="user@dagmar.fi", verified="true", hd="dagmar.fi"):
    user_data = {"hd": hd} if hd is not None else {}
    return {
        "email": email,
        "email_verified": verified,
        "google_user_data": user_data or None,
    }


class TestIsAllowedIdentity(unittest.TestCase):

    def test_accepts_verified_workspace_account(self):
        self.assertTrue(is_allowed_identity(_claims(), ALLOWED))

    def test_accepts_boolean_verified_and_mixed_case(self):
        claims = _claims(email="User@Dagmar.FI", verified=True, hd="Dagmar.fi")
        self.assertTrue(is_allowed_identity(claims, ALLOWED))

    def test_rejects_other_domain(self):
        claims = _claims(email="user@gmail.com", hd=None)
        self.assertFalse(is_allowed_identity(claims, ALLOWED))

    def test_rejects_lookalike_domain(self):
        for email in ("user@notdagmar.fi", "user@dagmar.fi.evil.com"):
            claims = _claims(email=email, hd=email.split("@")[1])
            self.assertFalse(is_allowed_identity(claims, ALLOWED), email)

    def test_rejects_unverified_email(self):
        for verified in ("false", False, None):
            claims = _claims(verified=verified)
            self.assertFalse(is_allowed_identity(claims, ALLOWED))

    def test_rejects_consumer_account_with_company_email(self):
        # A consumer Google account registered with a company address has no hd.
        self.assertFalse(is_allowed_identity(_claims(hd=None), ALLOWED))

    def test_rejects_mismatched_hosted_domain(self):
        self.assertFalse(is_allowed_identity(_claims(hd="other.fi"), ALLOWED))

    def test_rejects_missing_claims(self):
        self.assertFalse(is_allowed_identity(None, ALLOWED))
        self.assertFalse(is_allowed_identity({}, ALLOWED))
        self.assertFalse(is_allowed_identity({"email": ""}, ALLOWED))


class TestGetAllowedDomains(unittest.TestCase):

    def test_defaults_to_dagmar(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(ALLOWED_DOMAINS_ENV_VAR, None)
            self.assertEqual(get_allowed_domains(), ("dagmar.fi",))

    def test_blank_value_falls_back_to_default(self):
        with patch.dict(os.environ, {ALLOWED_DOMAINS_ENV_VAR: " , "}):
            self.assertEqual(get_allowed_domains(), ("dagmar.fi",))

    def test_parses_list(self):
        with patch.dict(
            os.environ, {ALLOWED_DOMAINS_ENV_VAR: "Dagmar.fi, @example.com"}
        ):
            self.assertEqual(
                get_allowed_domains(), ("dagmar.fi", "example.com")
            )


class TestDomainRestrictedGoogleProvider(unittest.IsolatedAsyncioTestCase):

    def _provider(self, allowed_domains=ALLOWED):
        return DomainRestrictedGoogleProvider(
            allowed_domains=allowed_domains,
            client_id="test-client-id",
            client_secret="test-client-secret",
            base_url="http://localhost:8080",
            jwt_signing_key="test-signing-key-with-enough-entropy",
            client_storage=MemoryStore(),
        )

    def _token(self, claims):
        return AccessToken(token="t", client_id="c", scopes=[], claims=claims)

    async def test_allows_dagmar_account(self):
        token = self._token(_claims())
        with patch.object(
            GoogleProvider, "load_access_token", AsyncMock(return_value=token)
        ):
            self.assertIs(await self._provider().load_access_token("x"), token)

    async def test_rejects_other_account(self):
        token = self._token(_claims(email="someone@gmail.com", hd=None))
        with patch.object(
            GoogleProvider, "load_access_token", AsyncMock(return_value=token)
        ):
            self.assertIsNone(await self._provider().load_access_token("x"))

    async def test_passes_through_invalid_token(self):
        with patch.object(
            GoogleProvider, "load_access_token", AsyncMock(return_value=None)
        ):
            self.assertIsNone(await self._provider().load_access_token("x"))

    def test_adds_hosted_domain_hint(self):
        params = self._provider()._extra_authorize_params
        self.assertEqual(params.get("hd"), "dagmar.fi")

    def test_no_hint_for_multiple_domains(self):
        params = self._provider(
            ("dagmar.fi", "example.com")
        )._extra_authorize_params
        self.assertNotIn("hd", params)


if __name__ == "__main__":
    unittest.main()
