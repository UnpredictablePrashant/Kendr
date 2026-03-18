from tasks.a2a_protocol import (
    append_artifact,
    append_message,
    complete_task,
    ensure_a2a_state,
    make_artifact,
    make_message,
    task_for_agent,
)
from tasks.utils import record_work_note


def begin_agent_session(state: dict, agent_name: str) -> tuple[dict | None, str, str]:
    ensure_a2a_state(state)
    active_task = state.get("active_task")

    if not active_task or active_task.get("recipient") != agent_name:
        active_task = task_for_agent(state, agent_name)
        if active_task:
            state["active_task"] = active_task

    sender = active_task["sender"] if active_task else "orchestrator_agent"
    content = active_task["content"] if active_task and active_task.get("content") else state.get("user_query", "")

    if active_task and isinstance(active_task.get("state_updates"), dict):
        state.update(active_task["state_updates"])

    state = append_message(
        state,
        make_message(agent_name, sender, "accepted", content or f"{agent_name} accepted the task."),
    )
    task_id = active_task["task_id"] if active_task else "no-task-id"
    record_work_note(
        state,
        agent_name,
        "accepted",
        f"task_id={task_id}\nsender={sender}\nwork_item={content or 'No content provided.'}",
    )
    return active_task, content, sender


def publish_agent_output(
    state: dict,
    agent_name: str,
    content: str,
    artifact_name: str,
    kind: str = "text",
    recipients: list[str] | None = None,
):
    ensure_a2a_state(state)
    active_task = state.get("active_task")
    recipients = recipients or ["orchestrator_agent"]

    for recipient in recipients:
        state = append_message(
            state,
            make_message(agent_name, recipient, "result", content or f"{agent_name} produced no output."),
        )

    state = append_artifact(
        state,
        make_artifact(
            name=artifact_name,
            kind=kind,
            content=content or "",
            metadata={
                "agent": agent_name,
                "task_id": active_task["task_id"] if active_task else None,
            },
        ),
    )

    if active_task:
        state = complete_task(state, active_task["task_id"], "completed")
    task_id = active_task["task_id"] if active_task else "no-task-id"
    record_work_note(
        state,
        agent_name,
        "completed",
        f"task_id={task_id}\nrecipients={', '.join(recipients)}\noutput={content or 'No output.'}",
    )
    return state


def recent_messages_for_agent(state: dict, agent_name: str, limit: int = 6) -> str:
    ensure_a2a_state(state)
    inbound = [m for m in state["a2a"]["messages"] if m["recipient"] == agent_name]
    if not inbound:
        return "No recent A2A messages."

    lines = []
    for item in inbound[-limit:]:
        lines.append(f"{item['sender']} [{item['role']}]: {item['content']}")
    return "\n".join(lines)
