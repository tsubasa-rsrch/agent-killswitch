"""Policy Engine — track violations, score severity, auto-kill when threshold exceeded.

The missing link between guardrails (detection) and killswitch (termination).
Four severity levels, configurable thresholds, automatic escalation.

v0.3: In-memory violation tracking with sliding window scoring
v0.4: Persistent violation storage + erosion detection (cross-session)

MS365 Copilot bypassed DLP silently. OpenClaw ignored stop commands.
Mexican Government Hack used 1000+ prompts — first refusal eroded over time.
This ensures: detect → alert → kill, automatically — even across sessions.
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
        # v0.3 mode (in-memory only)
        policy = PolicyEngine(kill_threshold=100, on_alert=my_callback)

        # v0.4 mode (persistent + erosion detection)
        policy = PolicyEngine(
            kill_threshold=100,
            persist=True,
            agent_name="my-agent",
            erosion_detection=True,
        )
        policy.report("high", "delete_email", "Mass deletion attempt")
    """

    def __init__(
        self,
        kill_threshold: int = 100,
        alert_threshold: int = 25,
        window_seconds: int = 300,  # 5 minute sliding window
        on_alert: Optional[Callable] = None,
        on_kill: Optional[Callable] = None,
        on_erosion: Optional[Callable] = None,
        auto_kill: bool = True,
        persist: bool = False,
        agent_name: str = "",
        erosion_detection: bool = False,
        history_hours: int = 168,  # Load 7 days of history
    ):
        self.kill_threshold = kill_threshold
        self.alert_threshold = alert_threshold
        self.window_seconds = window_seconds
        self.on_alert = on_alert
        self.on_kill = on_kill
        self.on_erosion = on_erosion
        self.auto_kill = auto_kill
        self.persist = persist
        self.erosion_detection = erosion_detection

        self._violations: List[Violation] = []
        self._lock = threading.Lock()
        self._killswitch = None  # Attached Killswitch instance
        self._killed = False

        # v0.4: Persistence
        self._store = None
        if persist and agent_name:
            from killswitch._persistence import ViolationStore
            self._store = ViolationStore(agent_name)
            # Load previous violations from disk
            history = self._store.load(max_age_hours=history_hours)
            self._history_violations = history  # Keep raw dicts for erosion
            # Don't add to _violations (those are current-session only for scoring)
            # But erosion detector sees the full history
        else:
            self._history_violations = []

        # v0.4: Erosion detector
        self._erosion_detector = None
        if erosion_detection:
            from killswitch._erosion import ErosionDetector
            self._erosion_detector = ErosionDetector()

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
        Violations are persisted to disk if persist=True.
        Erosion patterns are checked if erosion_detection=True.
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

        # v0.4: Persist to disk
        if self._store:
            self._store.append(violation.to_dict())

        # v0.4: Check erosion patterns (history + current session)
        if self._erosion_detector:
            self._check_erosion(violation)

        # Check thresholds
        current_score = self.score
        if current_score >= self.alert_threshold and self.on_alert:
            self.on_alert(violation, current_score, self.threat_level)

        if current_score >= self.kill_threshold and self.auto_kill and not self._killed:
            self._trigger_auto_kill(violation, current_score)

        return violation

    def _check_erosion(self, latest_violation: Violation) -> None:
        """Run erosion detection on combined history + current session."""
        # Skip erosion check for erosion-generated violations (prevent cascade)
        if latest_violation.action.startswith("erosion:"):
            return

        # Combine historical violations with current session
        # Filter out erosion-generated violations to prevent feedback loops
        current_dicts = [
            v.to_dict() for v in self._violations
            if not v.action.startswith("erosion:")
        ]
        history_filtered = [
            v for v in self._history_violations
            if not v.get("action", "").startswith("erosion:")
        ]
        all_violations = history_filtered + current_dicts

        signals = self._erosion_detector.analyze(all_violations)

        for signal in signals:
            if signal.confidence > 0.3:
                # Add bonus points from erosion to the score (once per pattern)
                if signal.bonus_points > 0:
                    erosion_v = Violation(
                        severity="high",
                        action=f"erosion:{signal.pattern}",
                        reason=signal.description,
                        points=signal.bonus_points,
                    )
                    with self._lock:
                        self._violations.append(erosion_v)

                    if self._store:
                        self._store.append(erosion_v.to_dict())

                # Notify callback
                if self.on_erosion:
                    self.on_erosion(signal)

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
    def historical_score(self) -> int:
        """Score from previous sessions (loaded from disk)."""
        return sum(v.get("points", 0) for v in self._history_violations)

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
    def erosion_signals(self) -> list:
        """Get current erosion signals (if erosion detection enabled)."""
        if not self._erosion_detector:
            return []
        current_dicts = [v.to_dict() for v in self._violations]
        all_violations = self._history_violations + current_dicts
        return self._erosion_detector.analyze(all_violations)

    @property
    def summary(self) -> dict:
        """Summary for heartbeat/dashboard."""
        with self._lock:
            window_violations = [
                v for v in self._violations
                if v.timestamp > time.time() - self.window_seconds
            ]
        result = {
            "score": self.score,
            "total_score": self.total_score,
            "threat_level": self.threat_level,
            "kill_threshold": self.kill_threshold,
            "violations_in_window": len(window_violations),
            "total_violations": len(self._violations),
            "auto_kill": self.auto_kill,
        }

        # v0.4 additions
        if self._store:
            result["historical_violations"] = len(self._history_violations)
            result["historical_score"] = self.historical_score
            result["persist"] = True

        if self._erosion_detector:
            signals = self.erosion_signals
            result["erosion_signals"] = len(signals)
            result["erosion_patterns"] = [
                {"pattern": s.pattern, "confidence": s.confidence}
                for s in signals if s.confidence > 0.3
            ]

        return result

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
