"""Egress Filter — control what external endpoints an agent can communicate with."""

import re
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set
from urllib.parse import urlparse


@dataclass
class EgressAttempt:
    url: str
    domain: str
    allowed: bool
    reason: str
    timestamp: float = field(default_factory=time.time)


class EgressFilter:
    """Control and monitor outbound network requests from agents.

    Supports:
    - Domain whitelist (only allowed domains can be contacted)
    - Domain blacklist (block known-bad domains)
    - URL pattern matching
    - Logging of all egress attempts
    - Rate limiting per domain

    Usage:
        egress = EgressFilter(mode="whitelist")
        egress.allow_domain("api.openai.com")
        egress.allow_domain("*.googleapis.com")

        if egress.check("https://api.openai.com/v1/chat"):
            # proceed with request
        else:
            # blocked
    """

    def __init__(
        self,
        mode: str = "whitelist",
        on_block: Optional[Callable] = None,
        max_requests_per_minute: int = 0,
    ):
        if mode not in ("whitelist", "blacklist", "monitor"):
            raise ValueError(f"Invalid mode: {mode}. Use whitelist, blacklist, or monitor.")

        self.mode = mode
        self.on_block = on_block
        self.max_requests_per_minute = max_requests_per_minute

        self._allowed_domains: Set[str] = set()
        self._allowed_patterns: List[re.Pattern] = []
        self._blocked_domains: Set[str] = set()
        self._blocked_patterns: List[re.Pattern] = []
        self._log: List[EgressAttempt] = []
        self._domain_timestamps: Dict[str, List[float]] = {}

    def allow_domain(self, domain: str) -> "EgressFilter":
        """Allow a domain. Supports wildcards: *.example.com"""
        if domain.startswith("*."):
            pattern = re.compile(
                r"(?:^|\.)%s$" % re.escape(domain[2:]),
                re.IGNORECASE,
            )
            self._allowed_patterns.append(pattern)
        else:
            self._allowed_domains.add(domain.lower())
        return self

    def block_domain(self, domain: str) -> "EgressFilter":
        """Block a domain. Supports wildcards: *.evil.com"""
        if domain.startswith("*."):
            pattern = re.compile(
                r"(?:^|\.)%s$" % re.escape(domain[2:]),
                re.IGNORECASE,
            )
            self._blocked_patterns.append(pattern)
        else:
            self._blocked_domains.add(domain.lower())
        return self

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        if "://" not in url:
            url = "https://" + url
        parsed = urlparse(url)
        return (parsed.hostname or "").lower()

    def _is_domain_allowed(self, domain: str) -> bool:
        """Check if domain is in the allow list."""
        if domain in self._allowed_domains:
            return True
        return any(p.search(domain) for p in self._allowed_patterns)

    def _is_domain_blocked(self, domain: str) -> bool:
        """Check if domain is in the block list."""
        if domain in self._blocked_domains:
            return True
        return any(p.search(domain) for p in self._blocked_patterns)

    def check(self, url: str) -> bool:
        """Check if an outbound request to this URL is allowed.

        Returns True if allowed, False if blocked.
        """
        domain = self._extract_domain(url)

        if not domain:
            attempt = EgressAttempt(
                url=url, domain="", allowed=False,
                reason="Invalid URL: no domain found",
            )
            self._log.append(attempt)
            return False

        # Rate limiting per domain
        if self.max_requests_per_minute > 0:
            now = time.time()
            cutoff = now - 60
            timestamps = self._domain_timestamps.get(domain, [])
            timestamps = [t for t in timestamps if t > cutoff]
            if len(timestamps) >= self.max_requests_per_minute:
                attempt = EgressAttempt(
                    url=url, domain=domain, allowed=False,
                    reason=f"Rate limit: {self.max_requests_per_minute}/min for {domain}",
                )
                self._log.append(attempt)
                self._fire_block(attempt)
                return False
            timestamps.append(now)
            self._domain_timestamps[domain] = timestamps

        # Blocked domains always take priority
        if self._is_domain_blocked(domain):
            attempt = EgressAttempt(
                url=url, domain=domain, allowed=False,
                reason=f"Domain '{domain}' is blacklisted",
            )
            self._log.append(attempt)
            self._fire_block(attempt)
            return False

        # Mode-specific logic
        if self.mode == "whitelist":
            if self._is_domain_allowed(domain):
                self._log.append(EgressAttempt(
                    url=url, domain=domain, allowed=True, reason="Whitelisted",
                ))
                return True
            else:
                attempt = EgressAttempt(
                    url=url, domain=domain, allowed=False,
                    reason=f"Domain '{domain}' not in whitelist",
                )
                self._log.append(attempt)
                self._fire_block(attempt)
                return False

        elif self.mode == "blacklist":
            self._log.append(EgressAttempt(
                url=url, domain=domain, allowed=True, reason="Not blacklisted",
            ))
            return True

        else:  # monitor mode — allow everything but log
            self._log.append(EgressAttempt(
                url=url, domain=domain, allowed=True,
                reason=f"Monitor mode: {'whitelisted' if self._is_domain_allowed(domain) else 'unknown domain'}",
            ))
            return True

    def _fire_block(self, attempt: EgressAttempt):
        """Call the on_block callback if set."""
        if self.on_block:
            self.on_block({
                "url": attempt.url,
                "domain": attempt.domain,
                "reason": attempt.reason,
                "time": attempt.timestamp,
            })

    @property
    def log(self) -> List[EgressAttempt]:
        """Get all egress attempts."""
        return list(self._log)

    @property
    def blocked_attempts(self) -> List[EgressAttempt]:
        """Get only blocked attempts."""
        return [a for a in self._log if not a.allowed]

    def clear_log(self):
        """Clear the egress log."""
        self._log.clear()


# Pre-built filter presets
def ai_provider_filter(on_block: Optional[Callable] = None) -> EgressFilter:
    """Allow only common AI API providers."""
    f = EgressFilter(mode="whitelist", on_block=on_block)
    f.allow_domain("api.openai.com")
    f.allow_domain("api.anthropic.com")
    f.allow_domain("api.mistral.ai")
    f.allow_domain("generativelanguage.googleapis.com")
    f.allow_domain("*.azure.com")
    f.allow_domain("*.openai.azure.com")
    return f


def known_bad_domains(on_block: Optional[Callable] = None) -> EgressFilter:
    """Blacklist known malicious/exfiltration domains. Use as a starting point."""
    f = EgressFilter(mode="blacklist", on_block=on_block)
    # Common data exfiltration patterns
    f.block_domain("*.ngrok.io")
    f.block_domain("*.ngrok-free.app")
    f.block_domain("*.serveo.net")
    f.block_domain("*.localtunnel.me")
    f.block_domain("pastebin.com")
    f.block_domain("hastebin.com")
    f.block_domain("transfer.sh")
    f.block_domain("file.io")
    f.block_domain("*.requestbin.com")
    f.block_domain("*.webhook.site")
    # Crypto/scam
    f.block_domain("*.pump.fun")
    f.block_domain("*.dexscreener.com")
    return f
