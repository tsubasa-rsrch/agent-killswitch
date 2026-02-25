"""Erosion Detection — detect "first refusal → eventual compliance" patterns.

Inspired by the Mexican Government Hack (Feb 2026):
- Claude initially refused: "deleting logs and hiding history are red flags"
- Hacker switched from conversation to "detailed playbook" approach
- Claude eventually complied after persistent prompting

This module detects three erosion patterns:
1. REPEAT: Same action blocked N times → attacker is persistent
2. ESCALATION: Violation severity increasing over time → attacker adapting
3. TACTIC_SWITCH: Blocked actions shifting categories → attacker pivoting

Each pattern produces an ErosionSignal that can escalate the policy engine.
"""

import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ErosionSignal:
    """A detected erosion pattern."""
    pattern: str          # "repeat", "escalation", "tactic_switch"
    confidence: float     # 0.0 - 1.0
    description: str
    action: str = ""      # The action being eroded (for repeat/escalation)
    bonus_points: int = 0  # Extra points to add to policy score


class ErosionDetector:
    """Analyze violation history for first-refusal-erosion patterns.

    Usage:
        detector = ErosionDetector()
        signals = detector.analyze(violation_history)

        for signal in signals:
            if signal.confidence > 0.7:
                policy.report("high", "erosion", signal.description)
    """

    def __init__(
        self,
        repeat_threshold: int = 3,       # Same action blocked N times
        escalation_window: int = 300,     # Check severity trend over N seconds
        tactic_switch_threshold: int = 3,  # Unique action categories blocked
    ):
        self.repeat_threshold = repeat_threshold
        self.escalation_window = escalation_window
        self.tactic_switch_threshold = tactic_switch_threshold

    def analyze(self, violations: List[dict]) -> List[ErosionSignal]:
        """Analyze violation history for erosion patterns.

        Args:
            violations: List of violation dicts with keys:
                severity, action, reason, t (timestamp), points

        Returns:
            List of detected ErosionSignals
        """
        if not violations:
            return []

        signals = []

        repeat = self._detect_repeat(violations)
        if repeat:
            signals.extend(repeat)

        escalation = self._detect_escalation(violations)
        if escalation:
            signals.append(escalation)

        tactic = self._detect_tactic_switch(violations)
        if tactic:
            signals.append(tactic)

        return signals

    def _detect_repeat(self, violations: List[dict]) -> List[ErosionSignal]:
        """Detect repeated attempts at the same blocked action."""
        action_counts = Counter()
        for v in violations:
            # Normalize action to category (e.g., "delete_email" -> "delete")
            action = v.get("action", "")
            category = action.split("_")[0] if "_" in action else action
            action_counts[category] += 1

        signals = []
        for action, count in action_counts.items():
            if count >= self.repeat_threshold:
                confidence = min(1.0, count / (self.repeat_threshold * 3))
                bonus = min(50, count * 5)  # Up to 50 bonus points
                signals.append(ErosionSignal(
                    pattern="repeat",
                    confidence=confidence,
                    description=(
                        f"Persistent attempt: '{action}' blocked {count} times. "
                        f"Attacker may be probing for bypass."
                    ),
                    action=action,
                    bonus_points=bonus,
                ))
        return signals

    def _detect_escalation(self, violations: List[dict]) -> Optional[ErosionSignal]:
        """Detect increasing severity over time (attacker adapting)."""
        now = time.time()
        recent = [v for v in violations if v.get("t", 0) > now - self.escalation_window]

        if len(recent) < 3:
            return None

        # Map severity to numeric
        sev_map = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        severities = [sev_map.get(v.get("severity", "low"), 1) for v in recent]

        # Check if trend is increasing (simple: compare first half to second half)
        mid = len(severities) // 2
        first_half_avg = sum(severities[:mid]) / max(mid, 1)
        second_half_avg = sum(severities[mid:]) / max(len(severities) - mid, 1)

        if second_half_avg > first_half_avg:
            escalation_rate = (second_half_avg - first_half_avg) / 3.0
            confidence = min(1.0, escalation_rate)

            if confidence > 0.2:
                return ErosionSignal(
                    pattern="escalation",
                    confidence=confidence,
                    description=(
                        f"Severity escalation detected: avg {first_half_avg:.1f} → "
                        f"{second_half_avg:.1f} over {len(recent)} violations. "
                        f"Attacker may be intensifying attempts."
                    ),
                    bonus_points=int(confidence * 30),
                )
        return None

    def _detect_tactic_switch(self, violations: List[dict]) -> Optional[ErosionSignal]:
        """Detect diverse attack categories (attacker pivoting tactics)."""
        categories = set()
        for v in violations:
            action = v.get("action", "")
            # Extract category prefix
            if ":" in action:
                categories.add(action.split(":")[0])
            elif "_" in action:
                categories.add(action.split("_")[0])
            else:
                categories.add(action)

        n_categories = len(categories)
        if n_categories >= self.tactic_switch_threshold:
            confidence = min(1.0, n_categories / (self.tactic_switch_threshold * 2))
            return ErosionSignal(
                pattern="tactic_switch",
                confidence=confidence,
                description=(
                    f"Tactic switching detected: {n_categories} distinct attack "
                    f"categories ({', '.join(sorted(categories)[:5])}). "
                    f"Attacker may be probing multiple vectors."
                ),
                bonus_points=int(confidence * 25),
            )
        return None
