# Dagmar Google Ads

This plugin connects Codex and Claude Code to Dagmar's hosted, read-only Google Ads MCP service:

`https://google-ads-mcp.dagmar.app/mcp`

The package contains no Google Ads developer token, OAuth client secret, customer ID, or user credential. Each user completes Google OAuth after installation and receives only the Google Ads access granted to their own Google identity.

## First use

1. Install and enable the plugin in Codex or Claude Code.
2. Authenticate the `dagmar-google-ads` MCP connection when prompted.
3. Start with: `List the Google Ads accounts I can access.`

OAuth credentials are stored by the client and the hosted MCP service. Users normally authenticate once per client application and device.
