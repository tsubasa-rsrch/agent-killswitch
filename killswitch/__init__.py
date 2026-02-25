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

    # With auto-kill on policy violations
    ks = guard(
        name="my-agent",
        block=["delete_*", "send_email"],
        auto_kill_threshold=100,  # Kill after 100 violation points
    )
"""

from killswitch._monitor import monitor, Killswitch
from killswitch._policy import PolicyEngine
from killswitch._erosion import ErosionDetector

__all__ = ["monitor", "Killswitch", "guard", "PolicyEngine", "ErosionDetector"]
__version__ = "0.4.0"


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
    auto_kill_threshold: int = 100,
    alert_threshold: int = 25,
    on_kill=None,
    on_violation=None,
    on_alert=None,
    on_erosion=None,
    persist: bool = False,
    erosion_detection: bool = False,
):
    """Start monitoring with guardrails — the all-in-one safety setup.

    Combines killswitch monitoring with action validation, egress filtering,
    and automatic policy enforcement (alert → pause → kill).

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
        auto_kill_threshold: Kill agent after this many violation points (0 = no auto-kill)
        alert_threshold: Alert after this many violation points
        on_kill: Callback when kill signal received
        on_violation: Callback when a guardrail is violated
        on_alert: Callback when alert threshold reached (receives violation, score, level)
        on_erosion: Callback when erosion pattern detected (receives ErosionSignal)
        persist: Save violations to disk across agent restarts (v0.4)
        erosion_detection: Detect "first refusal erosion" patterns (v0.4)

    Returns:
        Killswitch instance with .validator, .egress, and .policy attached
    """
    from killswitch.guardrails._validator import ActionValidator
    from killswitch.guardrails._egress import EgressFilter

    # Create policy engine (v0.4: with persistence + erosion)
    policy = PolicyEngine(
        kill_threshold=auto_kill_threshold,
        alert_threshold=alert_threshold,
        on_alert=on_alert,
        on_erosion=on_erosion,
        auto_kill=auto_kill_threshold > 0,
        persist=persist,
        agent_name=name,
        erosion_detection=erosion_detection,
    )

    # Start killswitch monitor
    ks = monitor(
        name=name,
        agent_id=agent_id or None,
        server_url=server_url or None,
        api_key=api_key or None,
        on_kill=on_kill,
    )

    # Attach policy engine to killswitch (for auto-kill)
    policy.attach(ks)
    ks.policy = policy

    # Create callbacks that chain: user callback + policy engine
    def validator_violation_handler(v):
        if on_violation:
            on_violation(v)
        policy.make_validator_callback()(v)

    def egress_block_handler(v):
        if on_violation:
            on_violation(v)
        policy.make_egress_callback()(v)

    # Set up action validator
    if allow:
        validator = ActionValidator(
            mode="allowlist",
            on_violation=validator_violation_handler,
            max_actions_per_minute=max_actions_per_minute,
        )
        for pattern in allow:
            validator.allow(pattern)
    else:
        validator = ActionValidator(
            mode="blocklist",
            on_violation=validator_violation_handler,
            max_actions_per_minute=max_actions_per_minute,
        )

    if block:
        for pattern in block:
            validator.block(pattern)

    # Set up egress filter
    if allow_domains:
        egress = EgressFilter(mode="whitelist", on_block=egress_block_handler)
        for domain in allow_domains:
            egress.allow_domain(domain)
    else:
        egress = EgressFilter(mode="monitor", on_block=egress_block_handler)

    if block_domains:
        for domain in block_domains:
            egress.block_domain(domain)

    # Attach to killswitch instance
    ks.validator = validator
    ks.egress = egress

    return ks
