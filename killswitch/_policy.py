"""Policy Engine — track violations, score severity, auto-kill when threshold exceeded.

The missing link between guardrails (detection) and killswitch (termination).
Three severity levels, configurable thresholds, automatic escalation.

MS365 Copilot bypassed DLP silently. OpenClaw ignored stop commands.
This ensures: detect → alert → kill, automatically.
"""

import time
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


# Severity levels and their default point values
SEVERITY_POINTS = {
    "critical": 100,  # Instant kill (e.g., credential exfiltration)
    "high": 25,       # Dangerous action (e.g., mass deletion)
    "medium": 5,      # Suspicious action (e.g., unexpected domain)
    "low": 1,         # Minor policy deviation (e.g., rate limit)
}


@dataclass
class Violation:
    """A single policy violation event."""
    severity: str
    action: str
    reason: str
    detail: str = ""
    points: int = 0
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if self.points == 0:
            self.points = SEVERITY_POINTS.get(self.severity, 1)

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "action": self.action,
            "reason": self.reason,
            "detail": self.detail[:200],  # Truncate for heartbeat payload
            "points": self.points,
            "t": self.timestamp,
        }


class PolicyEngine:
    """Track violations, accumulate score, trigger auto-kill.

    Usage:
        policy = PolicyEngine(kill_threshold=100, on_alert=my_callback)
        policy.report("high", "delete_email", "Mass deletion attempt", detail="200 emails")

        # Check current threat level
        level = policy.threat_level  # "green", "yellow", "orange", "red"
        score = policy.score

        # Wire into Killswitch for auto-kill
        policy.attach(killswitch_instance)
    """

    def __init__(
        self,
        kill_threshold: int = 100,
        alert_threshold: int = 25,
        window_seconds: int = 300,  # 5 minute sliding window
        on_alert: Optional[Callable] = None,
        on_kill: Optional[Callable] = None,
        auto_kill: bool = True,
    ):
        self.kill_threshold = kill_threshold
        self.alert_threshold = alert_threshold
        self.window_seconds = window_seconds
        self.on_alert = on_alert
        self.on_kill = on_kill
        self.auto_kill = auto_kill

        self._violations: List[Violation] = []
        self._lock = threading.Lock()
        self._killswitch = None  # Attached Killswitch instance
        self._killed = False

    def attach(self, killswitch) -> None:
        """Attach to a Killswitch instance for auto-kill capability."""
        self._killswitch = killswitch

    def report(
        self,
        severity: str,
        action: str,
        reason: str,
        detail: str = "",
        points: int = 0,
    ) -> Violation:
        """Report a policy violation. Returns the violation object.

        If accumulated score exceeds kill_threshold, triggers auto-kill.
        """
        severity = severity.lower()
        if severity not in SEVERITY_POINTS:
            severity = "medium"

        violation = Violation(
            severity=severity,
            action=action,
            reason=reason,
            detail=detail,
            points=points,
        )

        with self._lock:
            self._violations.append(violation)

        # Check thresholds
        current_score = self.score
        if current_score >= self.alert_threshold and self.on_alert:
            self.on_alert(violation, current_score, self.threat_level)

        if current_score >= self.kill_threshold and self.auto_kill and not self._killed:
            self._trigger_auto_kill(violation, current_score)

        return violation

    def _trigger_auto_kill(self, trigger_violation: Violation, score: int) -> None:
        """Execute auto-kill via attached Killswitch."""
        self._killed = True
        reason = (
            f"Policy auto-kill: score {score}/{self.kill_threshold} "
            f"(trigger: {trigger_violation.severity} - {trigger_violation.reason})"
        )

        if self.on_kill:
            self.on_kill(trigger_violation, score)

        if self._killswitch:
            self._killswitch._execute_kill(reason)

    @property
    def score(self) -> int:
        """Current violation score within the sliding window."""
        cutoff = time.time() - self.window_seconds
        with self._lock:
            return sum(v.points for v in self._violations if v.timestamp > cutoff)

    @property
    def total_score(self) -> int:
        """Total violation score (all time, no window)."""
        with self._lock:
            return sum(v.points for v in self._violations)

    @property
    def threat_level(self) -> str:
        """Current threat level based on score vs thresholds."""
        s = self.score
        if s >= self.kill_threshold:
            return "red"
        elif s >= self.alert_threshold:
            return "orange"
        elif s > 0:
            return "yellow"
        return "green"

    @property
    def violations(self) -> List[Violation]:
        """All recorded violations."""
        with self._lock:
            return list(self._violations)

    def recent_violations(self, n: int = 5) -> List[dict]:
        """Get the N most recent violations as dicts (for heartbeat payload)."""
        with self._lock:
            recent = self._violations[-n:]
        return [v.to_dict() for v in recent]

    @property
    def summary(self) -> dict:
        """Summary for heartbeat/dashboard."""
        with self._lock:
            window_violations = [
                v for v in self._violations
                if v.timestamp > time.time() - self.window_seconds
            ]
        return {
            "score": self.score,
            "total_score": self.total_score,
            "threat_level": self.threat_level,
            "kill_threshold": self.kill_threshold,
            "violations_in_window": len(window_violations),
            "total_violations": len(self._violations),
            "auto_kill": self.auto_kill,
        }

    def make_validator_callback(self) -> Callable:
        """Create a callback for ActionValidator.on_violation that reports to this engine."""
        def callback(violation_dict: dict):
            action = violation_dict.get("action", "unknown")
            reason = violation_dict.get("reason", "")
            detail = violation_dict.get("detail", "")
            rule = violation_dict.get("rule", "")

            # Map validator violations to severity
            # Blocked actions are "medium" — they were caught and didn't execute
            # Rate limits are "low" — just throttling
            severity = "medium"
            if "rate_limit" in rule:
                severity = "low"

            self.report(severity, action, reason, detail=detail)

        return callback

    def make_egress_callback(self) -> Callable:
        """Create a callback for EgressFilter.on_block that reports to this engine."""
        def callback(block_dict: dict):
            url = block_dict.get("url", "unknown")
            domain = block_dict.get("domain", "")
            reason = block_dict.get("reason", "")

            # Egress violations are high severity (potential data exfiltration)
            severity = "critical" if "blacklisted" in reason else "high"

            self.report(severity, f"egress:{domain}", reason, detail=url)

        return callback
