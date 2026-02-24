"""Ring buffer for tracking agent actions."""

import time
from collections import deque
from typing import Optional


class ActionLog:
    """Thread-safe ring buffer for recent agent actions."""

    def __init__(self, maxlen: int = 50):
        self._buffer: deque = deque(maxlen=maxlen)

    def log(self, action: str, detail: Optional[str] = None) -> None:
        """Log an action with timestamp."""
        entry = {
            "t": time.time(),
            "action": action,
        }
        if detail:
            entry["detail"] = detail
        self._buffer.append(entry)

    def recent(self, n: int = 10) -> list[dict]:
        """Get the N most recent actions."""
        items = list(self._buffer)
        return items[-n:]

    def clear(self) -> None:
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)
