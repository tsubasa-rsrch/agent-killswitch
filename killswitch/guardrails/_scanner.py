"""Credential and secret scanner — detect hardcoded secrets before they leak."""

import os
import re
from dataclasses import dataclass
from typing import List, Optional

# Severity levels
CRITICAL = "CRITICAL"
HIGH = "HIGH"
MEDIUM = "MEDIUM"
LOW = "LOW"


@dataclass
class Finding:
    severity: str
    category: str  # SECRET or VULN
    file: str
    line: int
    message: str
    snippet: str = ""


# Secret patterns: (compiled_regex, severity, message)
SECRET_PATTERNS = [
    # API keys — common formats
    (re.compile(r"""(?:api[_-]?key|apikey)\s*[=:]\s*['"]([a-zA-Z0-9_\-]{8,})['"]""", re.I),
     CRITICAL, "Hardcoded API key"),
    # Stripe keys
    (re.compile(r"""(?:sk|pk)_(?:live|test)_[a-zA-Z0-9]{20,}"""),
     CRITICAL, "Stripe API key"),
    # OpenAI keys
    (re.compile(r"""sk-[a-zA-Z0-9]{32,}"""),
     CRITICAL, "OpenAI/generic sk- key"),
    # Slack tokens
    (re.compile(r"""xox[bprs]-[a-zA-Z0-9\-]{10,}"""),
     CRITICAL, "Slack token"),
    # GitHub PAT
    (re.compile(r"""ghp_[a-zA-Z0-9]{36}"""),
     CRITICAL, "GitHub personal access token"),
    # AWS credentials
    (re.compile(r"""(?:aws_access_key_id|aws_secret_access_key)\s*[=:]\s*['"]([A-Z0-9/+=]{16,})['"]""", re.I),
     CRITICAL, "AWS credential"),
    # Generic password/secret assignment
    (re.compile(r"""(?:password|passwd|pwd|secret|token)\s*[=:]\s*['"]([^'"]{8,})['"]""", re.I),
     HIGH, "Hardcoded password/secret"),
    # RTSP URLs with auth (cameras, IoT)
    (re.compile(r"""rtsp://[^:]+:[^@]+@[\d.]+""", re.I),
     CRITICAL, "RTSP URL with embedded credentials"),
    # Private IP addresses (info leak)
    (re.compile(r"""(?:^|[^.\d])(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})(?:[^.\d]|$)"""),
     MEDIUM, "Hardcoded private IP address"),
    # Bearer tokens in code
    (re.compile(r"""['"]Bearer\s+[a-zA-Z0-9._\-]{20,}['"]"""),
     HIGH, "Hardcoded Bearer token"),
    # Connection strings
    (re.compile(r"""(?:mongodb|postgresql|mysql|redis)://[^:]+:[^@]+@""", re.I),
     CRITICAL, "Database connection string with credentials"),
]

# Code vulnerability patterns
VULN_PATTERNS = [
    (re.compile(r"""\beval\s*\("""), HIGH, "eval() — code injection risk"),
    (re.compile(r"""\bexec\s*\("""), HIGH, "exec() — code injection risk"),
    (re.compile(r"""\bos\.system\s*\("""), HIGH, "os.system() — shell injection risk"),
    (re.compile(r"""subprocess.*shell\s*=\s*True"""), HIGH, "subprocess with shell=True"),
    (re.compile(r"""\bpickle\.loads?\s*\("""), MEDIUM, "pickle deserialization risk"),
    (re.compile(r"""\b__import__\s*\("""), MEDIUM, "Dynamic import"),
    (re.compile(r"""chmod\s+777"""), MEDIUM, "World-writable permissions"),
]

# Safe context patterns — suppress false positives
SAFE_CONTEXTS = [
    re.compile(r"""os\.(?:getenv|environ)""", re.I),
    re.compile(r"""load_dotenv""", re.I),
    re.compile(r"""\.env\.example""", re.I),
    re.compile(r"""(?:example|sample|placeholder|template|dummy|fake|test)""", re.I),
    re.compile(r"""your[_-].*[_-](?:key|token|secret|password)""", re.I),
    re.compile(r"""(?:xxx+|placeholder|changeme|REPLACE_ME)""", re.I),
]

# File extensions to scan
SCAN_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".rb", ".php", ".sh", ".bash", ".zsh", ".yaml", ".yml",
    ".json", ".toml", ".ini", ".cfg", ".conf", ".env",
}

# Directories to skip
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".svelte-kit", "build",
    "dist", ".next", ".venv", "venv", "env", ".tox", ".eggs",
}


def _is_safe_context(line: str) -> bool:
    """Check if a line is a false positive (uses env vars, is a test, etc.)."""
    return any(p.search(line) for p in SAFE_CONTEXTS)


def scan_file(filepath: str) -> List[Finding]:
    """Scan a single file for secrets and vulnerabilities."""
    findings: List[Finding] = []

    ext = os.path.splitext(filepath)[1].lower()
    if ext not in SCAN_EXTENSIONS:
        return findings

    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except (OSError, PermissionError):
        return findings

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Skip comments and blank lines
        if not stripped or stripped.startswith("#") and not any(
            p[0].search(stripped) for p in SECRET_PATTERNS
        ):
            continue

        if _is_safe_context(stripped):
            continue

        # Check secret patterns
        for pattern, severity, message in SECRET_PATTERNS:
            if pattern.search(stripped):
                findings.append(Finding(
                    severity=severity,
                    category="SECRET",
                    file=filepath,
                    line=i,
                    message=message,
                    snippet=stripped[:120],
                ))

        # Check vulnerability patterns
        for pattern, severity, message in VULN_PATTERNS:
            if pattern.search(stripped):
                findings.append(Finding(
                    severity=severity,
                    category="VULN",
                    file=filepath,
                    line=i,
                    message=message,
                    snippet=stripped[:120],
                ))

    return findings


def scan_directory(
    path: str,
    exclude_dirs: Optional[set] = None,
    severity_threshold: str = LOW,
) -> List[Finding]:
    """Recursively scan a directory for secrets and vulnerabilities.

    Args:
        path: Directory to scan
        exclude_dirs: Additional directories to skip
        severity_threshold: Minimum severity to report (CRITICAL, HIGH, MEDIUM, LOW)
    """
    skip = SKIP_DIRS | (exclude_dirs or set())
    severity_order = {CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1}
    min_severity = severity_order.get(severity_threshold, 1)

    all_findings: List[Finding] = []

    for root, dirs, files in os.walk(path):
        # Prune skipped directories
        dirs[:] = [d for d in dirs if d not in skip]

        for fname in files:
            filepath = os.path.join(root, fname)
            findings = scan_file(filepath)
            all_findings.extend(
                f for f in findings
                if severity_order.get(f.severity, 0) >= min_severity
            )

    # Sort by severity (CRITICAL first)
    all_findings.sort(key=lambda f: -severity_order.get(f.severity, 0))
    return all_findings
