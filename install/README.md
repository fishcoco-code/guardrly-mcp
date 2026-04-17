# Guardrly Installation

## One-command install

**Mac / Linux:**
```bash
curl -fsSL https://guardrly.com/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://guardrly.com/install.ps1 | iex
```

## Manual installation

### 1. Install the package

**Mac / Linux:**
```bash
brew install pipx
pipx install guardrly
```

**Windows:**
```powershell
pip install pipx --user
# Or: winget install pipx
pipx install guardrly
```

### 2. Add to Claude Desktop config

> **Note:** If you used the one-line installer, credentials are configured automatically.
> The manual steps below are for advanced users only.

**Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Linux:** `~/.config/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "guardrly": {
      "command": "python3",
      "args": ["-m", "guardrly"],
      "env": {
        "GUARDRLY_API_KEY": "your_key_here",
        "GUARDRLY_API_URL": "https://api.guardrly.com",
        "HMAC_SECRET": "your_hmac_secret_here"
      }
    }
  }
}
```

### 3. Restart Claude Desktop

### 4. The `make_http_request` tool will appear in Claude Code

## Get your API key and HMAC Secret

> **Note:** If you used the one-line installer, your API key and HMAC Secret were saved
> automatically during login. You do not need to copy them manually.

For manual installation only: sign up at https://app.guardrly.com  
Go to **Settings → MCP Configuration** to copy your API Key and HMAC Secret.
