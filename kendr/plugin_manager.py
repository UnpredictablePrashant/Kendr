"""Compatibility shim for the legacy external-service plugin surface.

Use ``kendr.integration_registry`` for the canonical service-integration API.
This module remains for backward compatibility while the codebase migrates away
from overloaded "plugin" naming.
"""

from __future__ import annotations

from kendr.integration_registry import (
    AGENT_INTEGRATION_MAP,
    INTEGRATION_REGISTRY,
    IntegrationAction,
    IntegrationCard,
    check_agent_integration_config,
    get_integration,
    integration_categories,
    list_configured_integrations,
    list_integrations,
    list_unconfigured_integrations,
)


PluginAction = IntegrationAction
PluginCard = IntegrationCard
PLUGIN_REGISTRY = INTEGRATION_REGISTRY
AGENT_PLUGIN_MAP = AGENT_INTEGRATION_MAP


def check_agent_plugin_config(
    agent_name: str,
    existing_config_hint: str = "",
) -> tuple[str, list[str], bool, str]:
    return check_agent_integration_config(agent_name, existing_config_hint)


def list_plugins(category: str = "") -> list[PluginCard]:
    return list_integrations(category)


def list_configured_plugins() -> list[PluginCard]:
    return list_configured_integrations()


def list_unconfigured_plugins() -> list[PluginCard]:
    return list_unconfigured_integrations()


def get_plugin(plugin_id: str) -> PluginCard | None:
    return get_integration(plugin_id)


def plugin_categories() -> list[str]:
    return integration_categories()


__all__ = [
    "PluginAction",
    "PluginCard",
    "PLUGIN_REGISTRY",
    "AGENT_PLUGIN_MAP",
    "check_agent_plugin_config",
    "list_plugins",
    "list_configured_plugins",
    "list_unconfigured_plugins",
    "get_plugin",
    "plugin_categories",
]
