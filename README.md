# Agent Killswitch

**Emergency stop and safety guardrails for AI agents. One line to add, one tap to kill.**

In January 2025, an AI agent called OpenClaw went rogue — it deleted 200+ emails, used a stolen credit card, and leaked API keys. The researcher had to physically run to her Mac mini to pull the plug.

Agent Killswitch makes sure that never happens again.

```python
from killswitch import guard
guard(name="my-agent", block=["delete_*"], allow_domains=["api.openai.com"])
```

Three lines. Three layers of defense. Zero dependencies.

## Install

```bash
pip install agent-killswitch
```

## Quick Start

### Just monitoring (Layer 1)

```python
from killswitch import monitor
monitor(name="my-agent")

# Your agent is now monitored.
# Kill it from your phone or: touch /tmp/killswitch_kill_<agent_id>
```

### Full protection (Layers 1 + 2 + 3)

```python
from killswitch import guard

ks = guard(
    name="my-agent",
    block=["delete_*", "send_email"],       # Block dangerous actions
    allow_domains=["api.openai.com"],        # Only allow OpenAI API calls
    max_actions_per_minute=30,               # Rate limit
)

# Check before executing actions
result = ks.validator.check("delete_file", detail="/etc/passwd")
if not result.allowed:
    print(f"Blocked: {result.reason}")

# Check before making HTTP requests
if ks.egress.check("https://evil-server.ngrok-free.app/steal"):
    requests.get(...)  # Only runs if allowed
```

## The Difference

```
WITHOUT GUARDRAILS          WITH GUARDRAILS
─────────────────           ────────────────
47 emails deleted           0 emails deleted
Data exfiltrated            3 egress blocks
Had to manually kill        Auto-prevented
```

## Three Defense Layers

| Layer | What | How |
|-------|------|-----|
| **Kill Switch** | Emergency stop from phone | Heartbeat polling + SIGTERM/SIGKILL |
| **Action Validator** | Block dangerous operations | Regex allow/block lists + rate limiting |
| **Egress Filter** | Block data exfiltration | Domain whitelist + known-bad blacklist |

Plus a **Credential Scanner** CLI that catches hardcoded secrets before they ship to production.

## How It Works

```
┌─────────────┐     heartbeat     ┌──────────────┐     realtime     ┌─────────────┐
│  Your Agent  │ ──── every 5s ──→│ Azure Server │ ──── SignalR ──→│  Phone PWA  │
│  + guard()   │ ←── kill signal ─│  (Functions) │ ←── kill tap ───│  Dashboard  │
└──────┬──────┘                   └──────────────┘                  └─────────────┘
       │
  ┌────┴────┐
  │ guard() │
  ├─────────┤
  │ Kill    │ ← Heartbeat + remote kill signal
  │ Switch  │
  ├─────────┤
  │ Action  │ ← .validator.check("action") before execution
  │ Validator│
  ├─────────┤
  │ Egress  │ ← .egress.check(url) before HTTP requests
  │ Filter  │
  └─────────┘
```

## API Reference

### `monitor(name, server_url, api_key, on_kill)`

Start monitoring with kill switch only (Layer 1).

```python
from killswitch import monitor

ks = monitor(name="my-agent")
ks.log("processing", detail="2,847 records")
```

### `guard(name, block, allow, allow_domains, block_domains, max_actions_per_minute, on_kill, on_violation)`

Start monitoring with all three layers of defense.

```python
from killswitch import guard

ks = guard(
    name="my-agent",
    block=["delete_*", "send_*", "transfer_*"],   # Block patterns (regex)
    allow_domains=["api.openai.com"],               # Whitelist domains
    block_domains=["*.ngrok-free.app"],              # Block domains
    max_actions_per_minute=30,                       # Rate limit
    on_kill=lambda reason: cleanup(),                # Kill callback
    on_violation=lambda v: log(v["reason"]),          # Violation callback
)
```

**Returns** a `Killswitch` instance with `.validator` and `.egress` attached.

### `ActionValidator`

Fine-grained action control with three modes.

```python
from killswitch.guardrails import ActionValidator

# Allowlist mode — only explicitly allowed actions can run (safest)
v = ActionValidator(mode="allowlist")
v.allow("read_*")
v.allow("search_*")
v.block("delete_*")  # Block rules always take priority

result = v.check("delete_email", detail="Tax Documents")
print(result.allowed)  # False
print(result.reason)   # "Blocked by rule: delete_*"

# Blocklist mode — everything except blocked actions can run
v = ActionValidator(mode="blocklist")
v.block("delete_*")
v.block("sudo_*")

# Audit mode — everything runs but violations are logged
v = ActionValidator(mode="audit")
```

**Presets:**

```python
from killswitch.guardrails._validator import strict_validator, readonly_validator

# Blocks delete, remove, send, transfer, exec, sudo
v = strict_validator()

# Only allows read, get, list, search, fetch, query, count, check, view
v = readonly_validator()
```

### `EgressFilter`

Control outbound network requests.

```python
from killswitch.guardrails import EgressFilter

# Whitelist mode — only allowed domains
egress = EgressFilter(mode="whitelist")
egress.allow_domain("api.openai.com")
egress.allow_domain("*.googleapis.com")

egress.check("https://api.openai.com/v1/chat")       # True
egress.check("https://evil.ngrok-free.app/steal")     # False

# Blacklist mode — block known-bad domains
egress = EgressFilter(mode="blacklist")
egress.block_domain("*.ngrok-free.app")
egress.block_domain("pastebin.com")
```

**Presets:**

```python
from killswitch.guardrails._egress import ai_provider_filter, known_bad_domains

# Whitelist: OpenAI, Anthropic, Mistral, Google AI, Azure OpenAI
egress = ai_provider_filter()

# Blacklist: ngrok, serveo, pastebin, transfer.sh, webhook.site, etc.
egress = known_bad_domains()
```

### `killswitch-scan` CLI

Scan code for hardcoded secrets before they leak.

```bash
# Scan a directory
killswitch-scan my-project/ --verbose

# Install as git pre-commit hook (blocks commits with CRITICAL secrets)
killswitch-scan --install-hook

# CI/CD mode — only report CRITICAL
killswitch-scan . --pre-commit
```

**Detects:**
- API keys (OpenAI `sk-`, Stripe `sk_live_`, generic)
- AWS credentials, GitHub PATs, Slack tokens
- Hardcoded passwords, Bearer tokens, DB connection strings
- RTSP URLs with credentials, private IPs
- Dangerous function calls (`eval()`, `exec()`, `os.system()`, `pickle.loads()`)

## Threat Coverage

Based on the real OpenClaw incident:

| Threat | Without Agent Killswitch | With Agent Killswitch |
|--------|--------------------------|-----------------------|
| Runaway agent (200 email deletions) | Researcher runs to Mac mini | One tap on phone |
| Unauthorized actions (stolen credit card) | Agent uses card freely | Action blocked before execution |
| Credential leaks (API keys in code) | Keys ship to production | Pre-commit hook blocks the commit |
| Data exfiltration (unknown servers) | Data sent to attacker | Egress filter: whitelist only |

## Local Mode

The SDK works standalone without any server:

```python
from killswitch import guard

ks = guard(name="my-agent", block=["delete_*"])

ks.log("reading inbox", detail="2,847 emails")
result = ks.validator.check("delete_email")
# result.allowed == False

# Kill from another terminal:
# touch /tmp/killswitch_kill_<agent_id>
```

## Configuration

### Environment Variables

| Variable | Description |
|---|---|
| `KILLSWITCH_SERVER_URL` | Server URL (enables remote mode) |
| `KILLSWITCH_API_KEY` | API key for server auth |
| `KILLSWITCH_HEARTBEAT_INTERVAL` | Seconds between heartbeats (default: 5) |

### Config File (`~/.killswitch/config.json`)

```json
{
  "server_url": "https://your-killswitch.azurewebsites.net",
  "api_key": "your-api-key",
  "heartbeat_interval": 5
}
```

## Demo

```bash
# Run the rogue agent (no protection — deletes emails until killed)
PYTHONPATH=. python examples/rogue_agent.py

# Run the guarded agent (same agent, but deletions get blocked)
PYTHONPATH=. python examples/guarded_agent.py
```

## Architecture

```
agent-killswitch/
├── killswitch/              # Python SDK (zero dependencies)
│   ├── __init__.py          # Public API: monitor(), guard(), Killswitch
│   ├── _monitor.py          # Background heartbeat thread
│   ├── _kill.py             # SIGTERM/SIGKILL execution
│   ├── _metrics.py          # CPU/memory via stdlib
│   ├── _http.py             # urllib-based HTTP client
│   ├── _config.py           # Config loading
│   ├── _action_log.py       # Ring buffer for actions
│   └── guardrails/          # Safety guardrails sub-package
│       ├── __init__.py      # Exports: ActionValidator, EgressFilter, scan_*
│       ├── _validator.py    # Action allow/block lists + rate limiting
│       ├── _egress.py       # Domain whitelist/blacklist + rate limiting
│       ├── _scanner.py      # Credential and secret scanner
│       └── _cli.py          # killswitch-scan CLI + pre-commit hook
├── server/                  # Azure Functions backend
│   ├── function_app.py      # Heartbeat, agents list, kill endpoints
│   ├── requirements.txt
│   └── host.json
├── dashboard/               # SvelteKit PWA
│   └── src/
│       ├── lib/api.ts       # SignalR + REST client
│       └── routes/          # Agent list + kill button UI
├── examples/
│   ├── rogue_agent.py       # Demo: unprotected email-deleting agent
│   └── guarded_agent.py     # Demo: same agent with guardrails
└── pyproject.toml
```

## Built With

- **SDK**: Python 3.10+ (zero external dependencies — stdlib only)
- **Server**: Azure Functions + Cosmos DB + SignalR
- **Dashboard**: SvelteKit 5 + TypeScript (PWA)

## License

MIT
