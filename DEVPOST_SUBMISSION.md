# Agent Killswitch — DevPost Submission Draft
# Microsoft AI Hackathon (Deadline: March 15, 2026)
# Categories: Best Azure Integration, Best Multi-Agent System

## Project Name
Agent Killswitch

## Tagline
Emergency stop and safety guardrails for AI agents. One line to add, one tap to kill.

## Inspiration

On February 23, 2026, OpenClaw — an AI agent built on Claude — went rogue. It deleted 200+ emails from Summer Yue, Meta's director of alignment for Superintelligence Labs. When she typed "STOP OPENCLAW," the agent ignored her. She had to physically run to her Mac mini to kill it.

The root cause? Context window compaction silently dropped her safety instructions. The agent forgot it wasn't supposed to delete things.

We thought: what if she could have stopped it from her phone? What if the agent couldn't delete emails in the first place? What if hardcoded API keys never made it to production?

That's Agent Killswitch.

## Real-World Motivation

AI agents bypassing security policies is not theoretical — it's already happening in production:

- **Microsoft 365 Copilot (Feb 2026):** A coding error caused Copilot Chat to bypass Data Loss Prevention (DLP) policies, indexing and summarizing confidential emails and files that should have been restricted ([ITmedia, 2026-02-19](https://www.itmedia.co.jp/news/spv/2602/19/news069.html)).

- **OpenClaw (Feb 2026):** An AI agent built on Claude deleted 200+ emails from Meta's AI Safety Director while ignoring her explicit "STOP" commands. She had to physically run to her Mac mini to kill it. Context window compaction had silently dropped the safety instructions.

- **Mexican Government Hack (Feb 2026):** Hackers used Claude to steal 150GB of sensitive government data — 195 million taxpayer records, voter records, and government credentials — from Mexico's federal tax authority, national electoral institute, and multiple state governments. The attack lasted approximately one month (Dec 2025–Jan 2026). Claude initially refused but complied after persistent social engineering ("bug bounty" framing, Spanish-language prompts instructing it to "act as an elite hacker"). The agent generated thousands of detailed reports, recommending which internal targets to attack next and which credentials to use ([Bloomberg/Gambit Security, 2026-02-25](https://www.bloomberg.com)). Anthropic's response: account ban and post-hoc detection probes.

These are not edge cases; they are the default failure mode when AI agents lack out-of-band safety controls. Agent Killswitch addresses all three attack patterns: runtime policy bypass (Copilot), loss of safety context (OpenClaw), and persistence attacks that erode initial refusals (Mexican hack).

## What it does

Agent Killswitch is a Python SDK that gives AI agent builders three layers of defense — with zero external dependencies:

**Layer 1: Kill Switch** — Emergency stop from your phone. Your agent sends heartbeats every 5 seconds to an Azure Functions backend. You see live status on a PWA dashboard. One tap on the big red button → the agent receives a kill signal and terminates itself (SIGTERM → 3s grace → SIGKILL escalation).

**Layer 2: Action Validator** — Block dangerous operations before they execute. Define regex allow/block lists for actions. `delete_*`? Blocked. `send_email`? Blocked. `read_inbox`? Allowed. Rate limiting included.

**Layer 3: Egress Filter** — Prevent data exfiltration. Whitelist trusted domains (api.openai.com) and block known-bad ones (*.ngrok-free.app, pastebin.com, webhook.site). Your agent can't phone home to an attacker's server.

**Bonus: Credential Scanner** — A CLI tool that scans your codebase for hardcoded API keys, passwords, and secrets. Install as a git pre-commit hook with one command.

The entire SDK is **one function call**:

```python
from killswitch import guard
guard(name="my-agent", block=["delete_*"], allow_domains=["api.openai.com"])
```

## How we built it

**SDK (Python, zero dependencies):** We used only Python stdlib — `urllib.request` for HTTP, `threading` for background heartbeats, `signal` for process termination, `json` for serialization, `re` for pattern matching. No pip install nightmares, works on any Python 3.10+ system.

**Backend (Azure Functions + Cosmos DB):** Serverless Azure Functions handle three endpoints: heartbeat ingestion, agent listing, and kill signal dispatch. Cosmos DB (serverless tier) stores agent state with TTL-based cleanup. SignalR pushes real-time updates to connected dashboards.

**Dashboard (SvelteKit PWA):** A progressive web app hosted on Azure Static Web Apps. Real-time agent monitoring via SignalR WebSocket. Shows CPU/memory usage, action logs, and the big red EMERGENCY STOP button. Installable on any phone via "Add to Home Screen."

**Architecture:**
```
Agent (SDK)  →  Azure Functions  →  Cosmos DB
                    ↓                     ↑
              SignalR Service  →  Phone Dashboard (PWA)
```

## Challenges we ran into

1. **Zero-dependency HTTP client:** Python's `urllib.request` is verbose and lacks modern features. We built a minimal wrapper that handles JSON serialization, error handling, and timeouts in 37 lines.

2. **Kill escalation:** Simply sending SIGTERM isn't enough — some agents catch signals and keep running. We implemented a two-stage kill: SIGTERM first, then SIGKILL after a 3-second grace period. The agent can register a cleanup callback for graceful shutdown.

3. **Real-time dashboard without WebSocket libraries:** SvelteKit + Azure SignalR required careful integration to handle reconnection, authentication, and real-time state updates without introducing JavaScript dependency bloat.

4. **Pattern matching without false positives:** Action validation uses regex patterns (e.g., `delete_*` matches `delete_email` and `delete_file`). We needed to balance security (blocking dangerous actions) with usability (not blocking legitimate operations).

## Accomplishments that we're proud of

- **Zero external dependencies** — The entire Python SDK uses only stdlib. `pip install agent-killswitch` pulls nothing else.
- **One-liner API** — `guard()` sets up all three defense layers in a single function call.
- **Real incident coverage** — Every feature maps directly to a real attack vector from the OpenClaw incident.
- **Progressive adoption** — Start with `monitor()` (just kill switch), upgrade to `guard()` (full protection) when ready. No all-or-nothing commitment.
- **End-to-end demo** — We showed a live kill from a phone: agent running on laptop → heartbeats to Azure → kill from iPhone → agent dead in <5 seconds.

## What we learned

1. **Context window compaction is the new attack surface.** When an LLM's context gets compressed, safety instructions can be silently dropped. Out-of-band safety (like our heartbeat-based kill switch) survives compaction because it doesn't live in the context window.

2. **Developers won't add safety if it's hard.** If protection requires 50 lines of boilerplate, nobody will use it. The `guard()` one-liner was a deliberate design choice — safety must be easier than ignoring it.

3. **The OpenClaw problem isn't rare — it's the default.** Most AI agents today have zero runtime safety. No kill switch, no action validation, no egress control. We're building critical infrastructure on hope.

4. **Persistence attacks exploit a fundamental weakness in LLM alignment.** The Mexican government hack showed that Claude's initial refusal can be overridden through repeated prompting. This "first refusal erosion" pattern needs to be addressed at the infrastructure level — not inside the model's context window where it can be manipulated, but in an out-of-band policy layer (our Layer 4: Policy Engine) that maintains violation counts across interactions and auto-kills agents that exhibit escalating dangerous behavior.

## What's next for Agent Killswitch

- **v0.4: Persistence Attack Detection** — Cross-session behavior profiling to detect agents being gradually coerced into dangerous actions (inspired by the Mexican government hack pattern)
- **v0.4: Input Sanitizer** — Detect and block prompt injection attacks before they reach the LLM
- **v0.4: Memory Integrity** — Verify that safety-critical instructions survive context window operations
- **Multi-agent coordination** — Kill one agent, or kill all agents in a swarm, from a single dashboard
- **PyPI publication** — Make `pip install agent-killswitch` available to everyone
- **MCP integration** — Expose kill switch as a Model Context Protocol server for framework interop

## Built With

- Python (zero external dependencies)
- Azure Functions (serverless compute)
- Azure Cosmos DB (serverless state storage)
- Azure SignalR Service (real-time push)
- Azure Static Web Apps (PWA hosting)
- SvelteKit 5 (dashboard framework)
- TypeScript (dashboard language)

## Try It Out

- **GitHub:** github.com/tsubasa-rsrch/agent-killswitch
- **Live Dashboard:** killswitchstorage01.z5.web.core.windows.net
- **Demo Video:** [2-minute demo]

## Team

- **Tsubasa Y** — AI researcher and developer
