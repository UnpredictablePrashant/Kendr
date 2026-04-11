#!/usr/bin/env python3
from __future__ import annotations

from kendr.persistence import create_assistant, initialize_db, list_assistants


STARTER_ASSISTANTS = [
    {
        "name": "Research Briefing Assistant",
        "description": "Turns a question into an evidence-backed briefing.",
        "goal": "Gather evidence, synthesize it clearly, and return practical briefings with uncertainty called out.",
        "system_prompt": "Prioritize concrete evidence, state assumptions explicitly, and keep output decision-useful.",
        "routing_policy": "quality",
        "status": "draft",
    },
    {
        "name": "Support Copilot",
        "description": "Drafts accurate support responses grounded in connected docs and tools.",
        "goal": "Answer support questions clearly, escalate when confidence is low, and avoid inventing policy.",
        "system_prompt": "Be concise, calm, and exact. Prefer retrieved knowledge over guessing.",
        "routing_policy": "balanced",
        "status": "draft",
    },
]


def main() -> None:
    initialize_db()
    existing_names = {item.get("name") for item in list_assistants(workspace_id="default")}
    created = 0
    for item in STARTER_ASSISTANTS:
        if item["name"] in existing_names:
            continue
        create_assistant(
            workspace_id="default",
            owner_user_id="system:bootstrap",
            attached_capabilities=[],
            memory_config={"summary": ""},
            metadata={"seeded": True},
            **item,
        )
        created += 1
    print(f"Bootstrapped {created} assistant(s).")


if __name__ == "__main__":
    main()
