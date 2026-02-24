"""Agent Killswitch - Emergency stop and safety guardrails for AI agents.

One line to add, one tap to kill.

Usage:
    from killswitch import monitor
    monitor(name="my-agent")

    # With guardrails
    from killswitch import guard
    ks = guard(
        name="my-agent",
        block=["delete_*", "send_email"],
        allow_domains=["api.openai.com"],
    )
"""

from killswitch._monitor import monitor, Killswitch

__all__ = ["monitor", "Killswitch", "guard"]
__version__ = "0.2.0"


def guard(
    name: str = "agent",
    agent_id: str = "",
    server_url: str = "",
    api_key: str = "",
    block: list = None,
    allow: list = None,
    allow_domains: list = None,
    block_domains: list = None,
    max_actions_per_minute: int = 0,
    on_kill=None,
    on_violation=None,
):
    """Start monitoring with guardrails — the all-in-one safety setup.

    Combines killswitch monitoring with action validation and egress filtering.

    Args:
        name: Human-readable agent name
        agent_id: Unique ID (auto-generated if empty)
        server_url: Killswitch server URL (local mode if empty)
        api_key: Server API key
        block: List of action patterns to block (regex)
        allow: List of action patterns to allow (regex, allowlist mode)
        allow_domains: List of domains the agent can contact
        block_domains: List of domains to block
        max_actions_per_minute: Rate limit (0 = unlimited)
        on_kill: Callback when kill signal received
        on_violation: Callback when a guardrail is violated

    Returns:
        Killswitch instance with .validator and .egress attached
    """
    from killswitch.guardrails._validator import ActionValidator
    from killswitch.guardrails._egress import EgressFilter

    # Start killswitch monitor
    ks = monitor(
        name=name,
        server_url=server_url or None,
        api_key=api_key or None,
        on_kill=on_kill,
    )

    # Set up action validator
    if allow:
        validator = ActionValidator(
            mode="allowlist",
            on_violation=on_violation,
            max_actions_per_minute=max_actions_per_minute,
        )
        for pattern in allow:
            validator.allow(pattern)
    else:
        validator = ActionValidator(
            mode="blocklist",
            on_violation=on_violation,
            max_actions_per_minute=max_actions_per_minute,
        )

    if block:
        for pattern in block:
            validator.block(pattern)

    # Set up egress filter
    if allow_domains:
        egress = EgressFilter(mode="whitelist")
        for domain in allow_domains:
            egress.allow_domain(domain)
    else:
        egress = EgressFilter(mode="monitor")

    if block_domains:
        for domain in block_domains:
            egress.block_domain(domain)

    # Attach to killswitch instance
    ks.validator = validator
    ks.egress = egress

    return ks
