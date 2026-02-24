"""Agent Guardrails — prevent credential leaks, unauthorized actions, and data exfiltration."""

from killswitch.guardrails._scanner import scan_file, scan_directory, Finding
from killswitch.guardrails._validator import ActionValidator
from killswitch.guardrails._egress import EgressFilter

__all__ = [
    "scan_file",
    "scan_directory",
    "Finding",
    "ActionValidator",
    "EgressFilter",
]
