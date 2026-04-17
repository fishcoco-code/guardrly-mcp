"""Shopify Admin API platform adapter."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from mcp_server.adapters.base import PlatformAdapter

logger = logging.getLogger(__name__)

_RULES_PATH = Path(__file__).parent.parent / "rules" / "shopify.json"


def _load_and_compile(path: Path) -> list[dict[str, Any]]:
    """Load rules from JSON and precompile regex patterns."""
    with open(path, encoding="utf-8") as f:
        raw: list[dict] = json.load(f)
    compiled = []
    for rule in raw:
        try:
            compiled.append({
                "method": rule["method"].upper(),
                "pattern": re.compile(rule["pattern"], re.IGNORECASE),
                "raw_pattern": rule["pattern"],
                "label": rule["label"],
                "risk_level": rule["risk_level"],
            })
        except re.error as exc:
            logger.error("Failed to compile Shopify rule pattern %r: %s", rule.get("pattern"), exc)
    return compiled


# Module-level compiled rules - loaded once at import time
_COMPILED_RULES: list[dict[str, Any]] = _load_and_compile(_RULES_PATH)


def reload_rules() -> int:
    """Reload rules from JSON file without server restart.

    Returns count of rules successfully loaded.
    """
    global _COMPILED_RULES
    try:
        _COMPILED_RULES = _load_and_compile(_RULES_PATH)
        logger.info("Shopify rules reloaded: %d rules", len(_COMPILED_RULES))
        return len(_COMPILED_RULES)
    except Exception as exc:
        logger.error("Failed to reload Shopify rules: %s - keeping old rules", exc)
        return len(_COMPILED_RULES)


class ShopifyAdapter(PlatformAdapter):
    """Shopify Admin API adapter with 50-rule semantic dictionary."""

    platform_key = "shopify"

    def match(self, method: str, path: str) -> dict | None:
        """
        Match path + method against the Shopify rule dictionary.

        Each compiled rule pattern encodes the method prefix, e.g.
        "DELETE /admin/api/.*/products/(\\d+)$", so we match against
        "{METHOD} {path}".

        Returns: {label, risk_level, matched_pattern} or None.
        Method matching is case-insensitive.
        """
        method_upper = method.upper()
        target = f"{method_upper} {path}"
        for rule in _COMPILED_RULES:
            if rule["method"] != method_upper:
                continue
            if rule["pattern"].search(target):
                return {
                    "label": rule["label"],
                    "risk_level": rule["risk_level"],
                    "matched_pattern": rule["raw_pattern"],
                }
        return None

    def get_risk_level(self, method: str, path: str) -> int:
        """Infer risk from HTTP method when no rule matches."""
        m = method.upper()
        if m == "DELETE":
            return 2
        if m in ("POST", "PUT", "PATCH"):
            return 1
        return 0
