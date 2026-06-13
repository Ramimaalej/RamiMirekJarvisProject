#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
GWS_DIR="$BASE_DIR/gws"

echo "============================================"
echo "  Google Workspace CLI — Auth Setup"
echo "============================================"
echo ""
echo "STEP 1: Go to https://console.cloud.google.com"
echo "STEP 2: Create a new project (or select existing)"
echo "STEP 3: Enable these APIs:"
echo "   - Gmail API"
echo "   - Google Calendar API"
echo "   - Google Drive API"
echo "   - Google Sheets API"
echo "   - Google Docs API"
echo "   - Google Meet API"
echo "   - Google Chat API"
echo ""
echo "STEP 4: Go to 'Credentials' → 'Create Credentials' → 'OAuth client ID'"
echo "   - Application type: Desktop app"
echo "   - Name: Jarvis CLI"
echo "STEP 5: Download the JSON → rename it to 'credentials.json'"
echo "STEP 6: Place credentials.json into: $GWS_DIR"
echo ""
echo "============================================"
echo "  Opening Google Cloud Console..."
echo "============================================"

xdg-open "https://console.cloud.google.com" 2>/dev/null || \
    open "https://console.cloud.google.com" 2>/dev/null || \
    echo "Please open https://console.cloud.google.com manually."

echo ""
read -rp "Have you placed credentials.json in $GWS_DIR? (y/N): " CONFIRM

if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
    echo "Please place credentials.json in $GWS_DIR and re-run this script."
    exit 1
fi

if [[ ! -f "$GWS_DIR/credentials.json" ]]; then
    echo "credentials.json not found at $GWS_DIR/credentials.json"
    exit 1
fi

export GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE="$GWS_DIR/credentials.json"

echo ""
echo "Running: gws auth login"
echo "Follow the browser prompt to authenticate."
echo ""

gws auth login || {
    echo ""
    echo "Auth failed. Possible issues:"
    echo "  - credentials.json is invalid or incomplete"
    echo "  - Required APIs are not enabled"
    echo ""
    echo "Check your project at https://console.cloud.google.com/apis/dashboard"
    exit 1
}

echo ""
echo "============================================"
echo "  ✓ Google Workspace CLI is authenticated!"
echo "============================================"
echo ""
echo "You can now run: gws gmail +triage"
echo "To test: gws calendar +agenda --today"
echo ""
