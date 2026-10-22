# ABOUTME: Named asyncio locks (per watch, per user, ...) kept per event loop.
# ABOUTME: An asyncio.Lock belongs to one loop, so each running loop gets its own registry.

import asyncio
from collections.abc import Hashable
from weakref import WeakKeyDictionary

_registries: WeakKeyDictionary = WeakKeyDictionary()


def keyed_lock(namespace: str, key: Hashable) -> asyncio.Lock:
    """The lock for (namespace, key) in the running event loop."""
    loop = asyncio.get_running_loop()
    registry = _registries.get(loop)
    if registry is None:
        registry = {}
        _registries[loop] = registry
    lock = registry.get((namespace, key))
    if lock is None:
        lock = registry[(namespace, key)] = asyncio.Lock()
    return lock
