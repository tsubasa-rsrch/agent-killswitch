#!/bin/bash
# Agent Killswitch - Azure Infrastructure Setup
# Run after: az login
#
# Creates:
#   1. Resource Group
#   2. Cosmos DB (serverless) with database + containers
#   3. Function App (consumption plan, Python)
#   4. Static Web App (free tier) for dashboard
#
# Usage: bash deploy/setup-azure.sh

set -euo pipefail

# ── Configuration ──────────────────────────────────────────────────
RESOURCE_GROUP="killswitch-rg"
LOCATION="eastus"
COSMOS_ACCOUNT="killswitch-cosmos-$(openssl rand -hex 4)"
FUNCTION_APP="killswitch-api-$(openssl rand -hex 4)"
STORAGE_ACCOUNT="killswitchst$(openssl rand -hex 4 | head -c 8)"
API_KEY=$(openssl rand -hex 16)

echo "╔══════════════════════════════════════════════╗"
echo "║  Agent Killswitch - Azure Setup              ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Resource Group:   $RESOURCE_GROUP"
echo "Location:         $LOCATION"
echo "Cosmos Account:   $COSMOS_ACCOUNT"
echo "Function App:     $FUNCTION_APP"
echo "Storage Account:  $STORAGE_ACCOUNT"
echo "API Key:          $API_KEY"
echo ""

# ── 1. Resource Group ──────────────────────────────────────────────
echo "▸ Creating resource group..."
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --output none

# ── 2. Cosmos DB (Serverless) ──────────────────────────────────────
echo "▸ Creating Cosmos DB account (serverless)..."
az cosmosdb create \
  --name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --capabilities EnableServerless \
  --default-consistency-level Session \
  --output none

echo "▸ Creating database 'killswitch'..."
az cosmosdb sql database create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --name killswitch \
  --output none

echo "▸ Creating container 'agents'..."
az cosmosdb sql container create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --database-name killswitch \
  --name agents \
  --partition-key-path "/id" \
  --output none

echo "▸ Creating container 'kill_log'..."
az cosmosdb sql container create \
  --account-name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --database-name killswitch \
  --name kill_log \
  --partition-key-path "/agent_id" \
  --output none

# Get Cosmos DB connection info
COSMOS_ENDPOINT=$(az cosmosdb show \
  --name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query documentEndpoint -o tsv)

COSMOS_KEY=$(az cosmosdb keys list \
  --name "$COSMOS_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --query primaryMasterKey -o tsv)

# ── 3. Storage Account (for Functions) ─────────────────────────────
echo "▸ Creating storage account..."
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --output none

# ── 4. Function App ────────────────────────────────────────────────
echo "▸ Creating Function App (Python, consumption plan)..."
az functionapp create \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --storage-account "$STORAGE_ACCOUNT" \
  --consumption-plan-location "$LOCATION" \
  --runtime python \
  --runtime-version 3.11 \
  --functions-version 4 \
  --os-type Linux \
  --output none

echo "▸ Configuring app settings..."
az functionapp config appsettings set \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --settings \
    "COSMOS_ENDPOINT=$COSMOS_ENDPOINT" \
    "COSMOS_KEY=$COSMOS_KEY" \
    "API_KEY=$API_KEY" \
  --output none

# Get Function App URL
FUNCTION_URL="https://${FUNCTION_APP}.azurewebsites.net"

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  Setup Complete!                             ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
echo "Cosmos DB Endpoint:  $COSMOS_ENDPOINT"
echo "Function App URL:    $FUNCTION_URL"
echo "API Key:             $API_KEY"
echo ""
echo "Next steps:"
echo "  1. Deploy function: cd server && func azure functionapp publish $FUNCTION_APP"
echo "  2. Configure SDK:   export KILLSWITCH_SERVER_URL=$FUNCTION_URL"
echo "  3. Configure SDK:   export KILLSWITCH_API_KEY=$API_KEY"
echo ""

# Save config for local use
CONFIG_DIR="$HOME/.killswitch"
mkdir -p "$CONFIG_DIR"
cat > "$CONFIG_DIR/config.json" << HEREDOC
{
  "server_url": "$FUNCTION_URL",
  "api_key": "$API_KEY",
  "heartbeat_interval": 5
}
HEREDOC

echo "Config saved to $CONFIG_DIR/config.json"
echo ""

# Save deployment info (not committed to git)
cat > "$(dirname "$0")/deployment-info.txt" << HEREDOC
# Agent Killswitch - Deployment Info (DO NOT COMMIT)
# Generated: $(date -u +"%Y-%m-%dT%H:%M:%SZ")

RESOURCE_GROUP=$RESOURCE_GROUP
COSMOS_ACCOUNT=$COSMOS_ACCOUNT
COSMOS_ENDPOINT=$COSMOS_ENDPOINT
FUNCTION_APP=$FUNCTION_APP
FUNCTION_URL=$FUNCTION_URL
STORAGE_ACCOUNT=$STORAGE_ACCOUNT
API_KEY=$API_KEY
HEREDOC

echo "Deployment info saved to deploy/deployment-info.txt"
