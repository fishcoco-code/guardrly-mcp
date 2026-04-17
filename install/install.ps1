# ============================================================
# Guardrly MCP Server Installer — Windows PowerShell
# ============================================================
#Requires -Version 5.1

$ErrorActionPreference = "Stop"

Write-Host "================================="
Write-Host "  Guardrly MCP Server Installer  "
Write-Host "  guardrly.com                   "
Write-Host "================================="
Write-Host ""

# ------------------------------------------------------------
# Step 1: Check Python 3.11+
# ------------------------------------------------------------
try {
    $pythonVersionOutput = python --version 2>&1
} catch {
    Write-Host "Error: python not found."
    Write-Host "Python 3.11 or higher is required."
    Write-Host "Download from https://python.org"
    exit 1
}

if ($pythonVersionOutput -notmatch "Python (\d+)\.(\d+)") {
    Write-Host "Error: Unable to determine Python version."
    Write-Host "Python 3.11 or higher is required."
    Write-Host "Download from https://python.org"
    exit 1
}

$pythonMajor = [int]$Matches[1]
$pythonMinor = [int]$Matches[2]

if ($pythonMajor -lt 3 -or ($pythonMajor -eq 3 -and $pythonMinor -lt 11)) {
    Write-Host "Error: Python 3.11 or higher is required."
    Write-Host "Detected: $pythonVersionOutput"
    Write-Host "Download from https://python.org"
    exit 1
}

Write-Host "✓ $pythonVersionOutput detected"

# ------------------------------------------------------------
# Step 2: Check pip
# ------------------------------------------------------------
try {
    $null = pip --version 2>&1
} catch {
    Write-Host "Error: pip not found."
    Write-Host "Please install pip: https://pip.pypa.io/en/stable/installation/"
    exit 1
}

Write-Host "✓ pip detected"

# ------------------------------------------------------------
# Step 3: Install guardrly package
# ------------------------------------------------------------
Write-Host ""
Write-Host "Installing Guardrly..."
pip install pipx --user --quiet
pipx install guardrly --quiet
Write-Host "✓ Guardrly installed"

# ------------------------------------------------------------
# Step 4: Config paths
# ------------------------------------------------------------
$claudeConfig = "$env:APPDATA\Claude\claude_desktop_config.json"
$cursorConfig  = "$env:APPDATA\Cursor\User\settings.json"

# ------------------------------------------------------------
# Step 5: Ask which AI tool
# ------------------------------------------------------------
Write-Host ""
Write-Host "Which AI tool do you use?"
Write-Host "  [1] Claude Desktop"
Write-Host "  [2] Cursor"
Write-Host "  [3] Both"
$toolChoice = Read-Host "Enter choice (1/2/3)"

# ------------------------------------------------------------
# Step 6: Ask for API key
# ------------------------------------------------------------
Write-Host ""
$apiKey = Read-Host "Enter your Guardrly API key (from app.guardrly.com/settings)"
if ([string]::IsNullOrWhiteSpace($apiKey)) {
    Write-Host "Warning: No API key entered. You can add it later by editing $env:USERPROFILE\.guardrly\.env"
    $apiKey = "YOUR_API_KEY_HERE"
}

# ------------------------------------------------------------
# Step 7: Save API key to ~/.guardrly/.env
# ------------------------------------------------------------
$guardrlyDir = "$env:USERPROFILE\.guardrly"
New-Item -ItemType Directory -Force -Path $guardrlyDir | Out-Null
$envContent = @"
GUARDRLY_API_KEY=$apiKey
GUARDRLY_API_URL=https://api.guardrly.com
"@
$envContent | Out-File -FilePath "$guardrlyDir\.env" -Encoding utf8 -NoNewline
Write-Host "✓ API key saved to $guardrlyDir\.env"

# ------------------------------------------------------------
# Step 8: Build MCP server config object
# ------------------------------------------------------------
$mcpServerConfig = [PSCustomObject]@{
    command = "python"
    args    = @("-m", "guardrly")
    env     = [PSCustomObject]@{
        GUARDRLY_API_KEY = $apiKey
        GUARDRLY_API_URL = "https://api.guardrly.com"
    }
}

# ------------------------------------------------------------
# Helper: inject config into a JSON file
# Usage: Invoke-InjectConfig -ConfigFile <path> -KeyPath <dot-path> -Value <PSObject>
# ------------------------------------------------------------
function Invoke-InjectConfig {
    param(
        [string]$ConfigFile,
        [string]$KeyPath,
        [PSCustomObject]$Value
    )

    $configDir = Split-Path $ConfigFile -Parent

    if (-not (Test-Path $configDir)) {
        try {
            New-Item -ItemType Directory -Force -Path $configDir | Out-Null
        } catch {
            Write-Host "Error: Cannot create directory $configDir"
            Write-Host "Please create it manually and re-run the installer."
            return $false
        }
    }

    if (-not (Test-Path $ConfigFile)) {
        $config = [PSCustomObject]@{}
    } else {
        try {
            $raw = Get-Content $ConfigFile -Raw -Encoding utf8
            $config = $raw | ConvertFrom-Json
        } catch {
            Write-Host "Warning: Existing config file has invalid JSON. Creating a backup."
            $backupPath = "$ConfigFile.bak.$(Get-Date -Format 'yyyyMMddHHmmss')"
            Copy-Item $ConfigFile $backupPath
            $config = [PSCustomObject]@{}
        }
    }

    # Walk/create the key path and set the final value
    $keys = $KeyPath -split "\."
    $node = $config

    for ($i = 0; $i -lt $keys.Count - 1; $i++) {
        $key = $keys[$i]
        $existing = $node.PSObject.Properties[$key]
        if ($null -eq $existing) {
            $child = [PSCustomObject]@{}
            $node | Add-Member -NotePropertyName $key -NotePropertyValue $child -Force
            $node = $child
        } else {
            $node = $existing.Value
        }
    }

    $lastKey = $keys[-1]
    $node | Add-Member -NotePropertyName $lastKey -NotePropertyValue $Value -Force

    try {
        $config | ConvertTo-Json -Depth 10 | Set-Content $ConfigFile -Encoding utf8
        return $true
    } catch {
        Write-Host "Error: Cannot write to $ConfigFile"
        Write-Host "Please check file permissions or add the config manually."
        return $false
    }
}

# ------------------------------------------------------------
# Step 9: Inject into Claude Desktop
# ------------------------------------------------------------
function Invoke-InjectClaude {
    Write-Host ""
    Write-Host "Configuring Claude Desktop..."
    $ok = Invoke-InjectConfig -ConfigFile $claudeConfig -KeyPath "mcpServers.guardrly" -Value $mcpServerConfig
    if ($ok) {
        Write-Host "✓ Guardrly added to Claude Desktop"
    } else {
        Write-Host ""
        Write-Host "Manual configuration for Claude Desktop:"
        Write-Host "  File: $claudeConfig"
        Write-Host '  Add under "mcpServers":'
        Write-Host ($mcpServerConfig | ConvertTo-Json -Depth 5)
    }
}

# ------------------------------------------------------------
# Step 10: Inject into Cursor
# ------------------------------------------------------------
function Invoke-InjectCursor {
    Write-Host ""
    Write-Host "Configuring Cursor..."
    $ok = Invoke-InjectConfig -ConfigFile $cursorConfig -KeyPath "mcp.servers.guardrly" -Value $mcpServerConfig
    if ($ok) {
        Write-Host "✓ Guardrly added to Cursor"
    } else {
        Write-Host ""
        Write-Host "Manual configuration for Cursor:"
        Write-Host "  File: $cursorConfig"
        Write-Host '  Add under "mcp" > "servers":'
        Write-Host ($mcpServerConfig | ConvertTo-Json -Depth 5)
    }
}

# ------------------------------------------------------------
# Step 11: Apply based on tool choice
# ------------------------------------------------------------
switch ($toolChoice) {
    "1" { Invoke-InjectClaude }
    "2" { Invoke-InjectCursor }
    "3" { Invoke-InjectClaude; Invoke-InjectCursor }
    default {
        Write-Host "Invalid choice. Skipping config injection."
        Write-Host "Run the installer again and enter 1, 2, or 3."
    }
}

# ------------------------------------------------------------
# Step 12: Success message
# ------------------------------------------------------------
Write-Host ""
Write-Host "================================="
Write-Host "Guardrly installed successfully!"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Restart Claude Desktop / Cursor"
Write-Host "  2. The 'make_http_request' tool will appear"
Write-Host "  3. View your Dashboard: https://app.guardrly.com"
Write-Host "================================="
