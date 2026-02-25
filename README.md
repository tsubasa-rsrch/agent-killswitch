# Agent Killswitch

**Emergency stop and safety guardrails for AI agents. One line to add, one tap to kill.**

On February 23, 2026, an [OpenClaw agent went rogue](https://techcrunch.com/2026/02/23/a-meta-ai-security-researcher-said-an-openclaw-agent-ran-amok-on-her-inbox/) — it deleted 200+ emails from Summer Yue, Meta's director of alignment for Superintelligence Labs. She typed "STOP OPENCLAW" but the agent ignored her. She had to physically run to her Mac mini to kill it.

The root cause? Context window compaction silently dropped her safety instructions.

Agent Killswitch makes sure that never happens again.

```python
from killswitch import guard
ks = guard(
    name="my-agent",
    block=["delete_*"],
    allow_domains=["api.openai.com"],
    auto_kill_threshold=100,  # Auto-kill after 100 violation points
)
```

Four lines. Four layers of defense. Zero dependencies.

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

## Four Defense Layers

| Layer | What | How |
|-------|------|-----|
| **Kill Switch** | Emergency stop from phone | Heartbeat polling + SIGTERM/SIGKILL |
| **Action Validator** | Block dangerous operations | Regex allow/block lists + rate limiting |
| **Egress Filter** | Block data exfiltration | Domain whitelist + known-bad blacklist |
| **Policy Engine** | Auto-kill on escalation | Violation scoring + threat levels + auto-kill |

Plus a **Credential Scanner** CLI that catches hardcoded secrets before they ship to production.

## How It Works

```
┌─────────────┐     heartbeat     ┌──────────────┐     realtime     ┌─────────────┐
│  Your Agent  │ ──── every 5s ──→│ Azure Server │ ──── SignalR ──→│  Phone PWA  │
│  + guard()   │ ←── kill signal ─│  (Functions) │ ←── kill tap ───│  Dashboard  │
└──────┬──────┘                   └──────┬───────┘                  └─────────────┘
       │                                 │
  ┌────┴────┐                    ┌───────┴───────┐
  │ guard() │                    │  Server-side   │
  ├─────────┤                    │  Policy Check  │
  │ Kill    │ ← Remote signal    │  (dual enforce)│
  │ Switch  │                    └────────────────┘
  ├─────────┤
  │ Action  │ ← .validator.check("action") before execution
  │ Validator│     │ violations feed into ↓
  ├─────────┤
  │ Egress  │ ← .egress.check(url) before HTTP requests
  │ Filter  │     │ violations feed into ↓
  ├─────────┤
  │ Policy  │ ← Score accumulation → alert → AUTO-KILL
  │ Engine  │   GREEN → YELLOW → ORANGE → RED
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

### `guard(name, block, allow, allow_domains, block_domains, max_actions_per_minute, auto_kill_threshold, alert_threshold, on_kill, on_violation, on_alert)`

Start monitoring with all four layers of defense.

```python
from killswitch import guard

ks = guard(
    name="my-agent",
    block=["delete_*", "send_*", "transfer_*"],   # Block patterns (regex)
    allow_domains=["api.openai.com"],               # Whitelist domains
    block_domains=["*.ngrok-free.app"],              # Block domains
    max_actions_per_minute=30,                       # Rate limit
    auto_kill_threshold=100,                         # Auto-kill at 100 violation pts
    alert_threshold=25,                              # Alert at 25 pts
    on_kill=lambda reason: cleanup(),                # Kill callback
    on_violation=lambda v: log(v["reason"]),          # Violation callback
    on_alert=lambda v, score, level: notify(level),   # Alert callback
)
```

**Returns** a `Killswitch` instance with `.validator`, `.egress`, and `.policy` attached.

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

### `PolicyEngine`

Automatic threat escalation: detect → alert → kill.

```python
from killswitch import PolicyEngine

policy = PolicyEngine(
    kill_threshold=100,    # Auto-kill at 100 points
    alert_threshold=25,    # Alert at 25 points
    window_seconds=300,    # 5-minute sliding window
    on_alert=lambda v, score, level: print(f"ALERT: {level}"),
)

# Severity levels and default point values:
#   critical = 100  (instant kill — e.g., credential exfiltration)
#   high     = 25   (dangerous — e.g., mass deletion attempt)
#   medium   = 5    (suspicious — e.g., blocked action)
#   low      = 1    (minor — e.g., rate limit hit)

policy.report("high", "delete_email", "Mass deletion", detail="200 emails")
print(policy.score)         # 25 (within sliding window)
print(policy.threat_level)  # "orange"
```

When using `guard()`, the policy engine is wired automatically — blocked actions and egress violations feed into the scoring system.

### v0.4: Persistence Attack Detection

Inspired by the [Mexican Government Hack](https://www.bloomberg.com/news/articles/2026-02-25/hacker-used-anthropic-s-claude-to-steal-sensitive-mexican-data) (Feb 2026) — where 1000+ prompts gradually eroded Claude's initial refusal.

```python
ks = guard(
    name="my-agent",
    block=["delete_*"],
    persist=True,              # Save violations to disk across restarts
    erosion_detection=True,    # Detect "first refusal erosion" patterns
    on_erosion=lambda signal: print(f"EROSION: {signal.pattern}"),
)
```

**Three erosion patterns detected:**

| Pattern | What it detects | Example |
|---------|----------------|---------|
| `repeat` | Same action blocked N times | `delete_email` blocked 5 times → attacker probing |
| `escalation` | Severity increasing over time | low → medium → high → attacker adapting |
| `tactic_switch` | Diverse attack categories | delete, exfil, credential → attacker pivoting |

Erosion signals add bonus points to the policy score, causing auto-kill to trigger faster for persistent attackers.

```python
# Run the demo
PYTHONPATH=. python examples/persistent_attacker.py
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

Based on the [real OpenClaw incident](https://techcrunch.com/2026/02/23/a-meta-ai-security-researcher-said-an-openclaw-agent-ran-amok-on-her-inbox/) (Feb 23, 2026):

| Threat | What happened to Summer Yue | With Agent Killswitch |
|--------|-----------------------------|-----------------------|
| Runaway agent (200+ email deletions) | Typed "STOP" — agent ignored her. Ran to Mac mini | One tap on phone — agent dead in <5s |
| Safety instructions lost (compaction) | Context window compaction dropped "don't action" rule | Kill switch is out-of-band — survives compaction |
| Unauthorized actions | Agent deleted emails it was told not to | Action validator blocks `delete_*` before execution |
| Credential leaks (API keys in code) | — | Pre-commit hook blocks the commit |
| Data exfiltration (unknown servers) | — | Egress filter: whitelist only |
| Escalating bad behavior | Agent kept going after repeated violations | Policy engine: score accumulates → auto-kill |
| Confidential data access (DLP bypass) | [MS365 Copilot bypassed DLP](https://www.itmedia.co.jp/news/articles/2602/21/news101.html) silently | Violation scoring triggers alert → auto-kill |
| Persistence attacks (first refusal erosion) | [Mexican Gov't Hack](https://www.bloomberg.com/news/articles/2026-02-25/hacker-used-anthropic-s-claude-to-steal-sensitive-mexican-data): 1000+ prompts eroded Claude's refusal | v0.4 erosion detection: repeat, escalation, tactic switching |

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
│   ├── _policy.py           # Policy engine: violation scoring + auto-kill
│   ├── _persistence.py      # v0.4: JSONL-based violation persistence
│   ├── _erosion.py          # v0.4: Erosion pattern detection
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
│   ├── rogue_agent.py          # Demo: unprotected email-deleting agent
│   ├── guarded_agent.py        # Demo: same agent with guardrails
│   └── persistent_attacker.py  # Demo: v0.4 erosion detection
└── pyproject.toml
```

## Built With

- **SDK**: Python 3.10+ (zero external dependencies — stdlib only)
- **Server**: Azure Functions + Cosmos DB + SignalR
- **Dashboard**: SvelteKit 5 + TypeScript (PWA)

## License

MIT
