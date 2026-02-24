"""Kill execution with SIGTERM → SIGKILL escalation."""

import os
import signal
import sys
import threading
import time


def kill_self(graceful_timeout: float = 3.0) -> None:
    """Kill the current process. SIGTERM first, SIGKILL after timeout.

    Args:
        graceful_timeout: Seconds to wait after SIGTERM before SIGKILL.
    """
    pid = os.getpid()

    def _force_kill():
        time.sleep(graceful_timeout)
        os.kill(pid, signal.SIGKILL)

    # Start SIGKILL timer in daemon thread (dies if main exits cleanly)
    escalation = threading.Thread(target=_force_kill, daemon=True)
    escalation.start()

    # Try graceful shutdown first
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    # If SIGTERM didn't exit, wait for SIGKILL
    time.sleep(graceful_timeout + 1)
    # Shouldn't reach here, but just in case
    sys.exit(1)


def check_local_kill_signal(agent_id: str) -> bool:
    """Check if a local kill signal file exists."""
    kill_file = f"/tmp/killswitch_kill_{agent_id}"
    if os.path.exists(kill_file):
        try:
            os.remove(kill_file)
        except OSError:
            pass
        return True
    return False
