"""Core monitor: background heartbeat thread + kill signal detection."""

import atexit
import sys
import threading
import time
import uuid
from typing import Optional

from killswitch._action_log import ActionLog
from killswitch._config import load_config
from killswitch._http import post_json
from killswitch._kill import check_local_kill_signal, kill_self
from killswitch._metrics import collect_metrics

_active_instance: Optional["Killswitch"] = None


class Killswitch:
    """Monitor an agent process with heartbeats and remote kill capability.

    Usage:
        ks = Killswitch(name="my-agent")
        ks.start()

        # Log actions your agent takes
        ks.log("sending email", detail="to: user@example.com")

        # Stop monitoring
        ks.stop()
    """

    def __init__(
        self,
        name: str = "unnamed-agent",
        agent_id: Optional[str] = None,
        server_url: Optional[str] = None,
        api_key: Optional[str] = None,
        heartbeat_interval: Optional[int] = None,
        on_kill: Optional[callable] = None,
    ):
        self.name = name
        self.agent_id = agent_id or str(uuid.uuid4())[:8]
        self.actions = ActionLog()
        self.on_kill = on_kill
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._status = "starting"
        self._heartbeat_count = 0

        # Guardrails (attached by guard())
        self.validator = None
        self.egress = None
        self.policy = None

        config = load_config()
        self.server_url = server_url or config.get("server_url", "")
        self.api_key = api_key or config.get("api_key", "")
        self.heartbeat_interval = heartbeat_interval or config.get("heartbeat_interval", 5)
        self.local_mode = not self.server_url

    def start(self) -> "Killswitch":
        """Start the heartbeat thread."""
        if self._running:
            return self

        self._running = True
        self._status = "running"
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()
        atexit.register(self.stop)

        if self.local_mode:
            _print_local_banner(self.name, self.agent_id)
        else:
            self.actions.log("killswitch started", detail=f"server={self.server_url}")

        return self

    def stop(self) -> None:
        """Stop the heartbeat thread."""
        self._running = False
        self._status = "stopped"

    def log(self, action: str, detail: Optional[str] = None) -> None:
        """Log an agent action."""
        self.actions.log(action, detail)

    def _heartbeat_loop(self) -> None:
        """Background loop: send heartbeats, check kill signals."""
        while self._running:
            try:
                self._send_heartbeat()
                self._heartbeat_count += 1
            except Exception:
                pass

            time.sleep(self.heartbeat_interval)

    def _send_heartbeat(self) -> None:
        """Send a single heartbeat."""
        metrics = collect_metrics()
        payload = {
            "agent_id": self.agent_id,
            "name": self.name,
            "status": self._status,
            "heartbeat_num": self._heartbeat_count,
            "metrics": metrics,
            "recent_actions": self.actions.recent(5),
        }

        # Include policy violations if policy engine is attached
        if self.policy:
            payload["policy"] = self.policy.summary
            payload["recent_violations"] = self.policy.recent_violations(5)

        if self.local_mode:
            self._handle_local_heartbeat(payload)
        else:
            self._handle_remote_heartbeat(payload)

    def _handle_local_heartbeat(self, payload: dict) -> None:
        """Local mode: print to stderr + check file-based kill signal."""
        if self._heartbeat_count % 3 == 0:  # Print every 3rd beat to reduce noise
            cpu = payload["metrics"]["cpu_percent"]
            mem = payload["metrics"]["memory_mb"]
            acts = len(self.actions)
            sys.stderr.write(
                f"\r\033[90m[killswitch] {self.name} | "
                f"cpu={cpu}% mem={mem:.0f}MB acts={acts} | "
                f"kill: touch /tmp/killswitch_kill_{self.agent_id}\033[0m"
            )
            sys.stderr.flush()

        if check_local_kill_signal(self.agent_id):
            self._execute_kill("local file signal")

    def _handle_remote_heartbeat(self, payload: dict) -> None:
        """Remote mode: POST to server, check response for kill signal."""
        url = f"{self.server_url.rstrip('/')}/api/heartbeat"
        resp = post_json(url, payload, api_key=self.api_key)

        if resp and resp.get("kill_requested"):
            self._execute_kill("remote server signal")

    def _execute_kill(self, reason: str) -> None:
        """Execute kill sequence."""
        self._status = "killed"
        self._running = False

        sys.stderr.write(
            f"\n\033[91m[killswitch] KILL SIGNAL RECEIVED ({reason})\033[0m\n"
        )
        sys.stderr.write(
            f"\033[91m[killswitch] Terminating {self.name} (pid={self.agent_id})...\033[0m\n"
        )
        sys.stderr.flush()

        self.actions.log("KILLED", detail=reason)

        if self.on_kill:
            try:
                self.on_kill(reason)
            except Exception:
                pass

        kill_self()


def monitor(
    name: str = "unnamed-agent",
    agent_id: Optional[str] = None,
    server_url: Optional[str] = None,
    api_key: Optional[str] = None,
    on_kill: Optional[callable] = None,
) -> Killswitch:
    """One-liner to start monitoring. Returns Killswitch instance.

    Usage:
        from killswitch import monitor
        monitor(name="my-agent")
    """
    global _active_instance
    ks = Killswitch(
        name=name,
        agent_id=agent_id,
        server_url=server_url,
        api_key=api_key,
        on_kill=on_kill,
    )
    ks.start()
    _active_instance = ks
    return ks


def _print_local_banner(name: str, agent_id: str) -> None:
    """Print startup banner in local mode."""
    sys.stderr.write(
        f"\n\033[92m"
        f"╔══════════════════════════════════════════════╗\n"
        f"║  Agent Killswitch v0.1.0                     ║\n"
        f"║  Agent: {name:<37s}║\n"
        f"║  ID:    {agent_id:<37s}║\n"
        f"║  Mode:  LOCAL (no server)                    ║\n"
        f"║                                              ║\n"
        f"║  Kill:  touch /tmp/killswitch_kill_{agent_id}  ║\n"
        f"╚══════════════════════════════════════════════╝"
        f"\033[0m\n\n"
    )
    sys.stderr.flush()
