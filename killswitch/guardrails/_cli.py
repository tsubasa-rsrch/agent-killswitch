"""CLI for guardrails — scan code and install git hooks."""

import os
import stat
import sys


def main():
    """Entry point for `killswitch-scan` CLI command."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="killswitch-scan",
        description="Scan code for hardcoded secrets and vulnerabilities",
    )
    parser.add_argument("path", nargs="?", default=".", help="Directory or file to scan")
    parser.add_argument("--severity", default="LOW", choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                        help="Minimum severity to report (default: LOW)")
    parser.add_argument("--pre-commit", action="store_true",
                        help="Only report CRITICAL findings (for git hooks)")
    parser.add_argument("--install-hook", action="store_true",
                        help="Install as a git pre-commit hook in the current repo")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Show code snippets")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Only output if findings exist")
    args = parser.parse_args()

    if args.install_hook:
        _install_hook()
        return

    from killswitch.guardrails._scanner import scan_file, scan_directory, CRITICAL, HIGH, MEDIUM, LOW

    severity = CRITICAL if args.pre_commit else args.severity
    severity_order = {CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1}
    min_severity = severity_order.get(severity, 1)

    if os.path.isfile(args.path):
        findings = scan_file(args.path)
        findings = [f for f in findings if severity_order.get(f.severity, 0) >= min_severity]
    else:
        findings = scan_directory(args.path, severity_threshold=severity)

    if args.pre_commit:
        findings = [f for f in findings if f.severity == CRITICAL]

    if not findings:
        if not args.quiet:
            print("No findings.")
        sys.exit(0)

    # Group by severity
    by_severity = {}
    for f in findings:
        by_severity.setdefault(f.severity, []).append(f)

    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        group = by_severity.get(sev, [])
        if not group:
            continue
        print(f"\n{'='*60}")
        print(f" {sev} ({len(group)} findings)")
        print(f"{'='*60}")
        for f in group:
            print(f"  {f.file}:{f.line}")
            print(f"    [{f.category}] {f.message}")
            if args.verbose and f.snippet:
                print(f"    > {f.snippet}")

    print(f"\nTotal: {len(findings)} findings")

    # Exit with error if CRITICAL findings exist
    if any(f.severity == CRITICAL for f in findings):
        print("\nCRITICAL findings detected — commit blocked." if args.pre_commit else "")
        sys.exit(1)


def _install_hook():
    """Install killswitch-scan as a git pre-commit hook."""
    git_dir = _find_git_dir()
    if not git_dir:
        print("Error: Not in a git repository.", file=sys.stderr)
        sys.exit(1)

    hooks_dir = os.path.join(git_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)

    hook_path = os.path.join(hooks_dir, "pre-commit")

    hook_content = """#!/bin/sh
# Agent Killswitch — credential scanner pre-commit hook
# Blocks commits with CRITICAL secrets (hardcoded API keys, passwords, etc.)

if command -v killswitch-scan > /dev/null 2>&1; then
    killswitch-scan . --pre-commit
    if [ $? -ne 0 ]; then
        echo ""
        echo "Commit blocked by killswitch-scan."
        echo "Fix CRITICAL findings above or use --no-verify to skip."
        exit 1
    fi
elif python3 -c "from killswitch.guardrails._cli import main" 2>/dev/null; then
    python3 -m killswitch.guardrails._cli . --pre-commit
    if [ $? -ne 0 ]; then
        echo ""
        echo "Commit blocked by killswitch-scan."
        exit 1
    fi
fi
"""

    if os.path.exists(hook_path):
        with open(hook_path, "r") as f:
            existing = f.read()
        if "killswitch-scan" in existing:
            print(f"Hook already installed at {hook_path}")
            return
        # Append to existing hook
        with open(hook_path, "a") as f:
            f.write("\n" + hook_content)
        print(f"Appended killswitch-scan to existing hook at {hook_path}")
    else:
        with open(hook_path, "w") as f:
            f.write(hook_content)
        print(f"Installed pre-commit hook at {hook_path}")

    # Make executable
    st = os.stat(hook_path)
    os.chmod(hook_path, st.st_mode | stat.S_IEXEC)


def _find_git_dir():
    """Walk up to find .git directory."""
    path = os.getcwd()
    while path != "/":
        git_path = os.path.join(path, ".git")
        if os.path.isdir(git_path):
            return git_path
        path = os.path.dirname(path)
    return None


if __name__ == "__main__":
    main()
