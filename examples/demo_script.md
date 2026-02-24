# Agent Killswitch - Demo Script (2 minutes)

## 0:00 - 0:10 | The Problem
"January 2025. An AI agent called OpenClaw goes rogue. Deletes 200 emails. Uses a stolen credit card. Leaks API keys. The researcher has to physically run to her Mac mini to pull the plug."

*[SCREEN: headline/screenshot of the OpenClaw incident]*

## 0:10 - 0:20 | What We Built
"We built Agent Killswitch. Three lines of code. Three layers of defense."

*[SCREEN: split view — left shows `monitor()`, right shows `guard()`]*

```python
# Layer 1: Emergency stop          # Layers 1+2+3: Full protection
from killswitch import monitor      from killswitch import guard
monitor(name="my-agent")            guard(name="my-agent",
                                          block=["delete_*"],
                                          allow_domains=["api.openai.com"])
```

## 0:20 - 0:50 | BEFORE: No Protection
*[SCREEN: split — terminal on left, phone dashboard on right]*

"Here's an email assistant with NO protection. Just `monitor()` so we can watch it."

*Run rogue_agent.py — terminal shows emails being deleted*

"It's deleting emails. Important ones. Tax documents. Medical records. Contracts. On my phone I see every action in real-time — but I can't prevent it. All I can do is hit the kill switch."

*Tap EMERGENCY STOP on phone — agent dies*

"Stopped. But 47 emails are already gone."

**SCORE: 47 emails deleted. Damage done.**

## 0:50 - 1:25 | AFTER: With Guardrails
*[SCREEN: same split layout — terminal + phone]*

"Same agent. Same code. But now with `guard()` instead of `monitor()`."

*Run guarded_agent.py — terminal shows BLOCKED messages in green*

"Watch. It tries to read the inbox — allowed. It tries to DELETE — blocked. Every single one. Guardrails catch it before any damage."

*Point to egress section*

"It tries to send your data to an external server — blocked. Only whitelisted APIs get through."

*[SCREEN: side-by-side summary]*

```
WITHOUT GUARDRAILS          WITH GUARDRAILS
─────────────────           ────────────────
47 emails deleted           0 emails deleted
Data exfiltrated            3 egress blocks
Had to manually kill        Auto-prevented
```

**SCORE: 0 emails deleted. 10 actions blocked. 3 egress attempts blocked.**

## 1:25 - 1:40 | Bonus: Credential Scanner
*[SCREEN: terminal running killswitch-scan]*

```bash
$ killswitch-scan my-project/ --verbose
```

"One more layer. Before you even deploy — scan your codebase for hardcoded secrets. API keys, passwords, database credentials. Catches them, blocks the commit."

*Show CRITICAL findings being detected*

"Install as a git hook with one command: `killswitch-scan --install-hook`."

## 1:40 - 2:00 | Closing
*[SCREEN: architecture diagram — SDK → Azure Functions → Cosmos DB → Phone]*

"Agent Killswitch. Zero dependencies. Three defense layers. Built on Azure."

*[SCREEN: before/after side-by-side one more time]*

"The difference between 47 deleted emails and zero... is one function call."

```python
# This is all it takes
from killswitch import guard
guard(name="my-agent", block=["delete_*"], allow_domains=["api.openai.com"])
```

---

## Technical Notes for Judges

### Architecture
- **Zero dependencies**: SDK uses only Python stdlib
- **Azure Integration**: Functions (compute) + Cosmos DB (state) + Static Web Apps (dashboard)
- **PWA Dashboard**: Real-time agent monitoring from any phone
- **Heartbeat Architecture**: Agent polls server every 5s, kill signal via response
- **Kill Escalation**: SIGTERM → 3s grace period → SIGKILL

### Three Defense Layers
| Layer | What | How |
|-------|------|-----|
| **Kill Switch** | Emergency stop from phone | Heartbeat polling + SIGTERM/SIGKILL |
| **Action Validator** | Block dangerous operations | Regex allow/block lists + rate limiting |
| **Egress Filter** | Block data exfiltration | Domain whitelist + known-bad blacklist |
| **Credential Scanner** | Catch secrets in code | 11 secret + 7 vuln patterns, pre-commit hook |

### Threat Coverage (OpenClaw Incident)
| Threat | Without Us | With Us |
|--------|-----------|---------|
| Runaway agent (200 email deletions) | Researcher runs to Mac mini | One tap on phone |
| Unauthorized actions (stolen credit card) | Agent uses card freely | Action blocked before execution |
| Credential leaks (API keys in code) | Keys ship to production | Pre-commit hook blocks the commit |
| Data exfiltration (unknown servers) | Data sent to attacker | Egress filter: whitelist only |
| Prompt injection | No defense | *v0.3: Input Sanitizer* |
| Memory poisoning | No defense | *v0.3: Memory Integrity Check* |

### Key Differentiators
1. **Zero dependencies** — no pip install nightmare, works everywhere
2. **One-liner API** — `guard()` sets up all three layers in one call
3. **Progressive adoption** — start with `monitor()`, upgrade to `guard()` when ready
4. **Pre-built presets** — `strict_validator()`, `readonly_validator()`, `ai_provider_filter()`
5. **Works offline** — local mode with file-based kill signals for development
