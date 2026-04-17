"""Platform adapter registry."""

from mcp_server.adapters.base import PlatformAdapter
from mcp_server.adapters.generic import GenericAdapter
from mcp_server.adapters.meta import MetaAdapter
from mcp_server.adapters.shopify import ShopifyAdapter

ADAPTERS: dict[str, type[PlatformAdapter]] = {
    "shopify": ShopifyAdapter,
    "meta": MetaAdapter,
    "generic": GenericAdapter,
}

_instances: dict[str, PlatformAdapter] = {}


def get_adapter(platform: str) -> PlatformAdapter:
    """Return a singleton adapter instance for the given platform.

    Falls back to GenericAdapter for unrecognised platform keys.
    """
    key = platform.lower()
    if key not in _instances:
        cls = ADAPTERS.get(key, GenericAdapter)
        _instances[key] = cls()
    return _instances[key]
