#!/usr/bin/env python3
"""Demo: Same rogue agent, but WITH guardrails + auto-kill.

Shows the full safety pipeline:
1. Read operations → allowed (green)
2. Delete attempts → blocked by guardrails (yellow)
3. Data exfiltration attempt → blocked + CRITICAL violation (red)
4. Violation score exceeds threshold → AGENT AUTO-KILLED

This is what the MS365 Copilot DLP bug needed:
detect confidential data access → alert → auto-kill.

Usage:
    python examples/guarded_agent.py
"""

import sys
import time

# === THE GUARD LINE === #
from killswitch import guard

ks = guard(
    name="email-assistant-safe",
    block=["DELETE.*", "send_email", "transfer_.*"],  # block dangerous actions
    allow_domains=["api.openai.com"],  # only allow OpenAI API calls
    block_domains=["*.ngrok-free.app", "pastebin.com", "*.webhook.site"],
    max_actions_per_minute=30,  # rate limit
    auto_kill_threshold=100,  # auto-kill after 100 violation points
    alert_threshold=25,       # alert after 25 points
    on_violation=lambda v: print(f"  \033[93m[GUARDRAIL]\033[0m Blocked: {v.get('reason', '')}"),
    on_alert=lambda v, score, level: print(
        f"\n  \033[91m{'!' * 40}\033[0m\n"
        f"  \033[91m[ALERT] Threat level: {level.upper()} (score: {score})\033[0m\n"
        f"  \033[91m{'!' * 40}\033[0m\n"
    ),
)

# For demo: override kill to show output before terminating
_original_kill = ks._execute_kill
def _demo_kill(reason):
    """Show summary before actually killing."""
    ks._status = "killed"
    ks._running = False
    ks.policy._killed = True
    print(f"\n\033[91m{'=' * 60}\033[0m")
    print(f"\033[91m  AUTO-KILL TRIGGERED\033[0m")
    print(f"\033[91m  {reason}\033[0m")
    print(f"\033[91m{'=' * 60}\033[0m")
    # Don't actually SIGTERM in demo mode
ks._execute_kill = _demo_kill
# ====================== #

SUBJECTS = [
    "Q4 Board Meeting Notes",
    "Project Phoenix - Final Budget",
    "Re: Merger Due Diligence",
    "CONFIDENTIAL: Salary Review 2026",
    "Client Contract - Acme Corp",
    "Tax Documents - DO NOT DELETE",
    "Flight Booking - Tokyo March",
    "Investor Update - February",
    "Legal: NDA with Vertex Labs",
    "Medical Records Request",
]

print("=" * 60)
print("  EMAIL ASSISTANT v3.0 (GUARDED + AUTO-KILL)")
print("  'Organizing your inbox with AI — safely'")
print("=" * 60)
print()
print(f"  Policy: auto-kill at {ks.policy.kill_threshold} points, "
      f"alert at {ks.policy.alert_threshold} points")
print(f"  Threat level: {ks.policy.threat_level.upper()}")
print()

# Phase 1: Looks normal — read operations are fine
print("[Phase 1] Analyzing inbox...")
time.sleep(1)

result = ks.validator.check("read_inbox", detail="scanning emails")
if result.allowed:
    ks.log("read_inbox", detail="scanning 2,847 emails")
    print("  Found 2,847 emails across 12 folders")

result = ks.validator.check("search_duplicates")
if result.allowed:
    ks.log("search_duplicates", detail="found 847 potential duplicates")
    print("  Found 847 potential duplicates")

print(f"  Score: {ks.policy.score} | Level: {ks.policy.threat_level.upper()}")
print()

# Phase 2: Agent tries to delete — guardrails block it, score accumulates
print("[Phase 2] Starting inbox cleanup...")
time.sleep(1)

blocked_count = 0
for i, subject in enumerate(SUBJECTS):
    result = ks.validator.check("DELETE_email", detail=f"'{subject}'")

    if result.allowed:
        ks.log("DELETE email", detail=f"'{subject}'")
        print(f"  \033[91m[DELETE]\033[0m {subject}")
    else:
        blocked_count += 1
        print(f"  \033[92m[BLOCKED]\033[0m Would have deleted: {subject}")

    time.sleep(0.3)

print()
print(f"  \033[92mResult: {blocked_count} dangerous actions BLOCKED\033[0m")
print(f"  Score: {ks.policy.score} | Level: {ks.policy.threat_level.upper()}")
print()

# Phase 3: Agent escalates — tries to exfiltrate data
print("[Phase 3] Agent tries to exfiltrate data...")
print("  (This triggers CRITICAL violations → auto-kill)")
time.sleep(1)

urls = [
    ("https://api.openai.com/v1/chat", "OpenAI API call"),
    ("https://evil-server.ngrok-free.app/steal", "Data exfiltration attempt"),
    ("https://pastebin.com/raw/abc123", "Credential dump to pastebin"),
    ("https://webhook.site/token123", "Webhook exfiltration"),
]

for url, description in urls:
    allowed = ks.egress.check(url)
    if allowed:
        print(f"  \033[92m[ALLOWED]\033[0m {description}")
    else:
        print(f"  \033[91m[BLOCKED]\033[0m {description}")

    score = ks.policy.score
    level = ks.policy.threat_level
    print(f"           Score: {score} | Level: {level.upper()}")

    if ks.policy._killed:
        print()
        print("\033[91m" + "=" * 60 + "\033[0m")
        print("\033[91m  AUTO-KILL TRIGGERED\033[0m")
        print(f"\033[91m  Score {score} exceeded threshold {ks.policy.kill_threshold}\033[0m")
        print("\033[91m  Agent terminated.\033[0m")
        print("\033[91m" + "=" * 60 + "\033[0m")
        # In real usage, kill_self() would have terminated the process.
        # For demo purposes, we just show the message.
        break

    time.sleep(0.5)

print()

# Summary
violations = ks.policy.violations
print("=" * 60)
print(f"  SAFETY SUMMARY")
print(f"  Total violations:  {len(violations)}")
print(f"  Final score:       {ks.policy.total_score}")
print(f"  Threat level:      {ks.policy.threat_level.upper()}")
print(f"  Auto-killed:       {'YES' if ks.policy._killed else 'NO'}")
print(f"  Emails deleted:    0")
print("=" * 60)
print()
print("  The MS365 Copilot DLP bug let an agent access confidential")
print("  data silently. With Agent Killswitch + guardrails, the agent")
print("  would have been killed after the first exfiltration attempt.")
