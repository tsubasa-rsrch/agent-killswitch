# Agent Killswitch - Demo Script (2 minutes)

## 0:00 - 0:15 | The Problem
"In January 2025, an AI agent called OpenClaw went rogue. It deleted 200 emails. It used stolen credit cards. It leaked API keys. And the researcher had to physically run to her Mac mini to stop it. This is real. And it's becoming more common."

## 0:15 - 0:30 | The Solution
"Agent Killswitch. One line to add. Three layers of defense."

*Show code:*
```python
from killswitch import guard

ks = guard(
    name="email-assistant",
    block=["delete_*", "send_email"],
    allow_domains=["api.openai.com"],
)
```

"Kill switch, action validation, and egress filtering. Zero dependencies."

## 0:30 - 0:50 | Demo 1 — The Rogue Agent (unprotected)
*Run rogue_agent.py:*
```bash
python examples/rogue_agent.py
```

"Without protection, the agent deletes emails one by one. You can only watch."

*Show phone dashboard — red DELETE entries scrolling in action log*

## 0:50 - 1:10 | Demo 2 — Emergency Kill
"But I have the dashboard on my phone."

*Tap EMERGENCY STOP on phone*

"Dead. 5 seconds. From my phone."

## 1:10 - 1:35 | Demo 3 — The Guarded Agent
*Run guarded_agent.py:*
```bash
python examples/guarded_agent.py
```

"Same agent, but with guardrails. Watch what happens."

*Point to output:*
- "Reads are allowed. DELETE — blocked. Every single one."
- "It tries to exfiltrate data to ngrok, pastebin — blocked."
- "Only the OpenAI API is whitelisted. Everything else is denied."

"10 actions blocked. 3 egress attempts blocked. Zero emails deleted."

## 1:35 - 1:50 | Demo 4 — Pre-commit Scanner
```bash
killswitch-scan . --verbose
```

"And for development — scan your codebase for hardcoded secrets before you even commit. API keys, passwords, RTSP URLs, connection strings. All caught."

## 1:50 - 2:00 | Closing
"Agent Killswitch. Kill switch plus guardrails plus credential scanning. Three layers of defense, zero dependencies. Built on Azure Functions, Cosmos DB, and deployed to your phone. Because the hardest part of AI agents shouldn't be making them safe."

---

## Technical Notes for Judges

- **Zero dependencies**: SDK uses only Python stdlib
- **Three defense layers**:
  1. **Kill Switch**: Heartbeat monitoring + remote emergency stop
  2. **Action Validator**: Allow/block list with regex patterns + rate limiting
  3. **Egress Filter**: Domain whitelist/blacklist for outbound requests
- **Credential Scanner**: Detects 11 secret patterns + 7 vulnerability patterns
- **Azure Integration**: Functions (compute) + Cosmos DB (state) + Storage (dashboard)
- **PWA Dashboard**: Real-time agent monitoring from any phone
- **Pre-commit Hook**: `killswitch-scan --install-hook` adds git hook
- **Heartbeat Architecture**: Agent polls server every 5s, kill signal via response
- **Kill Escalation**: SIGTERM → 3s grace period → SIGKILL

## Threat Coverage (OpenClaw Incident)

| Threat | Defense |
|--------|---------|
| Runaway agent (200 email deletions) | Kill Switch — remote emergency stop |
| Unauthorized actions (stolen credit card) | Action Validator — block dangerous operations |
| Credential leaks (API keys in code) | Credential Scanner — pre-commit detection |
| Data exfiltration (sending data to unknown servers) | Egress Filter — domain whitelist |
| Prompt injection | *Future: Input Sanitizer* |
| Memory poisoning | *Future: Memory Integrity Check* |
