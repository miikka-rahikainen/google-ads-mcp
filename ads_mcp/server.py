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

"""Entry point for the MCP server."""

from ads_mcp.coordinator import mcp

# The following imports are necessary to register the resources with the `mcp`
# object, even though they are not directly used in this file.
# Tools are loaded dynamically via reflection in coordinator.py.
# The `# noqa: F401` comment tells the linter to ignore the "unused import"
# warning.
from ads_mcp.resources import (
    discovery,
    metrics,
    release_notes,
    segments,
)  # noqa: F401


import os
from starlette.responses import JSONResponse
from ads_mcp.hosted_config import is_hosted, validate_hosted_configuration


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    """Liveness only; no account or credential information."""
    return JSONResponse({"status": "ok"})


def run_server() -> None:
    validate_hosted_configuration()
    _CLIENT_ID = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_ID")
    _CLIENT_SECRET = os.environ.get("GOOGLE_ADS_MCP_OAUTH_CLIENT_SECRET")
    port = int(os.environ.get("PORT", "8080"))

    if is_hosted() or (_CLIENT_ID and _CLIENT_SECRET):
        mcp.run(
            transport="streamable-http",
            port=port,
            host="0.0.0.0",
            stateless_http=True,
            json_response=True,
            show_banner=False,
            path="/mcp",
            host_origin_protection=True,
            allowed_hosts=[
                "google-ads-mcp.dagmar.app",
                os.environ.get("GOOGLE_ADS_MCP_HTTP_HOST", "localhost"),
            ],
            allowed_origins=["https://google-ads-mcp.dagmar.app"],
            uvicorn_config={
                "access_log": False,
                "timeout_graceful_shutdown": 8,
                "timeout_keep_alive": 5,
                "proxy_headers": False,
            },
        )
    else:
        mcp.run()


if __name__ == "__main__":
    run_server()
