"""Generic HTTP fallback adapter - no semantic labels, method-based risk only."""

from mcp_server.adapters.base import PlatformAdapter


class GenericAdapter(PlatformAdapter):
    """Fallback adapter for unrecognised platforms.

    Does not match any semantic rules. Risk is inferred from HTTP method.
    """

    platform_key = "generic"

    def match(self, method: str, path: str) -> dict | None:
        """Generic adapter never matches - returns None for all inputs."""
        return None

    def get_risk_level(self, method: str, path: str) -> int:
        """Infer risk from HTTP method: DELETE->2, POST/PUT/PATCH->1, GET->0."""
        m = method.upper()
        if m == "DELETE":
            return 2
        if m in ("POST", "PUT", "PATCH"):
            return 1
        return 0
