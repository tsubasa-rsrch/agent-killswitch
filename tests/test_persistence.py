"""Tests for v0.4: persistence and erosion detection."""

import json
import os
import tempfile
import time

import pytest

from killswitch._persistence import ViolationStore
from killswitch._erosion import ErosionDetector, ErosionSignal
from killswitch._policy import PolicyEngine


# ─── ViolationStore ───

class TestViolationStore:
    def test_append_and_load(self, tmp_path):
        store = ViolationStore("test-agent", storage_dir=str(tmp_path))
        v = {"severity": "high", "action": "delete_email", "reason": "test", "t": time.time(), "points": 25}
        store.append(v)

        loaded = store.load()
        assert len(loaded) == 1
        assert loaded[0]["action"] == "delete_email"

    def test_load_empty(self, tmp_path):
        store = ViolationStore("nonexistent", storage_dir=str(tmp_path))
        assert store.load() == []

    def test_load_filters_old(self, tmp_path):
        store = ViolationStore("test-agent", storage_dir=str(tmp_path))
        old_v = {"severity": "low", "action": "old", "reason": "old", "t": time.time() - 999999, "points": 1}
        new_v = {"severity": "high", "action": "new", "reason": "new", "t": time.time(), "points": 25}
        store.append(old_v)
        store.append(new_v)

        loaded = store.load(max_age_hours=1)
        assert len(loaded) == 1
        assert loaded[0]["action"] == "new"

    def test_cleanup(self, tmp_path):
        store = ViolationStore("test-agent", storage_dir=str(tmp_path))
        old_v = {"severity": "low", "action": "old", "t": time.time() - 999999, "points": 1}
        new_v = {"severity": "high", "action": "new", "t": time.time(), "points": 25}
        store.append(old_v)
        store.append(new_v)

        removed = store.cleanup(max_age_hours=1)
        assert removed == 1

        # Verify file only has new violation
        loaded = store.load(max_age_hours=99999)
        assert len(loaded) == 1
        assert loaded[0]["action"] == "new"

    def test_append_creates_directory(self, tmp_path):
        deep_dir = str(tmp_path / "a" / "b" / "c")
        store = ViolationStore("test-agent", storage_dir=deep_dir)
        v = {"severity": "low", "action": "test", "t": time.time(), "points": 1}
        store.append(v)
        assert store.exists

    def test_jsonl_format(self, tmp_path):
        store = ViolationStore("test-agent", storage_dir=str(tmp_path))
        for i in range(3):
            store.append({"severity": "low", "action": f"act_{i}", "t": time.time(), "points": 1})

        with open(store.path) as f:
            lines = f.readlines()
        assert len(lines) == 3
        for line in lines:
            json.loads(line)  # Should not raise


# ─── ErosionDetector ───

class TestErosionDetector:
    def test_no_violations(self):
        detector = ErosionDetector()
        assert detector.analyze([]) == []

    def test_detect_repeat(self):
        detector = ErosionDetector(repeat_threshold=3)
        violations = [
            {"severity": "medium", "action": "delete_email", "t": time.time(), "points": 5},
            {"severity": "medium", "action": "delete_file", "t": time.time(), "points": 5},
            {"severity": "medium", "action": "delete_msg", "t": time.time(), "points": 5},
        ]
        signals = detector.analyze(violations)
        repeat_signals = [s for s in signals if s.pattern == "repeat"]
        assert len(repeat_signals) == 1
        assert repeat_signals[0].action == "delete"
        assert repeat_signals[0].confidence > 0

    def test_no_repeat_below_threshold(self):
        detector = ErosionDetector(repeat_threshold=5)
        violations = [
            {"severity": "medium", "action": "delete_email", "t": time.time(), "points": 5},
            {"severity": "medium", "action": "delete_file", "t": time.time(), "points": 5},
        ]
        signals = detector.analyze(violations)
        repeat_signals = [s for s in signals if s.pattern == "repeat"]
        assert len(repeat_signals) == 0

    def test_detect_tactic_switch(self):
        detector = ErosionDetector(tactic_switch_threshold=3)
        violations = [
            {"severity": "medium", "action": "delete_email", "t": time.time(), "points": 5},
            {"severity": "high", "action": "egress:evil.com", "t": time.time(), "points": 25},
            {"severity": "medium", "action": "send_spam", "t": time.time(), "points": 5},
        ]
        signals = detector.analyze(violations)
        tactic_signals = [s for s in signals if s.pattern == "tactic_switch"]
        assert len(tactic_signals) == 1

    def test_detect_escalation(self):
        now = time.time()
        detector = ErosionDetector(escalation_window=600)
        violations = [
            {"severity": "low", "action": "probe", "t": now - 100, "points": 1},
            {"severity": "low", "action": "probe", "t": now - 80, "points": 1},
            {"severity": "medium", "action": "attempt", "t": now - 60, "points": 5},
            {"severity": "high", "action": "attack", "t": now - 40, "points": 25},
            {"severity": "high", "action": "attack2", "t": now - 20, "points": 25},
            {"severity": "critical", "action": "exfil", "t": now, "points": 100},
        ]
        signals = detector.analyze(violations)
        esc_signals = [s for s in signals if s.pattern == "escalation"]
        assert len(esc_signals) == 1
        assert esc_signals[0].confidence > 0.2


# ─── PolicyEngine v0.4 integration ───

class TestPolicyEngineV04:
    def test_persist_mode(self, tmp_path):
        policy = PolicyEngine(
            persist=True,
            agent_name="test-agent",
            kill_threshold=1000,
            auto_kill=False,
        )
        # Override storage dir for test
        from killswitch._persistence import ViolationStore
        policy._store = ViolationStore("test-agent", storage_dir=str(tmp_path))

        policy.report("medium", "delete_email", "test deletion")
        policy.report("high", "delete_file", "test deletion 2")

        # Verify persisted
        loaded = policy._store.load()
        assert len(loaded) == 2

    def test_erosion_detection_enabled(self, tmp_path):
        erosion_signals = []

        def on_erosion(signal):
            erosion_signals.append(signal)

        policy = PolicyEngine(
            persist=True,
            agent_name="test-agent",
            erosion_detection=True,
            on_erosion=on_erosion,
            kill_threshold=1000,
            auto_kill=False,
        )
        policy._store = ViolationStore("test-agent", storage_dir=str(tmp_path))

        # Report enough violations to trigger repeat detection
        for i in range(5):
            policy.report("medium", f"delete_{i}", f"attempt {i}")

        assert len(erosion_signals) > 0
        assert any(s.pattern == "repeat" for s in erosion_signals)

    def test_historical_score(self, tmp_path):
        # Create store with pre-existing violations
        store = ViolationStore("test-agent", storage_dir=str(tmp_path))
        for i in range(3):
            store.append({"severity": "high", "action": f"old_{i}", "t": time.time() - 3600, "points": 25})

        policy = PolicyEngine(
            persist=True,
            agent_name="test-agent",
            kill_threshold=1000,
            auto_kill=False,
        )
        policy._store = store
        policy._history_violations = store.load()

        assert policy.historical_score == 75

    def test_summary_includes_v04_fields(self, tmp_path):
        store = ViolationStore("test-agent", storage_dir=str(tmp_path))
        policy = PolicyEngine(
            persist=True,
            agent_name="test-agent",
            erosion_detection=True,
            kill_threshold=1000,
            auto_kill=False,
        )
        policy._store = store
        policy._history_violations = []

        summary = policy.summary
        assert "historical_violations" in summary
        assert "historical_score" in summary
        assert "persist" in summary
        assert "erosion_signals" in summary
        assert "erosion_patterns" in summary

    def test_erosion_bonus_points_increase_score(self, tmp_path):
        """Erosion detection should add bonus points, making auto-kill more likely."""
        policy = PolicyEngine(
            persist=True,
            agent_name="test-agent",
            erosion_detection=True,
            kill_threshold=200,
            auto_kill=False,
        )
        policy._store = ViolationStore("test-agent", storage_dir=str(tmp_path))

        # Report 5 delete actions (5 * 5 = 25 base points)
        for i in range(5):
            policy.report("medium", f"delete_{i}", f"attempt {i}")

        # Score should be > 25 due to erosion bonus points
        assert policy.total_score > 25

    def test_backward_compatible_no_persist(self):
        """v0.3 mode: no persist, no erosion — should work identically."""
        policy = PolicyEngine(kill_threshold=100, auto_kill=False)
        policy.report("medium", "test", "test")
        assert policy.score == 5
        assert "persist" not in policy.summary


# ─── Existing v0.3 tests still pass ───

class TestPolicyEngineV03Compat:
    def test_basic_scoring(self):
        policy = PolicyEngine(kill_threshold=100, auto_kill=False)
        policy.report("low", "action", "reason")
        assert policy.score == 1

    def test_threat_levels(self):
        policy = PolicyEngine(kill_threshold=100, alert_threshold=25, auto_kill=False)
        assert policy.threat_level == "green"
        policy.report("high", "action", "reason")
        assert policy.threat_level == "orange"

    def test_critical_instant_kill_score(self):
        policy = PolicyEngine(kill_threshold=100, auto_kill=False)
        policy.report("critical", "exfil", "data theft")
        assert policy.score >= 100

    def test_recent_violations(self):
        policy = PolicyEngine(kill_threshold=1000, auto_kill=False)
        for i in range(10):
            policy.report("low", f"action_{i}", "reason")
        recent = policy.recent_violations(3)
        assert len(recent) == 3
