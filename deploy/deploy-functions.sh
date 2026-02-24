#!/bin/bash
# Deploy Azure Functions code
# Run after setup-azure.sh
#
# Usage: bash deploy/deploy-functions.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DEPLOY_INFO="$SCRIPT_DIR/deployment-info.txt"

if [ ! -f "$DEPLOY_INFO" ]; then
  echo "Error: deployment-info.txt not found. Run setup-azure.sh first."
  exit 1
fi

source "$DEPLOY_INFO"

echo "▸ Deploying to $FUNCTION_APP..."

# Azure Functions Core Tools deploy
cd "$PROJECT_DIR/server"

# Check if func CLI is available
if ! command -v func &> /dev/null; then
  echo "Azure Functions Core Tools not found. Installing..."
  npm install -g azure-functions-core-tools@4 --unsafe-perm true
fi

func azure functionapp publish "$FUNCTION_APP" --python

echo ""
echo "Deployed! API available at: $FUNCTION_URL"
echo ""
echo "Test:"
echo "  curl $FUNCTION_URL/api/health"
echo "  curl $FUNCTION_URL/api/agents -H 'X-API-Key: $API_KEY'"
