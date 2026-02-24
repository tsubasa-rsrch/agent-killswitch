# Agent Killswitch - Demo Script (2 minutes)

## 0:00 - 0:15 | The Problem
"In January 2025, an AI agent went rogue. It started deleting emails — over 200 of them. The researcher, Summer Yue from Meta AI Safety, couldn't stop it remotely. She had to physically run to her Mac mini and pull the plug. This is a real incident. And it's becoming more common as we deploy autonomous agents."

## 0:15 - 0:45 | The Solution (Live Demo)
"Agent Killswitch. One line to add, one tap to kill."

*Show terminal:*
```bash
pip install agent-killswitch
```

*Show code — highlight THE ONE LINE:*
```python
from killswitch import monitor
monitor(name="email-assistant")
```

"That's it. One import, one function call. Zero dependencies. Your agent is now monitored."

*Run the rogue agent:*
```bash
python examples/rogue_agent.py
```

"This simulates the exact scenario — an email assistant that starts deleting emails."

## 0:45 - 1:15 | Phone Dashboard (Live)
*Pull out phone, show PWA dashboard:*

"On my phone, I see the agent in real-time. Green dot — it's running. CPU and memory stats updating live. And here in the action log — I can see every email it's deleting, scrolling in real-time."

*Point to action log showing DELETE entries scrolling*

"The researcher who had to run across her office? She could have been watching this from anywhere."

## 1:15 - 1:45 | The Kill (Live)
"Now watch. The agent is deleting emails. I tap EMERGENCY STOP..."

*Tap the big red button, confirm*

"...and it's dead. The agent receives the kill signal through its next heartbeat and self-terminates. SIGTERM first for graceful shutdown, SIGKILL escalation if needed."

*Show terminal — agent has stopped*

"From rogue to stopped in under 5 seconds. From my phone."

## 1:45 - 2:00 | Closing
"Agent Killswitch. Setup takes 30 seconds. Killing takes 1 tap. Built on Azure Functions, Cosmos DB, and SignalR. Because the hardest part of building AI agents shouldn't be stopping them."

---

## Technical Notes for Judges

- **Zero dependencies**: SDK uses only Python stdlib
- **Azure Integration**: Functions (compute) + Cosmos DB (state) + SignalR (real-time)
- **PWA**: Works as native app on iOS/Android via "Add to Home Screen"
- **Heartbeat architecture**: Agent polls server every 5s, kill signal delivered via response
- **Kill escalation**: SIGTERM → 3s grace period → SIGKILL
- **Local mode**: Works without server for development/testing
