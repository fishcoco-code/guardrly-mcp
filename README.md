mcp-name: io.github.fishcoco-code/guardrly-mcp

# Guardrly

**Website:** [guardrly.com](https://guardrly.com)

Guardrly is a non-invasive AI Agent operation monitoring layer that intercepts, records, and
alerts on every API call an AI Agent makes to external platforms - giving users full visibility
into what their Agent did, when, and why.

## Features

- **Visibility** - Turn Agent black-box operations into a human-readable audit trail
- **Protection** - Alert on dangerous operations before damage is done
- **Evidence** - Generate structured operation logs usable as appeal evidence for banned accounts
- **Compliance** - PII is scrubbed at the local layer before any data reaches the cloud

## Installation

```bash
# Mac / Linux
curl -fsSL https://guardrly.com/install.sh | bash

# Windows (PowerShell)
iwr https://guardrly.com/install.ps1 | iex
```

## Development Setup

```bash
# Install dependencies
poetry install

# Copy environment template
cp .env.example .env
# Edit .env with your credentials

# Run API server
poetry run uvicorn api.main:app --reload
```

## License

MIT License. See [LICENSE](LICENSE) for details.
