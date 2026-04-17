#!/bin/bash
set -e

# ============================================================
# Guardrly MCP Server Installer — Mac / Linux
# ============================================================

echo "================================="
echo "  Guardrly MCP Server Installer  "
echo "  guardrly.com                   "
echo "================================="
echo ""

# ------------------------------------------------------------
# Step 1: Check Python 3.11+
# ------------------------------------------------------------
if ! command -v python3 &>/dev/null; then
  echo "Error: python3 not found."
  echo "Python 3.11 or higher is required."
  echo "Download from https://python.org"
  exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]; }; then
  echo "Error: Python 3.11 or higher is required."
  echo "Detected: Python $PYTHON_VERSION"
  echo "Download from https://python.org"
  exit 1
fi

echo "✓ Python $PYTHON_VERSION detected"

# ------------------------------------------------------------
# Step 2: Install guardrly package via pipx
# ------------------------------------------------------------
echo ""
echo "Installing Guardrly..."
if ! command -v pipx &> /dev/null; then
  echo "Installing pipx..."
  brew install pipx 2>/dev/null || pip3 install pipx --user
fi
pipx install guardrly --quiet
echo "✓ Guardrly installed"

# ------------------------------------------------------------
# Step 4: Detect AI tool config paths
# ------------------------------------------------------------
CLAUDE_CONFIG_MAC="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
CLAUDE_CONFIG_LINUX="$HOME/.config/Claude/claude_desktop_config.json"
CURSOR_CONFIG_MAC="$HOME/Library/Application Support/Cursor/User/settings.json"
CURSOR_CONFIG_LINUX="$HOME/.config/Cursor/User/settings.json"

# Detect OS and select correct paths
OS_TYPE="$(uname -s)"
if [ "$OS_TYPE" = "Darwin" ]; then
  CLAUDE_CONFIG="$CLAUDE_CONFIG_MAC"
  CURSOR_CONFIG="$CURSOR_CONFIG_MAC"
else
  CLAUDE_CONFIG="$CLAUDE_CONFIG_LINUX"
  CURSOR_CONFIG="$CURSOR_CONFIG_LINUX"
fi

# ------------------------------------------------------------
# Step 5: Ask which AI tool
# ------------------------------------------------------------
echo ""
echo "Which AI tool do you use?"
echo "  [1] Claude Desktop"
echo "  [2] Cursor"
echo "  [3] Both"
read -p "Enter choice (1/2/3): " TOOL_CHOICE

# ------------------------------------------------------------
# Step 6: Log in to get API key and HMAC secret automatically
# ------------------------------------------------------------
echo ""
echo "Log in to your Guardrly account"
echo "Don't have an account? Sign up at https://app.guardrly.com/register"
echo ""
read -p "Email: " GUARDRLY_EMAIL
read -s -p "Password: " GUARDRLY_PASSWORD
echo ""

echo "Logging in..."
LOGIN_RESPONSE=$(curl -s -X POST https://api.guardrly.com/api/v1/auth/cli-login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$GUARDRLY_EMAIL\",\"password\":\"$GUARDRLY_PASSWORD\"}")

# Check for error
LOGIN_ERROR=$(echo "$LOGIN_RESPONSE" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('detail', {}).get('error', ''))
except:
    print('parse_error')
" 2>/dev/null)

if [ -n "$LOGIN_ERROR" ]; then
  echo "Error: Login failed: $LOGIN_ERROR"
  echo "  Please check your email and password."
  echo "  Or sign up at https://app.guardrly.com/register"
  exit 1
fi

# Extract credentials
API_KEY=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['api_key'])" 2>/dev/null)
HMAC_SECRET=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['hmac_secret'])" 2>/dev/null)
GUARDRLY_EMAIL_OUT=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['email'])" 2>/dev/null)

if [ -z "$API_KEY" ] || [ -z "$HMAC_SECRET" ]; then
  echo "Error: Failed to retrieve credentials. Please try again."
  exit 1
fi

echo "✓ Logged in as $GUARDRLY_EMAIL_OUT"
echo "✓ API key created automatically"

# ------------------------------------------------------------
# Step 7: Save credentials to ~/.guardrly/.env
# ------------------------------------------------------------
mkdir -p ~/.guardrly
cat > ~/.guardrly/.env << EOF
GUARDRLY_API_KEY=$API_KEY
GUARDRLY_API_URL=https://api.guardrly.com
HMAC_SECRET=$HMAC_SECRET
EOF
echo "✓ Credentials saved to ~/.guardrly/.env"

# ------------------------------------------------------------
# Step 8: Build MCP server config JSON (used by injection fns)
# ------------------------------------------------------------
MCP_CONFIG='{
  "command": "python3",
  "args": ["-m", "guardrly"],
  "env": {
    "GUARDRLY_API_KEY": "'"$API_KEY"'",
    "GUARDRLY_API_URL": "https://api.guardrly.com",
    "HMAC_SECRET": "'"$HMAC_SECRET"'"
  }
}'

# ------------------------------------------------------------
# Helper: inject into a JSON file using python3
# Usage: inject_json_config <config_file> <json_path> <value_json>
#   json_path is a dot-separated key path, e.g. "mcpServers.guardrly"
# ------------------------------------------------------------
inject_json_config() {
  local CONFIG_FILE="$1"
  local KEY_PATH="$2"
  local VALUE_JSON="$3"
  local CONFIG_DIR
  CONFIG_DIR="$(dirname "$CONFIG_FILE")"

  if [ ! -d "$CONFIG_DIR" ]; then
    mkdir -p "$CONFIG_DIR" || {
      echo "Error: Cannot create directory $CONFIG_DIR"
      echo "Please create it manually and re-run the installer."
      return 1
    }
  fi

  if [ ! -f "$CONFIG_FILE" ]; then
    # Create minimal config
    python3 - <<PYEOF
import json, sys

keys = "$KEY_PATH".split(".")
value = json.loads('''$VALUE_JSON''')

config = {}
node = config
for key in keys[:-1]:
    node[key] = {}
    node = node[key]
node[keys[-1]] = value

with open("$CONFIG_FILE", "w") as f:
    json.dump(config, f, indent=2)
PYEOF
  else
    if [ ! -w "$CONFIG_FILE" ]; then
      echo "Error: Cannot write to $CONFIG_FILE"
      echo "Please check file permissions or add the config manually."
      return 1
    fi
    python3 - <<PYEOF
import json, sys

try:
    with open("$CONFIG_FILE", "r") as f:
        config = json.load(f)
except json.JSONDecodeError:
    print("Warning: Existing config file has invalid JSON. Creating a backup and starting fresh.")
    import shutil, time
    shutil.copy("$CONFIG_FILE", "$CONFIG_FILE.bak." + str(int(time.time())))
    config = {}

keys = "$KEY_PATH".split(".")
value = json.loads('''$VALUE_JSON''')

node = config
for key in keys[:-1]:
    if key not in node or not isinstance(node[key], dict):
        node[key] = {}
    node = node[key]
node[keys[-1]] = value

with open("$CONFIG_FILE", "w") as f:
    json.dump(config, f, indent=2)
PYEOF
  fi
}

# ------------------------------------------------------------
# Step 9: Inject into Claude Desktop
# ------------------------------------------------------------
inject_claude() {
  echo ""
  echo "Configuring Claude Desktop..."
  if inject_json_config "$CLAUDE_CONFIG" "mcpServers.guardrly" "$MCP_CONFIG"; then
    echo "✓ Guardrly added to Claude Desktop"
  else
    echo ""
    echo "Manual configuration for Claude Desktop:"
    echo "  File: $CLAUDE_CONFIG"
    echo '  Add under "mcpServers":'
    echo '  "guardrly": '"$MCP_CONFIG"
  fi
}

# ------------------------------------------------------------
# Step 10: Inject into Cursor
# ------------------------------------------------------------
inject_cursor() {
  echo ""
  echo "Configuring Cursor..."
  if inject_json_config "$CURSOR_CONFIG" "mcp.servers.guardrly" "$MCP_CONFIG"; then
    echo "✓ Guardrly added to Cursor"
  else
    echo ""
    echo "Manual configuration for Cursor:"
    echo "  File: $CURSOR_CONFIG"
    echo '  Add under "mcp" > "servers":'
    echo '  "guardrly": '"$MCP_CONFIG"
  fi
}

# ------------------------------------------------------------
# Step 11: Apply based on tool choice
# ------------------------------------------------------------
case "$TOOL_CHOICE" in
  1)
    inject_claude
    ;;
  2)
    inject_cursor
    ;;
  3)
    inject_claude
    inject_cursor
    ;;
  *)
    echo "Invalid choice. Skipping config injection."
    echo "Run the installer again and enter 1, 2, or 3."
    ;;
esac

# ------------------------------------------------------------
# Step 12: Success message
# ------------------------------------------------------------
echo ""
echo "================================="
echo "Guardrly installed successfully!"
echo ""
echo "Next steps:"
echo "  1. Restart Claude Desktop / Cursor"
echo "  2. The 'make_http_request' tool will appear"
echo "  3. View your Dashboard: https://app.guardrly.com"
echo "================================="
echo ""
echo "To verify installation, run:"
echo "  guardrly --version"
