"""Azure Functions server for Agent Killswitch.

Endpoints:
    POST /api/heartbeat  - Receive agent heartbeat + violations, return kill signal
    GET  /api/agents     - List all agents with policy status
    POST /api/kill       - Set kill flag on agent
    GET  /api/violations - Get violation history for an agent
    GET  /api/health     - Health check

Requires:
    - Azure Cosmos DB (serverless) with database "killswitch",
      containers "agents", "kill_log", and "violations"
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


def _violations_container():
    client = _get_cosmos()
    db = client.get_database_client("killswitch")
    return db.get_container_client("violations")


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


# ── Server-side policy check ────────────────────────────────────────

# Server can enforce kill threshold independently of client
SERVER_KILL_THRESHOLD = int(os.environ.get("POLICY_KILL_THRESHOLD", "100"))


def _check_server_policy(agent_doc: dict) -> bool:
    """Check if server-side policy triggers auto-kill. Returns True if should kill."""
    policy = agent_doc.get("policy", {})
    score = policy.get("score", 0)
    return score >= SERVER_KILL_THRESHOLD and SERVER_KILL_THRESHOLD > 0


# ── Endpoints ────────────────────────────────────────────────────────

@app.route(route="heartbeat", methods=["POST", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def heartbeat(req: func.HttpRequest) -> func.HttpResponse:
    """Receive heartbeat from agent SDK, upsert state, return kill signal.

    Now also accepts policy summary and recent violations from the agent.
    Server can independently trigger auto-kill based on violation score.
    """
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
    policy = body.get("policy", {})
    recent_violations = body.get("recent_violations", [])

    # Upsert agent doc in Cosmos DB
    container = _agents_container()
    now = time.time()
    doc = {
        "id": agent_id,
        "name": name,
        "status": status,
        "metrics": metrics,
        "recent_actions": recent_actions,
        "policy": policy,
        "recent_violations": recent_violations,
        "last_heartbeat": now,
        "last_heartbeat_iso": datetime.utcfromtimestamp(now).isoformat() + "Z",
        "kill_requested": False,
    }

    # Check if kill was already requested (read existing doc)
    kill_requested = False
    try:
        existing = container.read_item(item=agent_id, partition_key=agent_id)
        kill_requested = existing.get("kill_requested", False)
        doc["kill_requested"] = kill_requested
    except Exception:
        pass  # New agent, no existing doc

    # Server-side policy check: auto-kill if violation score exceeds threshold
    server_kill = False
    if not kill_requested and _check_server_policy(doc):
        doc["kill_requested"] = True
        doc["kill_requested_at"] = now
        doc["kill_reason"] = "server_policy_auto_kill"
        kill_requested = True
        server_kill = True
        logging.warning(
            f"Server auto-kill triggered for {name} ({agent_id}): "
            f"score={policy.get('score', 0)}/{SERVER_KILL_THRESHOLD}"
        )

    try:
        container.upsert_item(doc)
    except Exception as e:
        logging.error(f"Cosmos upsert failed: {e}")

    # Store violations in violations container (if any new ones)
    if recent_violations:
        try:
            violations_container = _violations_container()
            for v in recent_violations:
                violations_container.upsert_item({
                    "id": f"{agent_id}-{v.get('t', now)}-{v.get('action', '')}",
                    "agent_id": agent_id,
                    "agent_name": name,
                    **v,
                    "received_at": now,
                })
        except Exception as e:
            logging.error(f"Violations storage failed: {e}")

    # Log auto-kill event
    if server_kill:
        try:
            _kill_log_container().create_item({
                "id": f"{agent_id}-{int(now)}",
                "agent_id": agent_id,
                "agent_name": name,
                "killed_at": now,
                "killed_at_iso": datetime.utcfromtimestamp(now).isoformat() + "Z",
                "kill_reason": "server_policy_auto_kill",
                "policy_score": policy.get("score", 0),
                "last_actions": recent_actions,
                "last_violations": recent_violations,
            })
        except Exception as e:
            logging.error(f"Kill log failed: {e}")

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
    """List all agents with status and policy info."""
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
                "policy": item.get("policy", {}),
                "recent_violations": item.get("recent_violations", []),
                "last_heartbeat": item.get("last_heartbeat_iso"),
                "kill_requested": item.get("kill_requested", False),
                "kill_reason": item.get("kill_reason", ""),
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
    reason = body.get("reason", "manual_kill")
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
        existing["kill_reason"] = reason
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
            "kill_reason": reason,
            "last_actions": existing.get("recent_actions", []),
            "last_violations": existing.get("recent_violations", []),
        })
    except Exception as e:
        logging.error(f"Kill log failed: {e}")

    return func.HttpResponse(
        json.dumps({"ok": True, "killed": agent_id, "reason": reason}),
        mimetype="application/json",
        headers=_cors_headers(),
    )


@app.route(route="violations", methods=["GET", "OPTIONS"], auth_level=func.AuthLevel.ANONYMOUS)
def get_violations(req: func.HttpRequest) -> func.HttpResponse:
    """Get violation history for an agent.

    Query params:
        agent_id: Filter by agent (optional, returns all if not set)
        limit: Max results (default 50)
    """
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=204, headers=_cors_headers())

    if not _check_api_key(req):
        return _unauthorized()

    agent_id = req.params.get("agent_id")
    limit = int(req.params.get("limit", "50"))

    violations = []
    try:
        container = _violations_container()
        if agent_id:
            query = f"SELECT TOP {limit} * FROM c WHERE c.agent_id = @agent_id ORDER BY c.t DESC"
            params = [{"name": "@agent_id", "value": agent_id}]
        else:
            query = f"SELECT TOP {limit} * FROM c ORDER BY c.t DESC"
            params = []

        for item in container.query_items(
            query=query,
            parameters=params,
            enable_cross_partition_query=True,
        ):
            violations.append({
                "agent_id": item.get("agent_id"),
                "agent_name": item.get("agent_name"),
                "severity": item.get("severity"),
                "action": item.get("action"),
                "reason": item.get("reason"),
                "detail": item.get("detail"),
                "points": item.get("points"),
                "timestamp": item.get("t"),
            })
    except Exception as e:
        logging.error(f"Violations query failed: {e}")

    return func.HttpResponse(
        json.dumps({"violations": violations, "count": len(violations)}),
        mimetype="application/json",
        headers=_cors_headers(),
    )


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint."""
    return func.HttpResponse(
        json.dumps({
            "status": "ok",
            "service": "agent-killswitch",
            "version": "0.3.0",
            "features": ["killswitch", "guardrails", "policy_engine", "auto_kill"],
        }),
        mimetype="application/json",
        headers=_cors_headers(),
    )
