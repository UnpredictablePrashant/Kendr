from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


StateHandler = Callable[[dict], dict]


@dataclass(slots=True)
class AgentDefinition:
    name: str
    handler: StateHandler
    description: str
    skills: list[str] = field(default_factory=list)
    input_keys: list[str] = field(default_factory=list)
    output_keys: list[str] = field(default_factory=list)
    plugin_name: str = "builtin"
    requirements: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ChannelDefinition:
    name: str
    description: str
    plugin_name: str = "builtin"
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class ProviderDefinition:
    name: str
    description: str
    auth_mode: str = "api_key"
    plugin_name: str = "builtin"
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class PluginDefinition:
    name: str
    source: str
    description: str = ""
    version: str = "0.1.0"
    kind: str = "builtin"
    metadata: dict = field(default_factory=dict)
