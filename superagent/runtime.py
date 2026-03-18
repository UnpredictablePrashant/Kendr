from __future__ import annotations

import json
from datetime import UTC, datetime

from langgraph.graph import END, StateGraph

from tasks.a2a_protocol import (
    append_artifact,
    append_message,
    append_task,
    complete_task,
    ensure_a2a_state,
    make_artifact,
    make_message,
    make_task,
    task_for_agent,
)
from tasks.review_tasks import reviewer_agent
from tasks.setup_registry import build_setup_snapshot
from tasks.sqlite_store import initialize_db, insert_agent_execution, insert_run, update_run
from tasks.utils import (
    OUTPUT_DIR,
    create_run_output_dir,
    llm,
    log_task_update,
    logger,
    record_work_note,
    resolve_output_path,
    reset_text_file,
    set_active_output_dir,
    write_text_file,
)

from .registry import Registry


class AgentRuntime:
    def __init__(self, registry: Registry):
        self.registry = registry

    def _agent_cards(self) -> list[dict]:
        return self.registry.agent_cards()

    def _agent_descriptions(self) -> dict[str, str]:
        return self.registry.agent_descriptions()

    def apply_runtime_setup(self, state: dict) -> dict:
        snapshot = build_setup_snapshot(self._agent_cards())
        available_agents = snapshot.get("available_agents", [])
        filtered_cards = [card for card in self._agent_cards() if card["agent_name"] in available_agents]
        state["setup_status"] = snapshot
        state["available_agents"] = available_agents
        state["disabled_agents"] = snapshot.get("disabled_agents", {})
        state["setup_actions"] = snapshot.get("setup_actions", [])
        state["setup_summary"] = snapshot.get("summary_text", "")
        state["available_agent_cards"] = filtered_cards
        ensure_a2a_state(state, filtered_cards)
        return state

    def _is_agent_available(self, state: dict, agent_name: str) -> bool:
        return agent_name in set(state.get("available_agents", []))

    def _available_agent_descriptions(self, state: dict) -> dict[str, str]:
        available = set(state.get("available_agents", []))
        return {name: description for name, description in self._agent_descriptions().items() if name in available}

    def _agent_enum(self, state: dict, include_finish: bool = False) -> str:
        choices = list(state.get("available_agents", []))
        if include_finish:
            choices.append("finish")
        return "|".join(choices)

    def _truncate(self, text: str, limit: int = 1200) -> str:
        cleaned = " ".join((text or "").split())
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: limit - 3] + "..."

    def _history_as_text(self, state: dict) -> str:
        history = state.get("agent_history", [])
        if not history:
            return "No agents have run yet."
        return "\n".join(
            f"- {item['agent']} ({item['status']}): reason={item['reason']} output={item['output_excerpt']}"
            for item in history[-6:]
        )

    def _recent_a2a_messages(self, state: dict) -> str:
        ensure_a2a_state(state, state.get("available_agent_cards") or self._agent_cards())
        messages = state["a2a"]["messages"]
        if not messages:
            return "No A2A messages yet."
        return "\n".join(
            f"- {item['sender']} -> {item['recipient']} [{item['role']}]: {self._truncate(item['content'], 240)}"
            for item in messages[-8:]
        )

    def _append_history(self, state: dict, agent_name: str, status: str, reason: str, output_text: str) -> dict:
        timestamp = datetime.now(UTC).isoformat()
        history = state.get("agent_history", [])
        history.append(
            {
                "timestamp": timestamp,
                "agent": agent_name,
                "status": status,
                "reason": reason,
                "output_excerpt": self._truncate(output_text),
            }
        )
        state["agent_history"] = history
        state["last_agent"] = agent_name
        state["last_agent_status"] = status
        state["last_agent_output"] = output_text
        run_id = state.get("run_id")
        if run_id:
            insert_agent_execution(run_id, timestamp, agent_name, status, reason, self._truncate(output_text))
        return state

    def _infer_agent_output(self, before: dict, after: dict) -> str:
        if after.get("draft_response") and after.get("draft_response") != before.get("draft_response"):
            return str(after.get("draft_response", ""))
        preferred_suffixes = ("_summary", "_report", "_analysis", "_result", "_results", "_profile", "_plan", "_output")
        changed = []
        before_keys = set(before.keys())
        for key, value in after.items():
            if key.startswith("_") or key in {"a2a", "available_agent_cards", "setup_status"}:
                continue
            if before.get(key) != value:
                changed.append((key, value, key not in before_keys))
        for key, value, _ in changed:
            if key.endswith(preferred_suffixes):
                if isinstance(value, str):
                    return value
                return json.dumps(value, ensure_ascii=False)
        if changed:
            key, value, _ = changed[0]
            if isinstance(value, str):
                return value
            return json.dumps({key: value}, ensure_ascii=False)
        return ""

    def _handle_unavailable_agent_choice(self, state: dict, agent_name: str, reason: str) -> tuple[str, str]:
        if agent_name == "finish" or self._is_agent_available(state, agent_name):
            return agent_name, reason
        setup_actions = json.dumps(state.get("setup_actions", []), ensure_ascii=False)
        if self._is_agent_available(state, "agent_factory_agent"):
            state["missing_capability"] = agent_name
            return (
                "agent_factory_agent",
                f"{reason} Requested capability maps to unavailable agent {agent_name}. Create a new agent or scaffold for this gap. Setup actions: {setup_actions}",
            )
        if self._is_agent_available(state, "worker_agent"):
            return (
                "worker_agent",
                f"{reason} Requested agent {agent_name} is not configured. Explain missing setup and available actions: {setup_actions}",
            )
        return "finish", reason

    def _strip_code_fences(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 2:
                return "\n".join(lines[1:-1]).strip()
        return stripped

    def _parse_orchestrator_output(self, raw_output: str) -> dict:
        return json.loads(self._strip_code_fences(raw_output))

    def _execute_agent(self, state: dict, agent_name: str) -> dict:
        state = self.apply_runtime_setup(state)
        if not self._is_agent_available(state, agent_name):
            unavailable_reason = (
                f"{agent_name} is not configured in the current environment. "
                f"Missing setup: {json.dumps(state.get('disabled_agents', {}).get(agent_name, {}), ensure_ascii=False)}"
            )
            state["last_error"] = unavailable_reason
            state["review_pending"] = False
            return self._append_history(state, agent_name, "skipped", state.get("orchestrator_reason", ""), unavailable_reason)

        spec = self.registry.agents[agent_name]
        log_task_update("System", f"Dispatching to {agent_name}.")
        ensure_a2a_state(state, state.get("available_agent_cards") or self._agent_cards())
        active_task = task_for_agent(state, agent_name)
        if not active_task:
            active_task = make_task(
                sender="orchestrator_agent",
                recipient=agent_name,
                intent="fallback-dispatch",
                content=state.get("orchestrator_reason", "No explicit task content was provided."),
            )
            state = append_task(state, active_task)

        state["active_task"] = active_task
        record_work_note(
            state,
            "orchestrator_agent",
            "dispatch",
            (
                f"agent={agent_name}\n"
                f"task_id={active_task['task_id']}\n"
                f"intent={active_task.get('intent', '')}\n"
                f"content={active_task.get('content', '')}"
            ),
        )
        state = append_message(state, make_message(active_task["sender"], agent_name, "task", active_task["content"]))
        task_updates = active_task.get("state_updates", {})
        if isinstance(task_updates, dict):
            state.update(task_updates)

        before_state = {k: v for k, v in state.items() if k != "a2a"}
        try:
            state = spec.handler(state)
            output_text = self._infer_agent_output(before_state, state)
            if active_task.get("status") == "pending":
                state = complete_task(state, active_task["task_id"], "completed")
            state["review_pending"] = agent_name != "reviewer_agent"
            state = self._append_history(state, agent_name, "success", state.get("orchestrator_reason", ""), output_text)
        except Exception as exc:
            error_message = str(exc)
            state["last_error"] = error_message
            state = complete_task(state, active_task["task_id"], "failed")
            state["review_pending"] = False
            state = append_message(state, make_message(agent_name, "orchestrator_agent", "error", error_message))
            state = append_artifact(
                state,
                make_artifact(
                    name=f"{agent_name}_error",
                    kind="error",
                    content=error_message,
                    metadata={"task_id": active_task["task_id"], "status": "failed"},
                ),
            )
            state = self._append_history(state, agent_name, "error", state.get("orchestrator_reason", ""), error_message)
            record_work_note(state, agent_name, "failed", f"task_id={active_task['task_id']}\nerror={error_message}")
            log_task_update("System", f"{agent_name} failed.", error_message)
        return state

    def orchestrator_agent(self, state: dict) -> dict:
        state["orchestrator_calls"] = state.get("orchestrator_calls", 0) + 1
        max_steps = state.get("max_steps", 20)
        state = self.apply_runtime_setup(state)
        ensure_a2a_state(state, state.get("available_agent_cards") or self._agent_cards())
        current_objective = state.get("current_objective") or state.get("user_query", "")

        if state["orchestrator_calls"] > max_steps:
            state["next_agent"] = "__finish__"
            state["final_output"] = (
                state.get("final_output")
                or state.get("draft_response")
                or state.get("last_agent_output")
                or "Reached the orchestration step limit without a better final answer."
            )
            return state

        if state.get("last_agent") and state.get("last_agent") != "reviewer_agent" and state.get("review_pending") and self._is_agent_available(state, "reviewer_agent"):
            reason = f"Review the completed step from {state['last_agent']} before continuing."
            state["orchestrator_reason"] = reason
            state["next_agent"] = "reviewer_agent"
            state = append_task(state, make_task(sender="orchestrator_agent", recipient="reviewer_agent", intent="step-review", content=reason, state_updates={}))
            record_work_note(state, "orchestrator_agent", "decision", f"next_agent=reviewer_agent\nreason={reason}\nstate_updates={{}}")
            return state

        if state.get("last_agent") == "reviewer_agent" and state.get("review_decision") == "revise":
            next_agent = state.get("review_target_agent") or "worker_agent"
            reason = state.get("review_reason", "Reviewer requested a corrected retry.")
            next_agent, reason = self._handle_unavailable_agent_choice(state, next_agent, reason)
            corrected_values = state.get("review_corrected_values", {})
            if not isinstance(corrected_values, dict):
                corrected_values = {}
            revised_objective = state.get("review_revised_objective") or current_objective
            corrected_values = {**corrected_values, "current_objective": revised_objective}
            state["orchestrator_reason"] = reason
            state["next_agent"] = next_agent
            state = append_task(
                state,
                make_task(
                    sender="reviewer_agent",
                    recipient=next_agent,
                    intent="correction",
                    content=revised_objective,
                    state_updates=corrected_values,
                ),
            )
            return state

        if state.get("last_agent") == "agent_factory_agent" and state.get("dynamic_agent_ready") and self._is_agent_available(state, "dynamic_agent_runner"):
            reason = "A generated agent is ready. Execute it through the dynamic agent runner."
            state["orchestrator_reason"] = reason
            state["next_agent"] = "dynamic_agent_runner"
            state = append_task(
                state,
                make_task(
                    sender="orchestrator_agent",
                    recipient="dynamic_agent_runner",
                    intent="run-generated-agent",
                    content=state.get("generated_agent_task") or current_objective,
                    state_updates={
                        "generated_agent_name": state.get("generated_agent_name", ""),
                        "generated_agent_function": state.get("generated_agent_function", ""),
                        "generated_agent_module_path": state.get("generated_agent_module_path", ""),
                        "generated_agent_task": state.get("generated_agent_task") or current_objective,
                    },
                ),
            )
            return state

        prompt = f"""
You are the orchestration agent for a plugin-driven multi-agent AI system.

Your job is to decide which agent should run next, or whether the workflow should finish.
Choose from exactly these currently available agents:
{json.dumps(self._available_agent_descriptions(state), indent=2)}

Rules:
- Only choose agents that appear in the available-agent list above.
- Use the description of each agent as the source of truth for what it does.
- If incoming_channel or incoming_payload is present and gateway_message has not been created yet, prefer channel_gateway_agent first.
- If gateway_message exists but channel_session is missing, prefer session_router_agent before other work.
- If the user asks for an unavailable integration, use worker_agent to explain the missing setup unless agent_factory_agent is better suited.
- Finish when the current state already contains a good final answer.
- Never use any agent for exploitation, credential attacks, service disruption, or unauthorized access.
- If the reviewer already requested a retry, follow that instruction rather than inventing a different reroute.
- Avoid repeating the same failing agent unless the inputs changed.
- Put only useful state updates for the chosen agent in `state_updates`.

Current user query:
{state.get("user_query", "")}

Current objective:
{current_objective}

Current plan:
{state.get("plan", "") or "None"}

Current draft response:
{state.get("draft_response", "") or "None"}

Current review decision:
{state.get("review_decision", "") or "None"}

Current review reason:
{state.get("review_reason", "") or "None"}

Reviewer recommended next agent:
{state.get("review_target_agent", "") or "None"}

Reviewer corrected values:
{json.dumps(state.get("review_corrected_values", {}), ensure_ascii=False)}

Current setup summary:
{state.get("setup_summary", "")}

Disabled or unavailable agents:
{json.dumps(state.get("disabled_agents", {}), indent=2, ensure_ascii=False)}

Available setup actions:
{json.dumps(state.get("setup_actions", []), indent=2, ensure_ascii=False)}

A2A agent cards:
{json.dumps(state["a2a"]["agent_cards"], indent=2)}

A2A messages:
{self._recent_a2a_messages(state)}

Recent agent history:
{self._history_as_text(state)}

Return ONLY valid JSON in this exact schema:
{{
  "agent": "{self._agent_enum(state, include_finish=True)}",
  "reason": "short reason",
  "state_updates": {{}},
  "task_content": "short task content for the chosen agent",
  "final_response": "required only when agent is finish"
}}
""".strip()

        response = llm.invoke(prompt)
        raw_output = response.content.strip() if hasattr(response, "content") else str(response).strip()
        try:
            decision = self._parse_orchestrator_output(raw_output)
        except Exception:
            decision = {
                "agent": "finish",
                "reason": "The orchestrator returned invalid JSON. Falling back to the current best result.",
                "state_updates": {},
                "final_response": state.get("draft_response") or state.get("last_agent_output") or "The orchestrator could not produce a valid routing decision.",
            }

        state_updates = decision.get("state_updates", {})
        if isinstance(state_updates, dict):
            state.update(state_updates)

        next_agent = decision.get("agent", "finish")
        reason = decision.get("reason", "No reason provided.")
        next_agent, reason = self._handle_unavailable_agent_choice(state, next_agent, reason)
        state["orchestrator_reason"] = reason

        if next_agent == "finish":
            state["next_agent"] = "__finish__"
            state["final_output"] = decision.get("final_response") or state.get("draft_response") or state.get("last_agent_output") or "No final response was generated."
            state = append_message(state, make_message("orchestrator_agent", "user", "final", state["final_output"]))
        else:
            state["next_agent"] = next_agent
            task_content = decision.get("task_content") or state_updates.get("current_objective") or state.get("current_objective") or state.get("user_query", "")
            state = append_task(
                state,
                make_task(
                    sender="orchestrator_agent",
                    recipient=next_agent,
                    intent=reason,
                    content=task_content,
                    state_updates=state_updates if isinstance(state_updates, dict) else {},
                ),
            )
        log_task_update("Orchestrator", f"Decision: {next_agent}. Reason: {reason}")
        return state

    def orchestrator_router(self, state: dict):
        return state.get("next_agent", "__finish__")

    def build_workflow(self):
        workflow = StateGraph(dict)
        workflow.add_node("orchestrator_agent", self.orchestrator_agent)
        for agent_name in self.registry.agents:
            workflow.add_node(agent_name, lambda state, name=agent_name: self._execute_agent(state, name))
        workflow.set_entry_point("orchestrator_agent")
        edge_map = {agent_name: agent_name for agent_name in self.registry.agents}
        edge_map["__finish__"] = END
        workflow.add_conditional_edges("orchestrator_agent", self.orchestrator_router, edge_map)
        for agent_name in self.registry.agents:
            workflow.add_edge(agent_name, "orchestrator_agent")
        return workflow.compile()

    def save_graph(self, app):
        try:
            png_data = app.get_graph().draw_mermaid_png()
            graph_path = resolve_output_path("graph.png")
            with open(graph_path, "wb") as f:
                f.write(png_data)
            log_task_update("System", f"Workflow graph saved to {graph_path}")
        except Exception as exc:
            logger.error(f"Failed to generate graph PNG: {exc}")

    def new_run_id(self) -> str:
        return f"run_{datetime.now(UTC).timestamp()}"

    def build_initial_state(self, user_query: str, **overrides) -> dict:
        initial_state = {
            "run_id": overrides.get("run_id", self.new_run_id()),
            "work_notes_file": overrides.get("work_notes_file", "agent_work_notes.txt"),
            "user_query": user_query,
            "current_objective": user_query,
            "plan": "",
            "draft_response": "",
            "review_reason": "",
            "review_decision": "",
            "review_target_agent": "",
            "review_corrected_values": {},
            "review_revised_objective": user_query,
            "review_step_assessments": [],
            "review_is_output_correct": False,
            "review_pending": False,
            "worker_calls": 0,
            "reviewer_calls": 0,
            "revision_count": 0,
            "orchestrator_calls": 0,
            "next_agent": "",
            "orchestrator_reason": "",
            "final_output": "",
            "agent_history": [],
            "max_steps": overrides.get("max_steps", 20),
            "research_target": "",
            "use_vector_memory": True,
        }
        initial_state.update(overrides)
        initial_state = self.apply_runtime_setup(initial_state)
        ensure_a2a_state(initial_state, initial_state.get("available_agent_cards") or self._agent_cards())
        return initial_state

    def invoke(self, initial_state: dict) -> dict:
        app = self.build_workflow()
        return app.invoke(initial_state)

    def run_query(self, user_query: str, *, state_overrides: dict | None = None, create_outputs: bool = True) -> dict:
        initialize_db()
        run_id = (state_overrides or {}).get("run_id", self.new_run_id())
        started_at = datetime.now(UTC).isoformat()
        run_output_dir = create_run_output_dir(run_id) if create_outputs else OUTPUT_DIR
        insert_run(run_id, user_query, started_at, "running")
        reset_text_file(
            "agent_work_notes.txt",
            f"Run ID: {run_id}\nStarted At: {started_at}\nUser Query: {user_query}\n{'=' * 72}\n\n",
        )
        initial_state = self.build_initial_state(user_query, run_id=run_id, run_output_dir=run_output_dir, **(state_overrides or {}))
        if not self._is_agent_available(initial_state, "worker_agent"):
            raise RuntimeError("Core LLM setup is incomplete. OPENAI_API_KEY is required before the agent system can run.")
        initial_state = append_message(initial_state, make_message("user", "orchestrator_agent", "request", user_query))
        record_work_note(initial_state, "user", "request", user_query)
        try:
            app = self.build_workflow()
            self.save_graph(app)
            result = app.invoke(initial_state)
            final_output = result.get("final_output") or result.get("draft_response", "")
            if create_outputs:
                write_text_file("final_output.txt", final_output)
            update_run(run_id, status="completed", completed_at=datetime.now(UTC).isoformat(), final_output=final_output)
            return result
        except Exception:
            update_run(run_id, status="failed", completed_at=datetime.now(UTC).isoformat(), final_output="workflow failed")
            raise
        finally:
            if create_outputs:
                set_active_output_dir(OUTPUT_DIR)
