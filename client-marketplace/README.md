# Dagmar AI plugins

Local marketplace for the Dagmar Google Ads MCP plugin. The same plugin directory supports Codex and Claude Code.

## Codex

```sh
codex plugin marketplace add "/absolute/path/to/client-marketplace"
codex plugin add dagmar-google-ads@personal
```

Open a new Codex task after installation, then authenticate the plugin's MCP connection.

## Claude Code

```sh
claude plugin marketplace add "/absolute/path/to/client-marketplace"
claude plugin install dagmar-google-ads@personal --scope user
```

Start a new Claude Code session or run `/reload-plugins`, then authenticate through `/mcp` when prompted.

## Security model

- No Google Ads or OAuth secrets are included in this repository.
- The shared server holds the Google Ads developer token.
- Each person signs in with their own Google Workspace identity.
- Google Ads account visibility follows that person's existing Google Ads permissions.
