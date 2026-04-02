"""
MessageBus — in-process event bus for agent coordination.

Event naming convention: ``<agent>:<action>``
Examples: ``architect:complete``, ``scaffolder:complete``, ``planner:complete``

All agents communicate via the bus; they never call each other directly.
Wildcard subscribers (subscribed to ``"*"``) receive every event — used by
the monitor agent to observe the full pipeline.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Callable

EventHandler = Callable[[str, dict[str, Any]], None]


class MessageBus:
    """In-process publish/subscribe event bus.

    Usage::

        bus = MessageBus()

        # Subscribe to a specific event
        bus.subscribe("architect:complete", lambda event, data: print(data))

        # Subscribe to all events (wildcard)
        bus.subscribe("*", lambda event, data: print(event, data))

        # Emit an event
        bus.emit("architect:complete", {"files": ["ARCHITECTURE.md"]})
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._wildcard_handlers: list[EventHandler] = []
        self._event_log: list[dict[str, Any]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def subscribe(self, event: str, handler: EventHandler) -> None:
        """Register *handler* to be called when *event* is emitted.

        Pass ``"*"`` as *event* to receive every event (monitor pattern).
        """
        if event == "*":
            self._wildcard_handlers.append(handler)
        else:
            self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        """Remove a previously registered handler."""
        if event == "*":
            try:
                self._wildcard_handlers.remove(handler)
            except ValueError:
                pass
        else:
            try:
                self._handlers[event].remove(handler)
            except ValueError:
                pass

    def emit(self, event: str, data: dict[str, Any] | None = None) -> None:
        """Publish *event* with optional *data* payload.

        All matching handlers are called synchronously in registration order,
        followed by wildcard handlers.  Handler exceptions are caught and
        stored in the event log so one bad handler cannot abort the pipeline.
        """
        payload: dict[str, Any] = data or {}
        record: dict[str, Any] = {
            "event": event,
            "data": payload,
            "timestamp": time.time(),
            "errors": [],
        }
        self._event_log.append(record)

        for handler in list(self._handlers.get(event, [])):
            try:
                handler(event, payload)
            except Exception as exc:  # noqa: BLE001
                record["errors"].append({"handler": repr(handler), "error": str(exc)})

        for handler in list(self._wildcard_handlers):
            try:
                handler(event, payload)
            except Exception as exc:  # noqa: BLE001
                record["errors"].append({"handler": repr(handler), "error": str(exc)})

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_log(self) -> list[dict[str, Any]]:
        """Return a copy of the ordered event log (immutable snapshot)."""
        return list(self._event_log)

    def events_for(self, agent: str) -> list[dict[str, Any]]:
        """Return all log entries whose event starts with ``<agent>:``."""
        prefix = f"{agent}:"
        return [e for e in self._event_log if e["event"].startswith(prefix)]

    def clear_log(self) -> None:
        """Discard the event log (useful between pipeline runs)."""
        self._event_log.clear()

    def handler_count(self, event: str = "*") -> int:
        """Return total number of registered handlers for *event*."""
        if event == "*":
            return sum(len(v) for v in self._handlers.values()) + len(self._wildcard_handlers)
        return len(self._handlers.get(event, [])) + len(self._wildcard_handlers)

    def __repr__(self) -> str:  # pragma: no cover
        specific = sum(len(v) for v in self._handlers.values())
        return (
            f"<MessageBus events={len(self._event_log)} "
            f"specific_handlers={specific} "
            f"wildcard_handlers={len(self._wildcard_handlers)}>"
        )
