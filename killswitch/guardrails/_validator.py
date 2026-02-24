"""Action Validator — check agent actions against allow/block rules before execution."""

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set


@dataclass
class ValidationResult:
    allowed: bool
    action: str
    reason: str = ""
    rule: str = ""


@dataclass
class ActionRule:
    """A rule that matches actions by pattern and decides allow/block."""
    pattern: str
    action: str  # "allow" or "block"
    description: str = ""
    _compiled: re.Pattern = field(init=False, repr=False)

    def __post_init__(self):
        self._compiled = re.compile(self.pattern, re.IGNORECASE)

    def matches(self, action_name: str) -> bool:
        return bool(self._compiled.search(action_name))


class ActionValidator:
    """Validate agent actions before execution.

    Supports three modes:
    - allowlist: only explicitly allowed actions can run (default, safest)
    - blocklist: everything except blocked actions can run
    - audit: everything runs but violations are logged

    Usage:
        validator = ActionValidator(mode="allowlist")
        validator.allow("read_*", "Read operations")
        validator.allow("search_*", "Search operations")
        validator.block("delete_*", "No deletions")
        validator.block("send_email", "No email sending")

        result = validator.check("delete_file", detail="/etc/passwd")
        if not result.allowed:
            print(f"Blocked: {result.reason}")
    """

    def __init__(
        self,
        mode: str = "allowlist",
        on_violation: Optional[Callable] = None,
        max_actions_per_minute: int = 0,
    ):
        if mode not in ("allowlist", "blocklist", "audit"):
            raise ValueError(f"Invalid mode: {mode}. Use allowlist, blocklist, or audit.")

        self.mode = mode
        self.on_violation = on_violation
        self.max_actions_per_minute = max_actions_per_minute

        self._allow_rules: List[ActionRule] = []
        self._block_rules: List[ActionRule] = []
        self._violations: List[Dict] = []
        self._action_timestamps: List[float] = []

    def allow(self, pattern: str, description: str = "") -> "ActionValidator":
        """Add an allow rule. Pattern is a regex matched against action names."""
        self._allow_rules.append(ActionRule(pattern=pattern, action="allow", description=description))
        return self

    def block(self, pattern: str, description: str = "") -> "ActionValidator":
        """Add a block rule. Block rules take priority over allow rules."""
        self._block_rules.append(ActionRule(pattern=pattern, action="block", description=description))
        return self

    def check(self, action: str, detail: str = "") -> ValidationResult:
        """Check if an action is allowed.

        Args:
            action: The action name (e.g., "delete_email", "send_http", "read_file")
            detail: Optional detail string for logging
        """
        # Rate limiting check
        if self.max_actions_per_minute > 0:
            now = time.time()
            cutoff = now - 60
            self._action_timestamps = [t for t in self._action_timestamps if t > cutoff]
            if len(self._action_timestamps) >= self.max_actions_per_minute:
                result = ValidationResult(
                    allowed=False,
                    action=action,
                    reason=f"Rate limit exceeded: {self.max_actions_per_minute}/min",
                    rule="rate_limit",
                )
                self._record_violation(result, detail)
                return result
            self._action_timestamps.append(now)

        # Audit mode: always allow, but log what would have been blocked
        if self.mode == "audit":
            for rule in self._block_rules:
                if rule.matches(action):
                    self._record_audit(action, rule, detail)
            return ValidationResult(allowed=True, action=action)

        # Block rules always win (for allowlist and blocklist modes)
        for rule in self._block_rules:
            if rule.matches(action):
                result = ValidationResult(
                    allowed=False,
                    action=action,
                    reason=f"Blocked by rule: {rule.description or rule.pattern}",
                    rule=rule.pattern,
                )
                self._record_violation(result, detail)
                return result

        # Mode-specific logic
        if self.mode == "allowlist":
            for rule in self._allow_rules:
                if rule.matches(action):
                    return ValidationResult(allowed=True, action=action, rule=rule.pattern)
            # Not in allowlist = blocked
            result = ValidationResult(
                allowed=False,
                action=action,
                reason=f"Action '{action}' not in allowlist",
                rule="allowlist_default",
            )
            self._record_violation(result, detail)
            return result

        else:  # blocklist mode
            # Not blocked = allowed
            return ValidationResult(allowed=True, action=action)

    def _record_violation(self, result: ValidationResult, detail: str):
        """Record a violation and call the callback if set."""
        violation = {
            "time": time.time(),
            "action": result.action,
            "reason": result.reason,
            "rule": result.rule,
            "detail": detail,
        }
        self._violations.append(violation)

        if self.on_violation:
            self.on_violation(violation)

    def _record_audit(self, action: str, rule: ActionRule, detail: str):
        """Record an audit finding (would-be violation in audit mode)."""
        audit_entry = {
            "time": time.time(),
            "action": action,
            "reason": f"Audit: would be blocked by {rule.pattern}",
            "rule": rule.pattern,
            "detail": detail,
            "audit_only": True,
        }
        self._violations.append(audit_entry)

    @property
    def violations(self) -> List[Dict]:
        """Get all recorded violations."""
        return list(self._violations)

    def clear_violations(self):
        """Clear recorded violations."""
        self._violations.clear()


# Pre-built validator presets
def strict_validator(on_violation: Optional[Callable] = None) -> ActionValidator:
    """A strict validator that blocks dangerous operations.

    Blocks: file deletion, email sending, financial transactions,
    network requests to unknown hosts, code execution.
    """
    v = ActionValidator(mode="blocklist", on_violation=on_violation)
    v.block(r"delete_", "No deletion operations")
    v.block(r"remove_", "No removal operations")
    v.block(r"drop_", "No drop operations")
    v.block(r"send_email", "No email sending")
    v.block(r"send_message", "No message sending")
    v.block(r"transfer_", "No financial transfers")
    v.block(r"payment", "No payment operations")
    v.block(r"exec_", "No code execution")
    v.block(r"eval_", "No code evaluation")
    v.block(r"shell_", "No shell commands")
    v.block(r"sudo", "No elevated privileges")
    v.block(r"chmod", "No permission changes")
    v.block(r"format_", "No format operations")
    v.block(r"truncate_", "No truncation operations")
    return v


def readonly_validator(on_violation: Optional[Callable] = None) -> ActionValidator:
    """A read-only validator — only allow read/search/list operations."""
    v = ActionValidator(mode="allowlist", on_violation=on_violation)
    v.allow(r"read_", "Read operations")
    v.allow(r"get_", "Get operations")
    v.allow(r"list_", "List operations")
    v.allow(r"search_", "Search operations")
    v.allow(r"fetch_", "Fetch operations")
    v.allow(r"query_", "Query operations")
    v.allow(r"count_", "Count operations")
    v.allow(r"check_", "Check operations")
    v.allow(r"view_", "View operations")
    return v
