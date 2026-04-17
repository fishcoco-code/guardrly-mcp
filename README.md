# Guardrly MCP Server

Non-invasive AI Agent operation monitoring. Monitor every API call your AI Agent makes to external platforms like Shopify and Meta Ads. Real-time alerts, audit logs, and operation history.

**Website**: [guardrly.com](https://guardrly.com)  
**Dashboard**: [app.guardrly.com](https://app.guardrly.com)  
**PyPI**: [pypi.org/project/guardrly](https://pypi.org/project/guardrly)

## Features

- **Visibility** — Turn AI Agent black-box operations into a human-readable audit trail
- **Protection** — Get alerted on dangerous operations before damage is done  
- **Compliance** — PII is automatically scrubbed at the local layer before any data leaves your machine
- **Zero Code Changes** — Installs as an MCP Server, no changes to your Agent workflows

## Supported AI Tools

- Claude Desktop
- Cursor
- Any MCP-compatible AI tool

## Supported Platforms

- **Shopify Admin API** — 50 semantic rules, 10 operation categories
- **Meta Ads API** — 50 semantic rules, 10 operation categories
- **Generic HTTP** — Basic logging for any other API

## Installation

### Quick Install (Recommended)

Mac / Linux:
```bash
curl -fsSL https://guardrly.com/install.sh | bash
```

Windows (PowerShell):
```powershell
irm https://guardrly.com/install.ps1 | iex
```

### Manual Install

```bash
brew install pipx
pipx install guardrly
```

Then configure your AI tool with the MCP config from [app.guardrly.com/settings](https://app.guardrly.com/settings) → MCP Configuration.

## How It Works

```
AI Agent → make_http_request(url, method, headers, body)
  → Guardrly MCP Server (local)
      → Platform detection
      → PII scrubbing (Authorization headers, tokens, emails)  
      → Risk assessment
      → Local SQLite queue
  → Original API endpoint
  
Background (every 30s):
  → Log shipper sends to cloud
  → Dashboard at app.guardrly.com shows everything
```

## Documentation

Full documentation at [guardrly.com/docs](https://guardrly.com/docs)

## Support

- Email: support@guardrly.com  
- Website: [guardrly.com](https://guardrly.com)

## License

MIT License. See [LICENSE](LICENSE) for details.
