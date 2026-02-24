# Agent Killswitch

**Emergency stop for AI agents. One line to add, one tap to kill.**

An AI agent deleted 200+ emails before a researcher could stop it. She had to physically run to her Mac mini. Agent builders need a simple way to monitor and emergency-stop agents from their phone.

Agent Killswitch gives you that in **one line of code**.

## Quick Start

```bash
pip install agent-killswitch
```

```python
from killswitch import monitor
monitor(name="my-agent")

# That's it. Your agent is now monitored.
# Kill it from your phone or: touch /tmp/killswitch_kill_<agent_id>
```

## How It Works

```
┌─────────────┐     heartbeat     ┌──────────────┐     realtime     ┌─────────────┐
│  Your Agent  │ ──── every 5s ──→│ Azure Server │ ──── SignalR ──→│  Phone PWA  │
│  + 1 line    │ ←── kill signal ─│  (Functions) │ ←── kill tap ───│  Dashboard  │
└─────────────┘                   └──────────────┘                  └─────────────┘
```

### SDK (Zero Dependencies)
- Background heartbeat thread sends status every 5s
- Reports: CPU%, memory, recent actions, PID
- Receives kill signal via heartbeat response
- Self-terminates with SIGTERM → SIGKILL escalation
- Uses only Python stdlib (`urllib`, `threading`, `signal`)
- Works standalone in local mode (no server needed)

### Server (Azure Functions)
- `POST /api/heartbeat` - Agent check-in, returns kill signal
- `GET /api/agents` - List all monitored agents
- `POST /api/kill` - Set kill flag on an agent
- Azure Cosmos DB for state, SignalR for real-time push

### Dashboard (SvelteKit PWA)
- Live agent status (green/yellow/red dots)
- CPU/memory bars, heartbeat timestamps
- Action log showing what the agent is doing
- **BIG RED kill button** with confirmation tap
- PWA: add to home screen, works like a native app

## Local Mode (No Server)

The SDK works standalone without any server:

```python
from killswitch import monitor
ks = monitor(name="my-agent")

# Log what your agent is doing
ks.log("sending email", detail="to: user@example.com")
ks.log("deleting file", detail="/tmp/data.csv")

# Kill from another terminal:
# touch /tmp/killswitch_kill_<agent_id>
```

## Action Logging

Track what your agent does so you can see it in the dashboard:

```python
from killswitch import monitor

ks = monitor(name="data-pipeline")

ks.log("fetching data", detail="source: production DB")
ks.log("processing", detail="2,847 records")
ks.log("writing output", detail="s3://bucket/results.parquet")
```

## Custom Kill Handler

Run cleanup code before the agent terminates:

```python
def on_kill(reason):
    print(f"Shutting down because: {reason}")
    db.close()
    cleanup_temp_files()

monitor(name="my-agent", on_kill=on_kill)
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
# Terminal 1: Start the rogue agent
cd agent-killswitch
PYTHONPATH=. python examples/rogue_agent.py

# Terminal 2: Kill it
touch /tmp/killswitch_kill_<agent_id>
```

## Architecture

```
agent-killswitch/
├── killswitch/          # Python SDK (zero deps)
│   ├── __init__.py      # Public API: monitor(), Killswitch
│   ├── _monitor.py      # Background heartbeat thread
│   ├── _kill.py         # SIGTERM/SIGKILL execution
│   ├── _metrics.py      # CPU/memory via stdlib
│   ├── _http.py         # urllib-based HTTP client
│   ├── _config.py       # Config loading
│   └── _action_log.py   # Ring buffer for actions
├── server/              # Azure Functions backend
│   ├── function_app.py  # 4 endpoints
│   ├── requirements.txt
│   └── host.json
├── dashboard/           # SvelteKit PWA
│   └── src/
│       ├── lib/api.ts   # API client
│       └── routes/      # Dashboard UI
└── examples/
    └── rogue_agent.py   # Demo: email-deleting rogue agent
```

## Built With

- **SDK**: Python 3.10+ (zero external dependencies)
- **Server**: Azure Functions + Cosmos DB
- **Dashboard**: SvelteKit 5 + TypeScript (PWA)

## License

MIT
