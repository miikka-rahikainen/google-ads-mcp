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

"""Module declaring the singleton MCP instance.

The singleton allows other modules to register their tools with the same MCP
server using `@mcp.tool` annotations, thereby 'coordinating' the bootstrapping
of the server.
"""

import os
from typing import Any
from fastmcp import FastMCP
from ads_mcp.auth_storage import create_client_storage
from ads_mcp.domain_restriction import (
    DomainRestrictedGoogleProvider,
    get_allowed_domains,
)

_CLIENT_ID = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID")
_CLIENT_SECRET = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
_BASE_URL = os.environ.get("GOOGLE_ADS_MCP_BASE_URL", "http://localhost:8080")
_JWT_SIGNING_KEY = os.environ.get("GOOGLE_ADS_MCP_JWT_SIGNING_KEY")

if _CLIENT_ID and _CLIENT_SECRET:
    client_storage = create_client_storage()
    provider_kwargs: dict[str, Any] = {
        "client_id": _CLIENT_ID,
        "client_secret": _CLIENT_SECRET,
        "base_url": _BASE_URL,
        "required_scopes": [
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/adwords",
        ],
    }
    if _JWT_SIGNING_KEY:
        provider_kwargs["jwt_signing_key"] = _JWT_SIGNING_KEY
    if client_storage is not None:
        provider_kwargs["client_storage"] = client_storage

    auth = DomainRestrictedGoogleProvider(
        allowed_domains=get_allowed_domains(), **provider_kwargs
    )
    mcp = FastMCP("Google Ads Server", auth=auth)
else:
    mcp = FastMCP("Google Ads Server")


def initialize_and_mount_tools(parent_mcp: FastMCP) -> None:
    """Loads the tools configuration and dynamically mounts the tools sub-servers."""
    from ads_mcp.config import ToolsConfig
    import importlib

    config = ToolsConfig.load()
    approved_tools = (
        ("customers", "core", "customers_mcp", "list_accessible_customers"),
        (
            "metadata",
            "get_resource_metadata",
            "metadata_mcp",
            "get_resource_metadata",
        ),
        ("search", "search", "search_mcp", "search"),
    )
    for category, module_name, server_name, approved_name in approved_tools:
        if not config.is_namespace_enabled(category):
            continue
        if not config.is_tool_enabled(category, approved_name):
            continue

        module = importlib.import_module(f"ads_mcp.tools.{module_name}")
        sub_mcp = getattr(module, server_name)

        # Filter disabled tools inside the sub-server before mounting
        tool_names = []
        for key, val in sub_mcp.local_provider._components.items():
            if key.startswith("tool:"):
                tool_names.append(val.name)

        for name in tool_names:
            if name != approved_name:
                sub_mcp.local_provider.remove_tool(name)

        # Determine prefix/namespace
        namespace_prefix = config.get_namespace_prefix(category)

        # Mount the sub-server
        parent_mcp.mount(sub_mcp, namespace=namespace_prefix or None)


# Automatically initialize and mount tools upon import
initialize_and_mount_tools(mcp)
