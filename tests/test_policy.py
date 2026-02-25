"""Tests for PolicyEngine — violation scoring, threat levels, auto-kill."""

import time
import pytest
from killswitch._policy import PolicyEngine, Violation, SEVERITY_POINTS


class TestViolation:
    def test_default_points_from_severity(self):
        v = Violation(severity="critical", action="test", reason="test")
        assert v.points == 100

    def test_custom_points_override(self):
        v = Violation(severity="critical", action="test", reason="test", points=50)
        assert v.points == 50

    def test_all_severity_levels(self):
        for sev, pts in SEVERITY_POINTS.items():
            v = Violation(severity=sev, action="test", reason="test")
            assert v.points == pts

    def test_to_dict(self):
        v = Violation(severity="high", action="delete_email", reason="blocked", detail="inbox")
        d = v.to_dict()
        assert d["severity"] == "high"
        assert d["action"] == "delete_email"
        assert d["points"] == 25
        assert "t" in d


class TestPolicyEngine:
    def test_initial_state(self):
        pe = PolicyEngine()
        assert pe.score == 0
        assert pe.threat_level == "green"
        assert pe.total_score == 0

    def test_report_increases_score(self):
        pe = PolicyEngine()
        pe.report("medium", "test_action", "test reason")
        assert pe.score == 5
        assert pe.threat_level == "yellow"

    def test_threat_level_escalation(self):
        pe = PolicyEngine(kill_threshold=100, alert_threshold=25)
        assert pe.threat_level == "green"

        pe.report("low", "a1", "r1")  # 1 pt
        assert pe.threat_level == "yellow"

        # Push to alert threshold
        for _ in range(5):
            pe.report("medium", "a2", "r2")  # 5 pts each = 25 total
        assert pe.score == 26
        assert pe.threat_level == "orange"

    def test_auto_kill_triggered(self):
        killed = {"called": False, "reason": ""}

        def on_kill(v, score):
            killed["called"] = True

        pe = PolicyEngine(kill_threshold=100, on_kill=on_kill, auto_kill=True)
        pe.report("critical", "exfil", "data exfiltration")  # 100 pts
        assert pe._killed
        assert killed["called"]
        assert pe.threat_level == "red"

    def test_auto_kill_disabled(self):
        pe = PolicyEngine(kill_threshold=0, auto_kill=False)
        pe.report("critical", "exfil", "test")
        assert not pe._killed

    def test_alert_callback(self):
        alerts = []

        def on_alert(v, score, level):
            alerts.append({"score": score, "level": level})

        pe = PolicyEngine(alert_threshold=10, kill_threshold=200, on_alert=on_alert)
        pe.report("high", "test", "test")  # 25 pts > 10 threshold
        assert len(alerts) == 1
        assert alerts[0]["level"] == "orange"

    def test_sliding_window(self):
        pe = PolicyEngine(window_seconds=1)
        pe.report("medium", "old", "old action")
        assert pe.score == 5

        # Wait for window to expire
        time.sleep(1.1)
        assert pe.score == 0
        assert pe.total_score == 5  # Total never expires

    def test_unknown_severity_defaults_to_medium(self):
        pe = PolicyEngine()
        v = pe.report("bogus", "test", "test")
        assert v.severity == "medium"
        assert v.points == 5

    def test_recent_violations(self):
        pe = PolicyEngine()
        for i in range(10):
            pe.report("low", f"action_{i}", "reason")
        recent = pe.recent_violations(3)
        assert len(recent) == 3
        assert recent[-1]["action"] == "action_9"

    def test_summary(self):
        pe = PolicyEngine(kill_threshold=100, alert_threshold=25)
        pe.report("medium", "test", "test")
        s = pe.summary
        assert s["score"] == 5
        assert s["threat_level"] == "yellow"
        assert s["kill_threshold"] == 100
        assert s["total_violations"] == 1

    def test_validator_callback(self):
        pe = PolicyEngine()
        cb = pe.make_validator_callback()
        cb({"action": "delete_email", "reason": "blocked", "detail": "", "rule": "delete_*"})
        assert pe.score == 5  # medium severity for blocked actions

    def test_validator_rate_limit_callback(self):
        pe = PolicyEngine()
        cb = pe.make_validator_callback()
        cb({"action": "fast_action", "reason": "too fast", "detail": "", "rule": "rate_limit"})
        assert pe.score == 1  # low severity for rate limits

    def test_egress_callback_blacklisted(self):
        pe = PolicyEngine()
        cb = pe.make_egress_callback()
        cb({"url": "https://evil.com/steal", "domain": "evil.com", "reason": "blacklisted domain"})
        assert pe.score == 100  # critical for blacklisted

    def test_egress_callback_other(self):
        pe = PolicyEngine()
        cb = pe.make_egress_callback()
        cb({"url": "https://unknown.com", "domain": "unknown.com", "reason": "not whitelisted"})
        assert pe.score == 25  # high for other egress blocks

    def test_attach_killswitch(self):
        kill_reasons = []

        class MockKillswitch:
            def _execute_kill(self, reason):
                kill_reasons.append(reason)

        pe = PolicyEngine(kill_threshold=50)
        ks = MockKillswitch()
        pe.attach(ks)
        pe.report("critical", "exfil", "test")  # 100 > 50
        assert len(kill_reasons) == 1
        assert "auto-kill" in kill_reasons[0]


class TestGuardIntegration:
    def test_guard_creates_policy(self):
        from killswitch import guard
        ks = guard(
            name="test-agent",
            block=["delete_*"],
            allow_domains=["api.openai.com"],
            auto_kill_threshold=100,
            alert_threshold=25,
        )
        assert ks.policy is not None
        assert ks.policy.kill_threshold == 100
        assert ks.policy.alert_threshold == 25
        assert ks.validator is not None
        assert ks.egress is not None
        ks.stop()

    def test_guard_validator_feeds_policy(self):
        from killswitch import guard
        ks = guard(
            name="test-feed",
            block=["delete_*"],
            auto_kill_threshold=1000,
        )
        ks.validator.check("delete_email", detail="test")
        assert ks.policy.score == 5  # medium severity from blocked action
        ks.stop()

    def test_guard_egress_feeds_policy(self):
        from killswitch import guard
        ks = guard(
            name="test-egress",
            allow_domains=["api.openai.com"],
            block_domains=["evil.com"],
            auto_kill_threshold=1000,
        )
        ks.egress.check("https://evil.com/steal")
        assert ks.policy.score >= 25  # high or critical
        ks.stop()

    def test_guard_no_auto_kill_when_zero(self):
        from killswitch import guard
        ks = guard(
            name="test-no-kill",
            block=["delete_*"],
            auto_kill_threshold=0,
        )
        assert not ks.policy.auto_kill
        ks.stop()
