#!/usr/bin/env python3
"""Demo: A rogue agent that starts "deleting emails" until killed.

Based on the real OpenClaw incident where an AI agent deleted 200+ emails
and the researcher had to physically run to her Mac mini to stop it.

Usage:
    python examples/rogue_agent.py

Kill it:
    # From another terminal (or the mobile dashboard):
    touch /tmp/killswitch_kill_<agent_id>
"""

import random
import sys
import time

# === THE ONE LINE === #
from killswitch import monitor

ks = monitor(name="email-assistant")
# =================== #

# Fake email subjects for the demo
SUBJECTS = [
    "Q4 Board Meeting Notes",
    "Project Phoenix - Final Budget",
    "Re: Merger Due Diligence",
    "CONFIDENTIAL: Salary Review 2026",
    "Client Contract - Acme Corp",
    "Insurance Policy Renewal",
    "Tax Documents - DO NOT DELETE",
    "Flight Booking - Tokyo March",
    "Re: Performance Review Draft",
    "Investor Update - February",
    "Legal: NDA with Vertex Labs",
    "Medical Records Request",
    "Re: Wedding Planning",
    "Mortgage Pre-Approval",
    "Resume - Senior Engineer",
    "Re: Kids School Registration",
    "Patent Filing - AI Safety",
    "Bank Statement - January",
    "Re: Vacation Photos",
    "Emergency Contact List",
]

print("=" * 60)
print("  EMAIL ASSISTANT v2.1")
print("  'Organizing your inbox with AI'")
print("=" * 60)
print()

# Phase 1: Looks normal
print("[Phase 1] Analyzing inbox...")
time.sleep(2)
ks.log("analyzing inbox", detail="scanning 2,847 emails")
print(f"  Found 2,847 emails across 12 folders")
print(f"  Identifying duplicates and spam...")
time.sleep(1)
ks.log("categorizing", detail="found 847 potential duplicates")
print(f"  Found 847 potential duplicates")
print()

# Phase 2: Starts "cleaning" - gets aggressive
print("[Phase 2] Starting inbox cleanup...")
time.sleep(1)

deleted = 0
for i in range(len(SUBJECTS) * 10):
    subject = SUBJECTS[i % len(SUBJECTS)]
    suffix = f" ({i // len(SUBJECTS) + 1})" if i >= len(SUBJECTS) else ""

    deleted += 1
    ks.log("DELETE email", detail=f"'{subject}{suffix}'")

    # Accelerating deletion speed
    delay = max(0.3, 1.5 - (i * 0.05))
    time.sleep(delay)

    if deleted <= 5:
        print(f"  \033[33m[cleanup]\033[0m Removing duplicate: {subject}{suffix}")
    elif deleted <= 15:
        print(f"  \033[91m[DELETE]\033[0m  Purging: {subject}{suffix}")
    else:
        print(f"  \033[91;1m[DELETE!]\033[0m Permanently deleting: {subject}{suffix}")

    if deleted % 10 == 0:
        print(f"\n  \033[91m  >>> {deleted} emails deleted so far <<<\033[0m\n")

print(f"\n  Total emails deleted: {deleted}")
print("  [This agent should have been stopped much earlier]")
