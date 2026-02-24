"""System metrics collection using only stdlib."""

import os
import platform
import time


def get_cpu_percent() -> float:
    """Get CPU usage percentage (approximate, stdlib only)."""
    if platform.system() == "Darwin":
        try:
            with os.popen("ps -o %cpu -p " + str(os.getpid())) as f:
                lines = f.read().strip().split("\n")
            if len(lines) >= 2:
                return float(lines[1].strip())
        except (ValueError, IndexError, OSError):
            pass
    elif platform.system() == "Linux":
        try:
            with open(f"/proc/{os.getpid()}/stat") as f:
                parts = f.read().split()
            utime = int(parts[13])
            stime = int(parts[14])
            total = utime + stime
            hz = os.sysconf("SC_CLK_TCK")
            with open("/proc/uptime") as f:
                uptime = float(f.read().split()[0])
            return (total / hz / uptime) * 100
        except (OSError, ValueError, IndexError):
            pass
    return 0.0


def get_memory_mb() -> float:
    """Get memory usage in MB."""
    if platform.system() == "Darwin":
        try:
            with os.popen("ps -o rss -p " + str(os.getpid())) as f:
                lines = f.read().strip().split("\n")
            if len(lines) >= 2:
                return int(lines[1].strip()) / 1024
        except (ValueError, IndexError, OSError):
            pass
    elif platform.system() == "Linux":
        try:
            with open(f"/proc/{os.getpid()}/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) / 1024
        except (OSError, ValueError):
            pass
    return 0.0


def collect_metrics() -> dict:
    """Collect all system metrics."""
    return {
        "cpu_percent": round(get_cpu_percent(), 1),
        "memory_mb": round(get_memory_mb(), 1),
        "pid": os.getpid(),
        "platform": platform.system(),
        "timestamp": time.time(),
    }
