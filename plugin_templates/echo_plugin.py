from __future__ import annotations

from superagent.types import AgentDefinition


PLUGIN = {
    "name": "example.echo",
    "description": "Example external plugin that registers a simple echo agent.",
    "version": "0.1.0",
}


def echo_agent(state: dict) -> dict:
    text = state.get("user_query", "")
    state["draft_response"] = f"echo: {text}"
    return state


def register(registry) -> None:
    registry.register_agent(
        AgentDefinition(
            name="echo_agent",
            handler=echo_agent,
            description="Simple example agent used as a plugin template.",
            skills=["example", "echo"],
            input_keys=["user_query"],
            output_keys=["draft_response"],
            plugin_name=PLUGIN["name"],
        )
    )
