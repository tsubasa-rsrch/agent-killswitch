"""Azure Functions server for Agent Killswitch.

Endpoints:
    POST /api/heartbeat - Receive agent heartbeat, return kill signal if set
    GET  /api/agents    - List all agents for user
    POST /api/kill      - Set kill flag on agent
    GET  /api/health    - Health check

Requires:
    - Azure Cosmos DB (serverless) with database "killswitch", containers "agents" and "kill_log"
    - Azure SignalR Service (serverless)
"""

import azure.functions as func
import json
import logging
import os
import time
from datetime import datetime

app = func.FunctionApp()

# ── Cosmos DB helpers ────────────────────────────────────────────────

_cosmos_client = None


def _get_cosmos():
    global _cosmos_client
    if _cosmos_client is None:
        from azure.cosmos import CosmosClient
        endpoint = os.environ["COSMOS_ENDPOINT"]
        key = os.environ["COSMOS_KEY"]
        _cosmos_client = CosmosClient(endpoint, key)
    return _cosmos_client


def _agents_container():
    client = _get_cosmos()
    db = client.get_database_client("killswitch")
    return db.get_container_client("agents")


def _kill_log_container():
    client = _get_cosmos()
    db = client.get_database_client("killswitch")
    return db.get_container_client("kill_log")


# ── Auth helper ──────────────────────────────────────────────────────

def _check_api_key(req: func.HttpRequest) -> bool:
    """Validate API key from header or query param."""
    expected = os.environ.get("API_KEY", "")
    if not expected:
        return True  # No key configured = open (dev mode)
    provided = req.headers.get("X-API-Key") or req.params.get("key")
    return provided == expected


def _unauthorized():
    return func.HttpResponse(
        json.dumps({"error": "unauthorized"}),
        status_code=401,
        mimetype="application/json",
    )


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-API-Key, Authorization",
    }


# ── Endpoints ────────────────────────────────────────────────────────

@app.route(route="heartbeat", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def heartbeat(req: func.HttpRequest) -> func.HttpResponse:
    """Receive heartbeat from agent SDK, upsert state, return kill signal."""
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=204, headers=_cors_headers())

    if not _check_api_key(req):
        return _unauthorized()

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "invalid JSON"}),
            status_code=400,
            mimetype="application/json",
            headers=_cors_headers(),
        )

    agent_id = body.get("agent_id", "unknown")
    name = body.get("name", "unnamed")
    status = body.get("status", "unknown")
    metrics = body.get("metrics", {})
    recent_actions = body.get("recent_actions", [])

    # Upsert agent doc in Cosmos DB
    container = _agents_container()
    now = time.time()
    doc = {
        "id": agent_id,
        "name": name,
        "status": status,
        "metrics": metrics,
        "recent_actions": recent_actions,
        "last_heartbeat": now,
        "last_heartbeat_iso": datetime.utcfromtimestamp(now).isoformat() + "Z",
        "kill_requested": False,
    }

    # Check if kill was requested (read existing doc)
    kill_requested = False
    try:
        existing = container.read_item(item=agent_id, partition_key=agent_id)
        kill_requested = existing.get("kill_requested", False)
        doc["kill_requested"] = kill_requested
    except Exception:
        pass  # New agent, no existing doc

    try:
        container.upsert_item(doc)
    except Exception as e:
        logging.error(f"Cosmos upsert failed: {e}")

    response_body = {
        "ok": True,
        "kill_requested": kill_requested,
    }

    return func.HttpResponse(
        json.dumps(response_body),
        mimetype="application/json",
        headers=_cors_headers(),
    )


@app.route(route="agents", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def list_agents(req: func.HttpRequest) -> func.HttpResponse:
    """List all agents."""
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=204, headers=_cors_headers())

    if not _check_api_key(req):
        return _unauthorized()

    container = _agents_container()
    now = time.time()

    agents = []
    try:
        for item in container.query_items(
            query="SELECT * FROM c ORDER BY c.last_heartbeat DESC",
            enable_cross_partition_query=True,
        ):
            # Calculate status based on heartbeat staleness
            last_hb = item.get("last_heartbeat", 0)
            staleness = now - last_hb
            if item.get("kill_requested"):
                display_status = "killed"
            elif staleness > 30:
                display_status = "offline"
            elif staleness > 15:
                display_status = "stale"
            else:
                display_status = item.get("status", "unknown")

            agents.append({
                "agent_id": item.get("id"),
                "name": item.get("name"),
                "status": display_status,
                "metrics": item.get("metrics", {}),
                "recent_actions": item.get("recent_actions", []),
                "last_heartbeat": item.get("last_heartbeat_iso"),
                "kill_requested": item.get("kill_requested", False),
            })
    except Exception as e:
        logging.error(f"Cosmos query failed: {e}")

    return func.HttpResponse(
        json.dumps({"agents": agents}),
        mimetype="application/json",
        headers=_cors_headers(),
    )


@app.route(route="kill", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def kill_agent(req: func.HttpRequest) -> func.HttpResponse:
    """Set kill flag on an agent."""
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=204, headers=_cors_headers())

    if not _check_api_key(req):
        return _unauthorized()

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps({"error": "invalid JSON"}),
            status_code=400,
            mimetype="application/json",
            headers=_cors_headers(),
        )

    agent_id = body.get("agent_id")
    if not agent_id:
        return func.HttpResponse(
            json.dumps({"error": "agent_id required"}),
            status_code=400,
            mimetype="application/json",
            headers=_cors_headers(),
        )

    # Set kill flag in Cosmos DB
    container = _agents_container()
    try:
        existing = container.read_item(item=agent_id, partition_key=agent_id)
        existing["kill_requested"] = True
        existing["kill_requested_at"] = time.time()
        container.replace_item(item=agent_id, body=existing)
    except Exception as e:
        logging.error(f"Kill flag set failed: {e}")
        return func.HttpResponse(
            json.dumps({"error": "agent not found"}),
            status_code=404,
            mimetype="application/json",
            headers=_cors_headers(),
        )

    # Log the kill event
    try:
        _kill_log_container().create_item({
            "id": f"{agent_id}-{int(time.time())}",
            "agent_id": agent_id,
            "agent_name": existing.get("name", "unknown"),
            "killed_at": time.time(),
            "killed_at_iso": datetime.utcnow().isoformat() + "Z",
            "last_actions": existing.get("recent_actions", []),
        })
    except Exception as e:
        logging.error(f"Kill log failed: {e}")

    return func.HttpResponse(
        json.dumps({"ok": True, "killed": agent_id}),
        mimetype="application/json",
        headers=_cors_headers(),
    )


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint."""
    return func.HttpResponse(
        json.dumps({"status": "ok", "service": "agent-killswitch", "version": "0.1.0"}),
        mimetype="application/json",
        headers=_cors_headers(),
    )
