from __future__ import annotations

import importlib
import importlib.util
import inspect
import os
import pkgutil
from pathlib import Path

import tasks

from .registry import Registry
from .types import AgentDefinition, ChannelDefinition, PluginDefinition, ProviderDefinition


IGNORE_TASK_MODULES = {
    "__pycache__",
    "a2a_agent_utils",
    "a2a_protocol",
    "research_infra",
    "setup_registry",
    "sqlite_store",
    "utils",
}


PROVIDER_DEFINITIONS = [
    ("openai", "Core LLM provider for orchestration, reasoning, OCR, and research."),
    ("elevenlabs", "Speech and voice provider for text-to-speech and transcription."),
    ("serpapi", "Search provider for web, travel, scholarly, and patent lookup."),
    ("google_workspace", "Gmail and Google Drive workspace provider."),
    ("telegram", "Telegram bot or session provider."),
    ("slack", "Slack workspace provider."),
    ("microsoft_graph", "Outlook, Teams, and OneDrive provider."),
    ("aws", "AWS cloud provider."),
    ("qdrant", "Vector memory provider."),
    ("whatsapp", "WhatsApp Cloud API provider."),
    ("playwright", "Browser automation provider."),
    ("nmap", "Local network scanning provider."),
    ("zap", "OWASP ZAP baseline scanning provider."),
    ("cve_database", "CVE/NVD lookup provider."),
]


CHANNEL_DEFINITIONS = [
    ("webchat", "Browser-based chat surface."),
    ("telegram", "Telegram chat channel."),
    ("slack", "Slack channel surface."),
    ("whatsapp", "WhatsApp chat surface."),
    ("teams", "Microsoft Teams channel."),
    ("discord", "Discord channel."),
    ("matrix", "Matrix channel."),
    ("signal", "Signal channel."),
]


def _titleize(name: str) -> str:
    return name.replace("_", " ").strip().capitalize()


def _default_description(agent_name: str) -> str:
    if agent_name.endswith("_agent"):
        agent_name = agent_name[:-6]
    return f"{_titleize(agent_name)} agent."


def _default_skills(agent_name: str) -> list[str]:
    base = agent_name[:-6] if agent_name.endswith("_agent") else agent_name
    return [token for token in base.split("_") if token]


def _register_builtin_capabilities(registry: Registry) -> None:
    registry.register_plugin(
        PluginDefinition(
            name="builtin.core",
            source="builtin",
            description="Built-in channels and providers for the superagent runtime.",
        )
    )
    for name, description in PROVIDER_DEFINITIONS:
        registry.register_provider(ProviderDefinition(name=name, description=description, plugin_name="builtin.core"))
    for name, description in CHANNEL_DEFINITIONS:
        registry.register_channel(ChannelDefinition(name=name, description=description, plugin_name="builtin.core"))


def _register_task_module_agents(registry: Registry, module_name: str) -> None:
    module = importlib.import_module(module_name)
    plugin_name = f"builtin.{module_name}"
    registry.register_plugin(
        PluginDefinition(
            name=plugin_name,
            source=module_name,
            description=f"Built-in agents discovered from {module_name}.",
        )
    )
    module_metadata = getattr(module, "AGENT_METADATA", {})
    for name, fn in inspect.getmembers(module, inspect.isfunction):
        if fn.__module__ != module.__name__:
            continue
        if not name.endswith("_agent") or name.startswith("_"):
            continue
        metadata = module_metadata.get(name, {}) if isinstance(module_metadata, dict) else {}
        description = metadata.get("description") or inspect.getdoc(fn) or _default_description(name)
        registry.register_agent(
            AgentDefinition(
                name=name,
                handler=fn,
                description=description,
                skills=metadata.get("skills") or _default_skills(name),
                input_keys=metadata.get("input_keys", []),
                output_keys=metadata.get("output_keys", []),
                plugin_name=plugin_name,
                requirements=metadata.get("requirements", []),
                metadata=metadata,
            )
        )


def _discover_builtin_task_agents(registry: Registry) -> None:
    for module_info in pkgutil.iter_modules(tasks.__path__):
        name = module_info.name
        if name in IGNORE_TASK_MODULES or name.startswith("__"):
            continue
        _register_task_module_agents(registry, f"tasks.{name}")


def _load_external_plugin(registry: Registry, plugin_path: Path) -> None:
    module_name = f"external_plugin_{plugin_path.stem}_{abs(hash(str(plugin_path)))}"
    spec = importlib.util.spec_from_file_location(module_name, plugin_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load plugin from {plugin_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    register = getattr(module, "register", None)
    if not callable(register):
        raise RuntimeError(f"Plugin {plugin_path} must define a callable register(registry) function.")
    plugin_meta = getattr(module, "PLUGIN", {}) or {}
    registry.register_plugin(
        PluginDefinition(
            name=plugin_meta.get("name", plugin_path.stem),
            source=str(plugin_path),
            description=plugin_meta.get("description", "External plugin."),
            version=plugin_meta.get("version", "0.1.0"),
            kind="external",
            metadata=plugin_meta,
        )
    )
    register(registry)


def _plugin_search_paths() -> list[Path]:
    home = Path(os.getenv("SUPERAGENT_HOME", Path.home() / ".superagent")).expanduser()
    configured = os.getenv("SUPERAGENT_PLUGIN_PATHS", "")
    paths = [
        Path.cwd() / "plugins",
        home / "plugins",
    ]
    for raw in configured.split(os.pathsep):
        raw = raw.strip()
        if raw:
            paths.append(Path(raw).expanduser())
    unique = []
    seen = set()
    for path in paths:
        if str(path) in seen:
            continue
        seen.add(str(path))
        unique.append(path)
    return unique


def _discover_external_plugins(registry: Registry) -> None:
    for base in _plugin_search_paths():
        if not base.exists():
            continue
        for plugin_path in sorted(base.glob("*.py")):
            _load_external_plugin(registry, plugin_path)


def build_registry() -> Registry:
    registry = Registry()
    _register_builtin_capabilities(registry)
    _discover_builtin_task_agents(registry)
    _discover_external_plugins(registry)
    return registry
