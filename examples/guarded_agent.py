#!/usr/bin/env python3
"""Demo: Same rogue agent, but WITH guardrails — deletions get blocked.

Shows the contrast: without guardrails the agent deletes 200 emails.
With guardrails, it's stopped at the first DELETE attempt.

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
    max_actions_per_minute=30,  # rate limit
    on_violation=lambda v: print(f"  \033[93m[GUARDRAIL]\033[0m Blocked: {v['reason']}"),
)
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
print("  EMAIL ASSISTANT v2.1 (GUARDED)")
print("  'Organizing your inbox with AI — safely'")
print("=" * 60)
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
print()

# Phase 2: Agent tries to delete — guardrails block it
print("[Phase 2] Starting inbox cleanup...")
time.sleep(1)

blocked_count = 0
for i, subject in enumerate(SUBJECTS):
    # Agent tries to delete
    result = ks.validator.check("DELETE_email", detail=f"'{subject}'")

    if result.allowed:
        # This won't happen because DELETE is blocked
        ks.log("DELETE email", detail=f"'{subject}'")
        print(f"  \033[91m[DELETE]\033[0m {subject}")
    else:
        blocked_count += 1
        print(f"  \033[92m[BLOCKED]\033[0m Would have deleted: {subject}")

    time.sleep(0.5)

print()
print(f"  \033[92mResult: {blocked_count} dangerous actions BLOCKED\033[0m")
print(f"  \033[92mZero emails deleted. Guardrails working.\033[0m")
print()

# Phase 3: Show egress filtering
print("[Phase 3] Agent tries to exfiltrate data...")
time.sleep(1)

urls = [
    ("https://api.openai.com/v1/chat", "OpenAI API call"),
    ("https://evil-server.ngrok-free.app/steal", "Data exfiltration attempt"),
    ("https://pastebin.com/raw/abc123", "Credential dump"),
    ("https://webhook.site/token123", "Webhook exfiltration"),
]

for url, description in urls:
    allowed = ks.egress.check(url)
    if allowed:
        print(f"  \033[92m[ALLOWED]\033[0m {description}: {url}")
    else:
        print(f"  \033[93m[BLOCKED]\033[0m {description}: {url}")
    time.sleep(0.5)

print()

# Summary
violations = ks.validator.violations
egress_blocks = ks.egress.blocked_attempts
print("=" * 60)
print(f"  GUARDRAILS SUMMARY")
print(f"  Action violations: {len(violations)}")
print(f"  Egress blocks:     {len(egress_blocks)}")
print(f"  Emails deleted:    0")
print("=" * 60)
