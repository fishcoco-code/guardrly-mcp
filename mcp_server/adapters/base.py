"""PlatformAdapter base class."""

from abc import ABC, abstractmethod


class PlatformAdapter(ABC):
    """Abstract base class for all platform adapters."""

    platform_key: str = ""

    @abstractmethod
    def match(self, method: str, path: str) -> dict | None:
        """
        Match URL path + HTTP method against platform rule dictionary.

        Returns: {label: str, risk_level: int, matched_pattern: str}
        Returns None if no rule matches.
        """

    @abstractmethod
    def get_risk_level(self, method: str, path: str) -> int:
        """
        Return inferred risk level when no rule matches.
        Subclasses may override for platform-specific logic.
        """
