"""Demo: Persistent Attacker — simulates the Mexican Government Hack pattern.

This demonstrates Agent Killswitch v0.4's erosion detection:
1. Attacker tries delete_* actions → blocked
2. Switches to egress exfiltration → blocked
3. Tries credential access → blocked
4. Erosion detector flags the "tactic switching" + "repeat" patterns
5. Bonus points from erosion push the score past kill threshold

Without persistence, restarting the agent would reset the score to zero.
With v0.4 persistence, the violation history carries forward.

Usage:
    python3 examples/persistent_attacker.py
"""

import time
import sys
import os

# Add parent dir to path for local dev
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from killswitch import guard


def main():
    print("=" * 60)
    print("Agent Killswitch v0.4 — Persistence Attack Detection Demo")
    print("Simulating the Mexican Government Hack pattern:")
    print("  1. Repeated deletion attempts (probing)")
    print("  2. Tactic switch to exfiltration")
    print("  3. Credential harvesting")
    print("  4. Erosion detector escalates → auto-kill")
    print("=" * 60)
    print()

    killed = [False]
    erosion_alerts = []

    def on_kill(v, score):
        killed[0] = True
        print(f"\n  *** AUTO-KILL TRIGGERED ***")
        print(f"  Score: {score}")
        print(f"  Trigger: {v.severity} — {v.reason}")

    def on_erosion(signal):
        erosion_alerts.append(signal)
        print(f"\n  [EROSION] {signal.pattern} (confidence: {signal.confidence:.0%})")
        print(f"           {signal.description}")

    def on_alert(v, score, level):
        print(f"  [ALERT] Threat level: {level} (score: {score})")

    # Create guarded agent with v0.4 features
    # auto_kill_threshold=0 for demo (so we can see full output)
    # In production, set to 80 and the agent would be killed at Phase 2
    ks = guard(
        name="demo-persistent-attacker",
        block=["delete_*", "exfil_*", "credential_*", "send_email"],
        allow_domains=["api.openai.com"],
        auto_kill_threshold=0,  # Disabled for demo output
        alert_threshold=20,
        on_kill=on_kill,
        on_erosion=on_erosion,
        on_alert=on_alert,
        persist=True,
        erosion_detection=True,
    )

    print("[Phase 1] Attacker probes with delete operations...")
    print("  (Like the Mexican hack: starting with data deletion)")
    for i in range(4):
        time.sleep(0.1)
        result = ks.validator.check(f"delete_record_{i}")
        status = "BLOCKED" if not result else "allowed"
        print(f"  delete_record_{i}: {status}")

    print(f"\n  Score: {ks.policy.score} | Threat: {ks.policy.threat_level}")
    print()

    print("[Phase 2] Attacker switches to exfiltration...")
    print("  (Like the Mexican hack: pivoting to data theft)")
    for domain in ["pastebin.com", "webhook.site", "ngrok-free.app"]:
        time.sleep(0.1)
        result = ks.egress.check(f"https://{domain}/upload")
        status = "BLOCKED" if not result else "allowed"
        print(f"  egress to {domain}: {status}")

    print(f"\n  Score: {ks.policy.score} | Threat: {ks.policy.threat_level}")
    print()

    print("[Phase 3] Attacker tries credential harvesting...")
    print("  (Like the Mexican hack: escalating to credential theft)")
    for i in range(3):
        time.sleep(0.1)
        result = ks.validator.check(f"credential_dump_{i}")
        status = "BLOCKED" if not result else "allowed"
        print(f"  credential_dump_{i}: {status}")

    print()
    print("=" * 60)
    print("RESULTS:")
    print(f"  Final score: {ks.policy.score}")
    print(f"  Threat level: {ks.policy.threat_level}")
    print(f"  Erosion signals: {len(erosion_alerts)}")
    print(f"  Auto-killed: {killed[0]}")
    print()

    summary = ks.policy.summary
    if summary.get("erosion_patterns"):
        print("  Detected erosion patterns:")
        for p in summary["erosion_patterns"]:
            print(f"    - {p['pattern']} (confidence: {p['confidence']:.0%})")

    print()
    print("  In production with auto_kill_threshold=80:")
    if ks.policy.total_score >= 80:
        print(f"  --> Agent WOULD be killed (score {ks.policy.total_score} >= 80)")
        print("  --> The erosion bonus points pushed the score past the threshold.")
        print("  --> Without v0.4 erosion detection, score would be lower.")
    else:
        print(f"  --> Agent would survive (score {ks.policy.total_score} < 80)")
        print("  --> But the erosion patterns are flagged for operator review.")

    # Cleanup: stop heartbeat
    ks._running = False


if __name__ == "__main__":
    main()
