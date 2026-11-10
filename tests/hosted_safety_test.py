"""Deterministic security and deployed-storage compatibility regressions."""

import asyncio
import hashlib
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from cryptography.fernet import Fernet
from fastmcp import FastMCP
from fastmcp.server.auth.oauth_proxy.proxy import derive_jwt_key
from key_value.aio._utils.managed_entry import ManagedEntry
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.wrappers.encryption.fernet import FernetEncryptionWrapper

from ads_mcp.auth_storage import create_client_storage
from ads_mcp.hosted_config import validate_hosted_configuration
from ads_mcp.legacy_firestore import (
    INDEX_COLLECTION,
    LegacyFileTreeFirestoreStore,
    physical_id,
    physical_path,
)


class HostedSafetyTest(unittest.IsolatedAsyncioTestCase):
    async def test_oauth_discovery_preserves_live_issuer_and_pkce(self):
        from ads_mcp.domain_restriction import DomainRestrictedGoogleProvider
        from starlette.testclient import TestClient

        provider = DomainRestrictedGoogleProvider(
            allowed_domains=("dagmar.fi",),
            client_id="synthetic-client",
            client_secret="synthetic-secret",
            base_url="https://google-ads-mcp.dagmar.app",
            jwt_signing_key="synthetic-signing-key-with-sufficient-material",
            client_storage=MemoryStore(),
        )
        server = FastMCP("synthetic-oauth", auth=provider)
        app = server.http_app(transport="streamable-http", stateless_http=True)
        with TestClient(app) as client:
            response = client.get("/.well-known/oauth-authorization-server")
            self.assertEqual(response.status_code, 200)
            metadata = response.json()
            self.assertEqual(
                metadata["issuer"], "https://google-ads-mcp.dagmar.app/"
            )
            self.assertTrue(
                metadata["authorization_response_iss_parameter_supported"]
            )
            self.assertEqual(
                metadata["code_challenge_methods_supported"], ["S256"]
            )
            self.assertEqual(client.post("/mcp").status_code, 401)

    async def test_inventory_cannot_enable_upstream_mutations(self):
        from ads_mcp.coordinator import initialize_and_mount_tools
        from ads_mcp.config import ToolsConfig

        with patch(
            "ads_mcp.config.ToolsConfig.load", return_value=ToolsConfig()
        ):
            with patch.dict("os.environ", {"GOOGLE_ADS_MCP_MODE": "hosted"}):
                parent = FastMCP("read-only-test")
                initialize_and_mount_tools(parent)
        self.assertEqual(
            {tool.name for tool in await parent.list_tools()},
            {
                "customers_list_accessible_customers",
                "search_search",
                "metadata_get_resource_metadata",
            },
        )

    async def test_hosted_never_falls_back_to_service_account(self):
        from ads_mcp.utils import _create_credentials

        with patch.dict(
            "os.environ", {"GOOGLE_ADS_MCP_MODE": "hosted"}, clear=True
        ):
            with patch(
                "fastmcp.server.dependencies.get_access_token",
                return_value=None,
            ):
                with patch("google.auth.default") as adc:
                    with self.assertRaises(PermissionError):
                        _create_credentials()
                    adc.assert_not_called()

    async def test_hosted_missing_secrets_fails_closed(self):
        with patch.dict(
            "os.environ", {"GOOGLE_ADS_MCP_MODE": "hosted"}, clear=True
        ):
            with self.assertRaises(ValueError):
                validate_hosted_configuration()

    async def test_legacy_encryption_uses_existing_key_precedence_and_salt(
        self,
    ):
        raw = MemoryStore()
        material = "synthetic-storage-secret"
        old = FernetEncryptionWrapper(
            key_value=raw,
            fernet=Fernet(
                derive_jwt_key(
                    high_entropy_material=material,
                    salt="fastmcp-storage-encryption-key",
                )
            ),
        )
        env = {
            "GOOGLE_ADS_MCP_STORAGE_TYPE": "memory",
            "GOOGLE_ADS_MCP_STORAGE_ENCRYPTION_KEY": material,
            "GOOGLE_ADS_MCP_JWT_SIGNING_KEY": "different-synthetic-jwt-secret",
        }
        with patch.dict("os.environ", env, clear=True):
            with patch(
                "key_value.aio.stores.memory.MemoryStore", return_value=raw
            ):
                new = create_client_storage()
        await old.put("old", {"synthetic": "old-session"})
        self.assertEqual(await new.get("old"), {"synthetic": "old-session"})
        await new.put("new", {"synthetic": "new-session"})
        self.assertEqual(await old.get("new"), {"synthetic": "new-session"})


class LegacyStorageTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.docs = {}
        docs = self.docs

        class Ref:
            def __init__(self, collection, key):
                self.address = collection, key

            async def get(self):
                return SimpleNamespace(to_dict=lambda: docs.get(self.address))

            async def set(self, value):
                docs[self.address] = value

            async def create(self, value):
                from google.api_core.exceptions import AlreadyExists

                if self.address in docs:
                    raise AlreadyExists("synthetic existing metadata")
                docs[self.address] = value

        client = MagicMock()
        client.collection.side_effect = lambda c: SimpleNamespace(
            document=lambda k: Ref(c, k)
        )
        self.store = LegacyFileTreeFirestoreStore(client=client)

    async def test_normalized_url_identity_expiry_writes_and_index(self):
        collection = "mcp-oauth-proxy-clients"
        key = "https://chatgpt.com/oauth/client"
        physical = "https:/chatgpt.com/oauth/client"
        self.assertEqual(physical_path(key, key=True), physical)
        key_id = "ft_" + hashlib.sha256(physical.encode()).hexdigest()
        collection_id = physical_id(collection)
        self.assertEqual(
            self.store._sanitize_collection_and_key(
                collection=collection, key=key
            ),
            (collection_id, key_id),
        )

        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        entry = ManagedEntry(
            value={"synthetic": "old-session"}, expires_at=expires
        )
        self.docs[collection_id, key_id] = (
            self.store._serialization_adapter.dump_dict(entry=entry)
        )
        self.assertEqual(
            await self.store.get(key, collection=collection), dict(entry.value)
        )
        self.assertGreater(
            (await self.store.ttl(key, collection=collection))[1], 3500
        )

        entry.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.docs[collection_id, key_id] = (
            self.store._serialization_adapter.dump_dict(entry=entry)
        )
        self.assertIsNone(await self.store.get(key, collection=collection))

        await self.store.put(
            key, {"synthetic": "new-session"}, collection=collection, ttl=3600
        )
        item = self.docs[collection_id, key_id]
        self.assertEqual(item["_legacy_key"], physical)
        self.assertEqual(
            await self.store.get(key, collection=collection),
            {"synthetic": "new-session"},
        )
        index = self.docs[INDEX_COLLECTION, collection_id]
        self.assertEqual(index["directory"], "/data/oauth/" + collection)

        await self.store.put_many(
            ["a", "b"], [{"n": 1}, {"n": 2}], collection=collection, ttl=60
        )
        for key, value in [("a", 1), ("b", 2)]:
            self.assertEqual(
                await self.store.get(key, collection=collection), {"n": value}
            )
            self.assertEqual(
                self.docs[collection_id, physical_id(key)]["_legacy_key"], key
            )

    async def test_legacy_unsafe_paths_fail(self):
        for value in ("../escape", "/absolute", "nul\x00key"):
            with self.assertRaises(ValueError):
                physical_path(value, key=True)
