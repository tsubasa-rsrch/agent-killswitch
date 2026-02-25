"""Persistent violation storage — violations survive agent restarts.

The Mexican Government Hack (Feb 2026) used 1000+ prompts across sessions.
Claude initially refused, then complied after tactic switching.
Without persistent violation history, each restart is a clean slate for attackers.

This ensures violation history carries forward across agent restarts.
"""

import json
import os
import time
from pathlib import Path
from typing import List, Optional


# Default storage directory
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), ".killswitch", "violations")


class ViolationStore:
    """Append-only JSONL file for violation persistence.

    Usage:
        store = ViolationStore("my-agent")
        store.append(violation_dict)

        # Load history from previous sessions
        history = store.load(max_age_hours=168)  # Last 7 days
    """

    def __init__(self, agent_name: str, storage_dir: str = ""):
        self.agent_name = agent_name
        self.storage_dir = storage_dir or DEFAULT_DIR
        self._path = os.path.join(self.storage_dir, f"{agent_name}.jsonl")

        # Ensure directory exists
        os.makedirs(self.storage_dir, exist_ok=True)

    def append(self, violation: dict) -> None:
        """Append a violation record to the JSONL file."""
        line = json.dumps(violation, separators=(",", ":")) + "\n"
        with open(self._path, "a") as f:
            f.write(line)

    def load(self, max_age_hours: int = 168) -> List[dict]:
        """Load violations from disk, filtered by age.

        Args:
            max_age_hours: Only load violations from the last N hours (default: 7 days)

        Returns:
            List of violation dicts, oldest first
        """
        if not os.path.exists(self._path):
            return []

        cutoff = time.time() - (max_age_hours * 3600)
        violations = []

        with open(self._path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    v = json.loads(line)
                    if v.get("t", 0) >= cutoff:
                        violations.append(v)
                except (json.JSONDecodeError, KeyError):
                    continue

        return violations

    def cleanup(self, max_age_hours: int = 168) -> int:
        """Remove violations older than max_age_hours. Returns count removed."""
        if not os.path.exists(self._path):
            return 0

        cutoff = time.time() - (max_age_hours * 3600)
        kept = []
        removed = 0

        with open(self._path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    v = json.loads(line)
                    if v.get("t", 0) >= cutoff:
                        kept.append(line)
                    else:
                        removed += 1
                except (json.JSONDecodeError, KeyError):
                    removed += 1

        # Rewrite file with only kept violations
        with open(self._path, "w") as f:
            for line in kept:
                f.write(line + "\n")

        return removed

    @property
    def path(self) -> str:
        return self._path

    @property
    def exists(self) -> bool:
        return os.path.exists(self._path)
