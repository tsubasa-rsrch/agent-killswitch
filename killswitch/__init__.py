"""Agent Killswitch - Emergency stop for AI agents.

One line to add, one tap to kill.

Usage:
    from killswitch import monitor
    monitor(name="my-agent")
"""

from killswitch._monitor import monitor, Killswitch

__all__ = ["monitor", "Killswitch"]
__version__ = "0.1.0"
