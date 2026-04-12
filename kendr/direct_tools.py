from __future__ import annotations

import asyncio
import json
import os
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from kendr.llm_router import get_model_capabilities
from kendr.workflow_contract import approval_request_to_text, build_approval_request
from tasks.utils import agent_model_context, llm, log_task_update, normalize_llm_text, _client_for_model, model_for_agent


@dataclass(slots=True)
class DirectToolDefinition:
    tool_id: str
    kind: str
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def prompt_summary(self) -> str:
        schema_text = "{}"
        if self.input_schema:
            try:
                schema_text = json.dumps(self.input_schema, ensure_ascii=False, separators=(",", ":"))
            except Exception:
                schema_text = "{}"
        approval_note = " requires approval" if self.requires_approval else ""
        return (
            f"- `{self.tool_id}` ({self.kind}{approval_note}): {self.description}\n"
            f"  input_schema={schema_text}"
        )


@dataclass(slots=True)
class DirectToolExecution:
    ok: bool
    output: Any = None
    summary: str = ""
    error_code: str = ""
    error_message: str = ""
    awaiting_input: bool = False
    state_updates: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


_SUPPORTED_INTEGRATION_ACTIONS: dict[str, dict[str, dict[str, Any]]] = {
    "aws": {
        "list_s3_buckets": {
            "name": "List S3 Buckets",
            "description": "List accessible S3 buckets for the authorized AWS account.",
            "input_schema": {"type": "object", "properties": {}},
        },
        "describe_ec2": {
            "name": "Describe EC2 Instances",
            "description": "Describe EC2 instances in the authorized AWS account and region.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "region": {"type": "string", "description": "Optional AWS region override."},
                },
            },
        },
    },
    "gmail": {
        "read_inbox": {
            "name": "Read Gmail Inbox",
            "description": "Read recent Gmail inbox messages for the connected account.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
        },
        "search_emails": {
            "name": "Search Gmail",
            "description": "Search Gmail messages for the connected account using a Gmail query string.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": 50},
                },
                "required": ["query"],
            },
        },
    },
    "google_drive": {
        "list_files": {
            "name": "List Drive Files",
            "description": "List Google Drive files matching a query for the connected account.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "page_size": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
        },
    },
    "slack": {
        "list_channels": {
            "name": "List Slack Channels",
            "description": "List accessible Slack channels for the connected workspace.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
        },
        "read_messages": {
            "name": "Read Slack Messages",
            "description": "Read recent messages from a Slack channel by channel ID.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "required": ["channel"],
            },
        },
    },
    "microsoft_graph": {
        "list_files": {
            "name": "List OneDrive Files",
            "description": "List files from the connected Microsoft 365 OneDrive root.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                },
            },
        },
    },
    "github": {
        "get_repo": {
            "name": "Get GitHub Repository",
            "description": "Fetch repository metadata for a GitHub repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository slug in owner/repo form."},
                    "owner": {"type": "string"},
                    "name": {"type": "string", "description": "Repository name when owner is provided separately."},
                },
            },
        },
        "list_issues": {
            "name": "List GitHub Issues",
            "description": "List issues for a GitHub repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository slug in owner/repo form."},
                    "owner": {"type": "string"},
                    "name": {"type": "string"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"]},
                    "per_page": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
        },
        "get_issue": {
            "name": "Get GitHub Issue",
            "description": "Fetch a specific issue from a GitHub repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository slug in owner/repo form."},
                    "owner": {"type": "string"},
                    "name": {"type": "string"},
                    "number": {"type": "integer", "minimum": 1},
                },
                "required": ["number"],
            },
        },
        "list_pull_requests": {
            "name": "List GitHub Pull Requests",
            "description": "List pull requests for a GitHub repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository slug in owner/repo form."},
                    "owner": {"type": "string"},
                    "name": {"type": "string"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"]},
                },
            },
        },
        "get_pull_request": {
            "name": "Get GitHub Pull Request",
            "description": "Fetch a specific pull request from a GitHub repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository slug in owner/repo form."},
                    "owner": {"type": "string"},
                    "name": {"type": "string"},
                    "number": {"type": "integer", "minimum": 1},
                },
                "required": ["number"],
            },
        },
        "list_branches": {
            "name": "List GitHub Branches",
            "description": "List branches for a GitHub repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository slug in owner/repo form."},
                    "owner": {"type": "string"},
                    "name": {"type": "string"},
                },
            },
        },
        "clone_repo": {
            "name": "Clone GitHub Repository",
            "description": "Clone a GitHub repository into the working directory.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository slug in owner/repo form."},
                    "owner": {"type": "string"},
                    "name": {"type": "string"},
                    "to_dir": {"type": "string", "description": "Optional destination directory relative to the working directory."},
                    "depth": {"type": "integer", "minimum": 0},
                },
            },
            "requires_approval": True,
        },
        "current_branch": {
            "name": "Get Git Branch",
            "description": "Get the current branch for a local git repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo_dir": {"type": "string", "description": "Repository directory relative to the working directory."},
                },
                "required": ["repo_dir"],
            },
        },
        "diff": {
            "name": "Get Git Diff",
            "description": "Read the current diff for a local git repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo_dir": {"type": "string", "description": "Repository directory relative to the working directory."},
                },
                "required": ["repo_dir"],
            },
        },
        "read_repo_file": {
            "name": "Read Repository File",
            "description": "Read a file from a local git repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo_dir": {"type": "string", "description": "Repository directory relative to the working directory."},
                    "path": {"type": "string", "description": "File path relative to the repository root."},
                },
                "required": ["repo_dir", "path"],
            },
        },
        "write_repo_file": {
            "name": "Write Repository File",
            "description": "Write a file inside a local git repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo_dir": {"type": "string", "description": "Repository directory relative to the working directory."},
                    "path": {"type": "string", "description": "File path relative to the repository root."},
                    "content": {"type": "string"},
                },
                "required": ["repo_dir", "path", "content"],
            },
            "requires_approval": True,
        },
        "create_branch": {
            "name": "Create Git Branch",
            "description": "Create a new branch in a local git repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo_dir": {"type": "string"},
                    "branch": {"type": "string"},
                },
                "required": ["repo_dir", "branch"],
            },
            "requires_approval": True,
        },
        "switch_branch": {
            "name": "Switch Git Branch",
            "description": "Switch to a branch in a local git repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo_dir": {"type": "string"},
                    "branch": {"type": "string"},
                },
                "required": ["repo_dir", "branch"],
            },
            "requires_approval": True,
        },
        "commit": {
            "name": "Commit Git Changes",
            "description": "Commit local changes in a git repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo_dir": {"type": "string"},
                    "message": {"type": "string"},
                    "add_all": {"type": "boolean"},
                },
                "required": ["repo_dir", "message"],
            },
            "requires_approval": True,
        },
        "push": {
            "name": "Push Git Branch",
            "description": "Push a local branch to the remote repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo_dir": {"type": "string"},
                    "remote": {"type": "string"},
                    "branch": {"type": "string"},
                    "set_upstream": {"type": "boolean"},
                },
                "required": ["repo_dir"],
            },
            "requires_approval": True,
        },
        "add_comment": {
            "name": "Add GitHub Comment",
            "description": "Add a comment to a GitHub issue or pull request.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository slug in owner/repo form."},
                    "owner": {"type": "string"},
                    "name": {"type": "string"},
                    "number": {"type": "integer", "minimum": 1, "description": "Issue or pull request number."},
                    "body": {"type": "string"},
                },
                "required": ["number", "body"],
            },
            "requires_approval": True,
        },
        "create_pull_request": {
            "name": "Create GitHub Pull Request",
            "description": "Create a pull request on a GitHub repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository slug in owner/repo form."},
                    "owner": {"type": "string"},
                    "name": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"},
                    "head": {"type": "string", "description": "Source branch name."},
                    "base": {"type": "string", "description": "Target branch name."},
                },
                "required": ["title", "head"],
            },
            "requires_approval": True,
        },
        "merge_pull_request": {
            "name": "Merge GitHub Pull Request",
            "description": "Merge a pull request on a GitHub repository.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string", "description": "Repository slug in owner/repo form."},
                    "owner": {"type": "string"},
                    "name": {"type": "string"},
                    "number": {"type": "integer", "minimum": 1, "description": "Pull request number."},
                    "commit_title": {"type": "string"},
                    "merge_method": {"type": "string", "enum": ["merge", "squash", "rebase"]},
                },
                "required": ["number"],
            },
            "requires_approval": True,
        },
    },
}


def build_direct_tool_catalog(state: dict) -> list[DirectToolDefinition]:
    tools: list[DirectToolDefinition] = []
    seen: set[str] = set()

    try:
        from kendr.skill_manager import list_runtime_skills

        for row in list_runtime_skills():
            slug = str(row.get("slug", "") or "").strip()
            if not slug:
                continue
            tool_id = f"skill:{slug}"
            if tool_id in seen:
                continue
            seen.add(tool_id)
            metadata = row.get("metadata", {}) if isinstance(row.get("metadata"), dict) else {}
            permissions = metadata.get("permissions", {}) if isinstance(metadata.get("permissions"), dict) else {}
            tools.append(
                DirectToolDefinition(
                    tool_id=tool_id,
                    kind="skill",
                    name=str(row.get("name", slug) or slug),
                    description=str(row.get("description", "") or f"Skill `{slug}`").strip(),
                    input_schema=row.get("input_schema", {}) if isinstance(row.get("input_schema", {}), dict) else {},
                    requires_approval=bool(permissions.get("requires_approval", False)),
                    metadata={
                        "slug": slug,
                        "skill_type": str(row.get("skill_type", "") or "").strip(),
                        "category": str(row.get("category", "") or "").strip(),
                    },
                )
            )
    except Exception:
        pass

    if state.get("use_mcp") is not False:
        try:
            from kendr.mcp_manager import list_servers

            for server in list_servers():
                if not server.get("enabled", True):
                    continue
                server_id = str(server.get("id", "") or "").strip()
                server_name = str(server.get("name", server_id or "mcp") or "").strip()
                server_tools = server.get("tools", []) if isinstance(server.get("tools", []), list) else []
                for tool in server_tools:
                    tool_name = str(tool.get("name", "") or "").strip()
                    if not tool_name:
                        continue
                    tool_id = f"mcp:{server_id}:{tool_name}"
                    if tool_id in seen:
                        continue
                    seen.add(tool_id)
                    raw_schema = tool.get("schema", {}) if isinstance(tool.get("schema", {}), dict) else {}
                    tools.append(
                        DirectToolDefinition(
                            tool_id=tool_id,
                            kind="mcp",
                            name=tool_name,
                            description=str(tool.get("description", "") or f"MCP tool `{tool_name}` from `{server_name}`").strip(),
                            input_schema=raw_schema,
                            requires_approval=False,
                            metadata={
                                "server_id": server_id,
                                "server_name": server_name,
                                "tool_name": tool_name,
                                "connection": str(server.get("connection", "") or "").strip(),
                                "server_type": str(server.get("type", "http") or "http").strip(),
                                "auth_token": str(server.get("auth_token", "") or "").strip(),
                            },
                        )
                    )
        except Exception:
            pass

    tools.extend(_build_integration_tools(state, seen))

    return tools


def _build_integration_tools(state: dict, seen: set[str]) -> list[DirectToolDefinition]:
    tools: list[DirectToolDefinition] = []
    try:
        from kendr.integration_registry import get_integration
    except Exception:
        return tools

    for integration_id, actions in _SUPPORTED_INTEGRATION_ACTIONS.items():
        card = get_integration(integration_id)
        if card is None:
            continue
        if not _integration_runtime_available(integration_id, card):
            continue
        for action_name, config in actions.items():
            tool_id = f"integration:{integration_id}:{action_name}"
            if tool_id in seen:
                continue
            seen.add(tool_id)
            tools.append(
                DirectToolDefinition(
                    tool_id=tool_id,
                    kind="integration",
                    name=str(config.get("name", action_name) or action_name),
                    description=str(config.get("description", "") or f"{card.name}: {action_name}").strip(),
                    input_schema=config.get("input_schema", {}) if isinstance(config.get("input_schema", {}), dict) else {},
                    requires_approval=bool(config.get("requires_approval", False)),
                    metadata={
                        "integration_id": integration_id,
                        "action": action_name,
                        "integration_name": card.name,
                        "category": card.category,
                    },
                )
            )
    return tools


def _integration_runtime_available(integration_id: str, card: Any) -> bool:
    if integration_id == "gmail":
        try:
            from kendr.providers import get_google_access_token

            return bool(get_google_access_token())
        except Exception:
            return False
    if integration_id == "google_drive":
        try:
            from kendr.providers import get_google_access_token

            return bool(get_google_access_token())
        except Exception:
            return False
    if integration_id == "slack":
        try:
            from kendr.providers import get_slack_bot_token

            return bool(get_slack_bot_token())
        except Exception:
            return False
    if integration_id == "microsoft_graph":
        try:
            from kendr.providers import get_microsoft_graph_access_token

            return bool(get_microsoft_graph_access_token())
        except Exception:
            return False
    if integration_id == "aws":
        return bool(os.getenv("AWS_ACCESS_KEY_ID", "").strip() and os.getenv("AWS_SECRET_ACCESS_KEY", "").strip())
    if integration_id == "github":
        return bool(os.getenv("GITHUB_TOKEN", "").strip())
    return bool(getattr(card, "is_configured", False))


def _tool_lookup(tools: list[DirectToolDefinition]) -> dict[str, DirectToolDefinition]:
    return {tool.tool_id: tool for tool in tools}


def _stringify_output(value: Any, *, limit: int = 5000) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            text = str(value)
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 15] + "\n... [truncated]"


def _strip_code_fences(text: str) -> str:
    stripped = str(text or "").strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def _parse_direct_tool_decision(raw_output: str) -> dict[str, Any]:
    parsed = json.loads(_strip_code_fences(raw_output))
    if not isinstance(parsed, dict):
        raise ValueError("Direct tool loop must return a JSON object.")
    return parsed


def _tool_to_native_schema(tool: DirectToolDefinition) -> dict[str, Any]:
    properties = tool.input_schema if isinstance(tool.input_schema, dict) else {}
    schema_type = str(properties.get("type", "") or "").strip() if properties else ""
    parameters = properties if schema_type == "object" else {
        "type": "object",
        "properties": {},
    }
    if "type" not in parameters:
        parameters = {"type": "object", **parameters}
    return {
        "type": "function",
        "function": {
            "name": tool.tool_id,
            "description": tool.description,
            "parameters": parameters,
        },
    }


def _native_tool_calling_supported(state: dict) -> bool:
    model = model_for_agent("orchestrator_agent")
    capabilities = get_model_capabilities(model)
    if not capabilities.get("tool_calling", False):
        return False
    try:
        client = _client_for_model(model, "general")
    except Exception:
        return False
    return hasattr(client, "bind_tools")


def _native_tool_system_prompt(*, state: dict, tools: list[DirectToolDefinition]) -> str:
    current_objective = str(state.get("current_objective") or state.get("user_query") or "").strip()
    tool_lines = "\n".join(tool.prompt_summary() for tool in tools) or "- none"
    return f"""
You are the direct tool router for a multi-agent runtime.

Current objective:
{current_objective}

Available tools:
{tool_lines}

Rules:
- Call tools only when they are the best direct surface for the request.
- Use exact arguments; do not invent fields outside the tool schema.
- If a tool result fully answers the task, provide the final answer directly.
- If the listed tools are not the right surface, reply with a short final answer beginning with `FALLBACK:` and explain why broader orchestration is needed.
""".strip()


def _extract_native_tool_calls(response: Any) -> list[dict[str, Any]]:
    raw_calls = getattr(response, "tool_calls", None)
    if isinstance(raw_calls, list):
        normalized: list[dict[str, Any]] = []
        for item in raw_calls:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or "").strip()
            if not name:
                continue
            args = item.get("args", {})
            if not isinstance(args, dict):
                args = {}
            normalized.append(
                {
                    "id": str(item.get("id", "") or "").strip(),
                    "name": name,
                    "args": args,
                }
            )
        return normalized
    additional = getattr(response, "additional_kwargs", {}) or {}
    maybe_calls = additional.get("tool_calls")
    normalized = []
    if isinstance(maybe_calls, list):
        for item in maybe_calls:
            if not isinstance(item, dict):
                continue
            function = item.get("function", {}) if isinstance(item.get("function"), dict) else {}
            name = str(function.get("name", "") or item.get("name", "") or "").strip()
            if not name:
                continue
            raw_args = function.get("arguments", {})
            args: dict[str, Any]
            if isinstance(raw_args, str):
                try:
                    parsed_args = json.loads(raw_args)
                    args = parsed_args if isinstance(parsed_args, dict) else {}
                except Exception:
                    args = {}
            elif isinstance(raw_args, dict):
                args = raw_args
            else:
                args = {}
            normalized.append(
                {
                    "id": str(item.get("id", "") or "").strip(),
                    "name": name,
                    "args": args,
                }
            )
    return normalized


def _run_native_direct_tool_loop(state: dict, *, tools: list[DirectToolDefinition], tool_map: dict[str, DirectToolDefinition], max_rounds: int) -> dict[str, Any]:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    model = model_for_agent("orchestrator_agent")
    client = _client_for_model(model, "general")
    tool_client = client.bind_tools([_tool_to_native_schema(tool) for tool in tools])
    history: list[dict[str, Any]] = []
    state.setdefault("direct_tool_trace", [])
    messages: list[Any] = [
        SystemMessage(content=_native_tool_system_prompt(state=state, tools=tools)),
        HumanMessage(content=str(state.get("current_objective") or state.get("user_query") or "").strip()),
    ]

    for round_index in range(1, max_rounds + 1):
        with agent_model_context("orchestrator_agent"):
            response = tool_client.invoke(messages)
        tool_calls = _extract_native_tool_calls(response)
        if not tool_calls:
            text = normalize_llm_text(getattr(response, "content", response))
            if str(text or "").strip().upper().startswith("FALLBACK:"):
                return {"status": "fallback", "reason": str(text).strip()[9:].strip() or "Native tool router requested fallback."}
            if str(text or "").strip():
                return {
                    "status": "final",
                    "response": str(text).strip(),
                    "trace": history,
                }
            return {"status": "fallback", "reason": "Native tool router returned no tool calls and no final response."}

        messages.append(response if isinstance(response, AIMessage) else AIMessage(content="", tool_calls=tool_calls))

        for call in tool_calls:
            tool_id = str(call.get("name", "") or "").strip()
            tool = tool_map.get(tool_id)
            if tool is None:
                history.append(
                    {
                        "round": round_index,
                        "action": "error",
                        "tool_id": tool_id,
                        "reason": f"Unknown tool_id `{tool_id}`.",
                    }
                )
                continue

            arguments = call.get("args", {})
            if not isinstance(arguments, dict):
                arguments = {}

            log_task_update("Direct Tools", f"Calling {tool_id}", json.dumps(arguments, ensure_ascii=False))
            execution = execute_direct_tool(state, tool, arguments)
            if execution.state_updates:
                state.update(execution.state_updates)

            event = {
                "round": round_index,
                "action": "call_tool",
                "tool_id": tool_id,
                "arguments": arguments,
                "ok": bool(getattr(execution, "ok", False)),
                "summary": str(getattr(execution, "summary", "") or "").strip(),
                "error_code": str(getattr(execution, "error_code", "") or "").strip(),
            }
            history.append(event)
            state["direct_tool_trace"] = list(history)

            if execution.awaiting_input:
                return {
                    "status": "awaiting_input",
                    "response": execution.summary or str(state.get("pending_user_question", "") or "").strip(),
                    "trace": history,
                }

            tool_message = ToolMessage(
                content=_stringify_output(execution.output if execution.output is not None else execution.summary),
                tool_call_id=str(call.get("id", "") or tool_id),
                name=tool_id,
            )
            messages.append(tool_message)

    return {
        "status": "fallback",
        "reason": "Native direct tool loop exhausted without reaching a final answer.",
        "trace": history,
    }


def _direct_tool_prompt(
    *,
    state: dict,
    tools: list[DirectToolDefinition],
    history: list[dict[str, Any]],
    round_index: int,
) -> str:
    working_directory = str(state.get("working_directory", "") or "").strip()
    current_objective = str(state.get("current_objective") or state.get("user_query") or "").strip()
    tool_lines = "\n".join(tool.prompt_summary() for tool in tools) or "- none"
    history_text = json.dumps(history, indent=2, ensure_ascii=False) if history else "[]"

    return f"""
You are the direct tool router for a multi-agent runtime.

Your job is to decide whether to:
1. call exactly one available tool,
2. return the final answer, or
3. fall back to the broader agent/workflow orchestrator.

Current objective:
{current_objective}

Execution context:
- working_directory: {working_directory or "."}
- round: {round_index}

Available tools:
{tool_lines}

Previous direct tool history:
{history_text}

Rules:
- Use only tool IDs from the available tools list.
- If one listed tool can directly help, choose `call_tool`.
- If the available tools are not the right surface for the task, choose `fallback`.
- After a tool result is available, either call another tool or produce `final`.
- Do not invent tool IDs or arguments outside the listed schema.
- For `skill:shell-command`, provide an exact command string in `arguments.command`.
- Prefer concise, deterministic tool arguments.

Return ONLY valid JSON in this schema:
{{
  "action": "call_tool" | "final" | "fallback",
  "tool_id": "required only when action=call_tool",
  "arguments": {{}},
  "reason": "short reason",
  "response": "required only when action=final"
}}
""".strip()


def _execute_skill_tool(state: dict, tool: DirectToolDefinition, arguments: dict[str, Any]) -> DirectToolExecution:
    from kendr.skill_manager import execute_skill_by_slug

    slug = str(tool.metadata.get("slug", "") or "").strip()
    result = execute_skill_by_slug(
        slug,
        dict(arguments or {}),
        session_id=str(state.get("session_id", "") or ""),
    )
    if result.get("error_type") == "approval_required":
        state_updates = {
            "awaiting_user_input": True,
            "pending_user_input_kind": str(result.get("pending_user_input_kind", "") or "skill_approval").strip(),
            "approval_pending_scope": str(result.get("approval_pending_scope", "") or f"skill_permission:{slug}").strip(),
            "approval_request": result.get("approval_request", {}) if isinstance(result.get("approval_request"), dict) else {},
            "pending_user_question": str(result.get("pending_user_question", "") or "").strip(),
            "direct_tool_last_result": {
                "tool_id": tool.tool_id,
                "status": "approval_required",
                "summary": str(result.get("pending_user_question", "") or "").strip(),
            },
        }
        return DirectToolExecution(
            ok=False,
            output=result,
            summary=str(result.get("pending_user_question", "") or f"Approval required to run {tool.tool_id}.").strip(),
            error_code="approval_required",
            error_message=str(result.get("error", "") or "approval_required").strip(),
            awaiting_input=True,
            state_updates=state_updates,
        )

    if result.get("success"):
        output = result.get("output")
        summary = _stringify_output(output if output is not None else result.get("stdout", ""))
        return DirectToolExecution(
            ok=True,
            output=output if output is not None else result,
            summary=summary,
            state_updates={
                "direct_tool_last_result": {
                    "tool_id": tool.tool_id,
                    "status": "ok",
                    "summary": summary,
                }
            },
        )

    error_message = str(result.get("error", "") or "Skill execution failed.").strip()
    return DirectToolExecution(
        ok=False,
        output=result,
        summary=error_message,
        error_code="skill_error",
        error_message=error_message,
        state_updates={
            "direct_tool_last_result": {
                "tool_id": tool.tool_id,
                "status": "error",
                "summary": error_message,
            }
        },
    )


def _execute_mcp_tool(state: dict, tool: DirectToolDefinition, arguments: dict[str, Any]) -> DirectToolExecution:
    connection = str(tool.metadata.get("connection", "") or "").strip()
    server_type = str(tool.metadata.get("server_type", "http") or "http").strip()
    tool_name = str(tool.metadata.get("tool_name", "") or tool.name).strip()
    auth_token = str(tool.metadata.get("auth_token", "") or "").strip()

    if not connection or not tool_name:
        return DirectToolExecution(
            ok=False,
            summary="MCP tool metadata is incomplete.",
            error_code="mcp_metadata_incomplete",
            error_message="Missing MCP connection or tool name.",
        )

    try:
        from fastmcp import Client as MCPClient
    except ImportError:
        return DirectToolExecution(
            ok=False,
            summary="fastmcp is not installed.",
            error_code="fastmcp_missing",
            error_message="fastmcp is not installed.",
        )

    async def _call() -> Any:
        client_kwargs: dict[str, Any] = {}
        if server_type == "stdio":
            from fastmcp.client.transports.stdio import StdioTransport

            try:
                parts = shlex.split(connection)
            except Exception:
                parts = connection.split()
            if not parts:
                parts = [connection]
            transport: Any = StdioTransport(command=parts[0], args=parts[1:])
        else:
            transport = connection
            if auth_token:
                client_kwargs["headers"] = {"Authorization": f"Bearer {auth_token}"}
        async with MCPClient(transport, timeout=30, **client_kwargs) as client:
            return await client.call_tool(tool_name, dict(arguments or {}))

    try:
        result = asyncio.run(_call())
    except Exception as exc:
        error_message = str(exc).strip() or "MCP tool execution failed."
        return DirectToolExecution(
            ok=False,
            summary=error_message,
            error_code="mcp_error",
            error_message=error_message,
            state_updates={
                "direct_tool_last_result": {
                    "tool_id": tool.tool_id,
                    "status": "error",
                    "summary": error_message,
                }
            },
        )

    if hasattr(result, "content"):
        parts = result.content
        values = parts if isinstance(parts, list) else [parts]
        text = "\n".join(getattr(item, "text", str(item)) for item in values)
        output: Any = text
    else:
        output = str(result)
    summary = _stringify_output(output)
    return DirectToolExecution(
        ok=True,
        output=output,
        summary=summary,
        state_updates={
            "direct_tool_last_result": {
                "tool_id": tool.tool_id,
                "status": "ok",
                "summary": summary,
            }
        },
    )


def _approval_required_execution(
    *,
    tool: DirectToolDefinition,
    scope: str,
    title: str,
    summary: str,
    sections: list[dict[str, Any]] | None = None,
) -> DirectToolExecution:
    request = build_approval_request(
        scope=scope,
        title=title,
        summary=summary,
        sections=sections or [],
        accept_label="Approve",
        reject_label="Reject",
        suggest_label="Suggest",
    )
    question = approval_request_to_text(request) or summary
    return DirectToolExecution(
        ok=False,
        output={"approval_request": request},
        summary=question,
        error_code="approval_required",
        error_message=summary,
        awaiting_input=True,
        state_updates={
            "awaiting_user_input": True,
            "pending_user_input_kind": "integration_approval",
            "approval_pending_scope": scope,
            "approval_request": request,
            "pending_user_question": question,
            "direct_tool_last_result": {
                "tool_id": tool.tool_id,
                "status": "approval_required",
                "summary": summary,
            },
        },
    )


def _require_integration_access(state: dict, tool: DirectToolDefinition, integration_id: str) -> DirectToolExecution | None:
    if integration_id in {"gmail", "google_drive", "slack", "microsoft_graph"} and not state.get("communication_authorized", False):
        return _approval_required_execution(
            tool=tool,
            scope="integration_communication_access",
            title="Communication Access Approval",
            summary="Approve read access to the connected communication and productivity integrations for this run.",
            sections=[
                {
                    "title": "Requested access",
                    "items": [
                        "Read data from the connected provider",
                        f"Tool: {tool.tool_id}",
                    ],
                }
            ],
        )
    if integration_id == "aws" and not state.get("aws_authorized", False):
        return _approval_required_execution(
            tool=tool,
            scope="integration_aws_access",
            title="AWS Access Approval",
            summary="Approve AWS account access for this run before calling direct AWS tools.",
            sections=[
                {
                    "title": "Requested access",
                    "items": [
                        "Use configured AWS credentials",
                        f"Tool: {tool.tool_id}",
                    ],
                }
            ],
        )
    if integration_id == "github":
        action = str(tool.metadata.get("action", "") or "").strip()
        api_write_actions = {"add_comment", "create_pull_request", "merge_pull_request"}
        local_write_actions = {"write_repo_file", "create_branch", "switch_branch", "commit"}
        remote_git_actions = {"clone_repo", "push"}
        if action in api_write_actions and not state.get("github_write_authorized", False):
            return _approval_required_execution(
                tool=tool,
                scope="integration_github_write_access",
                title="GitHub Write Access Approval",
                summary="Approve write access for direct GitHub actions in this run.",
                sections=[
                    {
                        "title": "Requested access",
                        "items": [
                            "Post comments, create pull requests, or merge pull requests on GitHub",
                            f"Tool: {tool.tool_id}",
                        ],
                    }
                ],
            )
        if action in local_write_actions and not state.get("github_local_git_authorized", False):
            return _approval_required_execution(
                tool=tool,
                scope="integration_github_local_git_access",
                title="Local Git Mutation Approval",
                summary="Approve local repository mutations for direct git actions in this run.",
                sections=[
                    {
                        "title": "Requested access",
                        "items": [
                            "Modify files or branch state inside local git repositories under the working directory",
                            f"Tool: {tool.tool_id}",
                        ],
                    }
                ],
            )
        if action in remote_git_actions and not state.get("github_remote_git_authorized", False):
            return _approval_required_execution(
                tool=tool,
                scope="integration_github_remote_git_access",
                title="Remote Git Network Approval",
                summary="Approve remote git network operations for direct GitHub tools in this run.",
                sections=[
                    {
                        "title": "Requested access",
                        "items": [
                            "Clone from or push to remote GitHub repositories",
                            f"Tool: {tool.tool_id}",
                        ],
                    }
                ],
            )
    return None


def _coerce_positive_int(value: Any, *, default: int, minimum: int = 1, maximum: int = 100) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


def _resolve_github_repo_target(state: dict, arguments: dict[str, Any]) -> tuple[str, str]:
    owner = str(arguments.get("owner", "") or state.get("github_owner", "") or "").strip()
    name = str(arguments.get("name", "") or "").strip()
    repo_value = str(arguments.get("repo", "") or state.get("github_repo", "") or "").strip()

    if repo_value and "/" in repo_value:
        parts = repo_value.split("/", 1)
        owner = owner or parts[0].strip()
        name = name or parts[1].strip()
    elif repo_value and not name:
        name = repo_value

    return owner, name


def _resolve_working_directory(state: dict) -> str:
    working_directory = str(state.get("working_directory", "") or "").strip()
    if working_directory:
        return str(Path(working_directory).expanduser().resolve())
    return str(Path.cwd().resolve())


def _resolve_path_within_root(root: str, raw_path: str, *, default_name: str = "") -> "Path":
    from pathlib import Path

    base = Path(root).expanduser().resolve()
    candidate_raw = str(raw_path or default_name or "").strip()
    if not candidate_raw:
        candidate = base
    else:
        candidate_path = Path(candidate_raw).expanduser()
        candidate = candidate_path.resolve() if candidate_path.is_absolute() else (base / candidate_path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise PermissionError(f"Path `{candidate}` is outside the working directory root `{base}`.") from exc
    return candidate


def _execute_aws_integration(state: dict, tool: DirectToolDefinition, action: str, arguments: dict[str, Any]) -> DirectToolExecution:
    from tasks.aws_tasks import _execute_allowed_operation, _get_boto3_session

    exec_state = dict(state)
    region = str(arguments.get("region", "") or "").strip()
    if region:
        exec_state["aws_region"] = region
    session = _get_boto3_session(exec_state)

    if action == "list_s3_buckets":
        response = _execute_allowed_operation(session, "s3", "list_buckets", {}, exec_state) or {}
        buckets = []
        for bucket in response.get("Buckets", []) if isinstance(response, dict) else []:
            if not isinstance(bucket, dict):
                continue
            buckets.append(
                {
                    "name": bucket.get("Name"),
                    "creation_date": bucket.get("CreationDate"),
                }
            )
        output: Any = {"buckets": buckets}
    elif action == "describe_ec2":
        response = _execute_allowed_operation(session, "ec2", "describe_instances", {}, exec_state) or {}
        instances: list[dict[str, Any]] = []
        reservations = response.get("Reservations", []) if isinstance(response, dict) else []
        for reservation in reservations:
            if not isinstance(reservation, dict):
                continue
            for instance in reservation.get("Instances", []) or []:
                if not isinstance(instance, dict):
                    continue
                instances.append(
                    {
                        "instance_id": instance.get("InstanceId"),
                        "state": ((instance.get("State") or {}).get("Name") if isinstance(instance.get("State"), dict) else ""),
                        "type": instance.get("InstanceType"),
                        "private_ip": instance.get("PrivateIpAddress"),
                        "launch_time": instance.get("LaunchTime"),
                    }
                )
        output = {"instances": instances, "region": exec_state.get("aws_region", "")}
    else:
        return DirectToolExecution(
            ok=False,
            summary=f"Unsupported AWS integration action: {action}",
            error_code="unsupported_integration_action",
            error_message=f"Unsupported AWS integration action: {action}",
        )

    summary = _stringify_output(output)
    return DirectToolExecution(
        ok=True,
        output=output,
        summary=summary,
        state_updates={"direct_tool_last_result": {"tool_id": tool.tool_id, "status": "ok", "summary": summary}},
    )


def _execute_communication_integration(
    state: dict,
    tool: DirectToolDefinition,
    integration_id: str,
    action: str,
    arguments: dict[str, Any],
) -> DirectToolExecution:
    from kendr.providers import get_google_access_token, get_microsoft_graph_access_token, get_slack_bot_token
    from tasks.communication_tasks import _http_json

    if integration_id == "gmail":
        access_token = get_google_access_token()
        if not access_token:
            raise ValueError("No Google access token is available for Gmail.")
        headers = {"Authorization": f"Bearer {access_token}"}
        max_results = _coerce_positive_int(arguments.get("max_results"), default=10, maximum=50)
        query = "in:inbox" if action == "read_inbox" else str(arguments.get("query", "") or "").strip()
        if action == "search_emails" and not query:
            raise ValueError("integration:gmail:search_emails requires `query`.")
        list_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages?" + urlencode(
            {"q": query, "maxResults": max_results}
        )
        listing = _http_json(list_url, headers=headers)
        messages = []
        for item in listing.get("messages", [])[:max_results]:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            msg = _http_json(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{item['id']}?format=metadata&metadataHeaders=Subject&metadataHeaders=From&metadataHeaders=Date",
                headers=headers,
            )
            headers_map = {
                str(header.get("name", "")).lower(): header.get("value", "")
                for header in msg.get("payload", {}).get("headers", [])
                if isinstance(header, dict)
            }
            messages.append(
                {
                    "id": msg.get("id"),
                    "thread_id": msg.get("threadId"),
                    "snippet": msg.get("snippet", ""),
                    "subject": headers_map.get("subject", ""),
                    "from": headers_map.get("from", ""),
                    "date": headers_map.get("date", ""),
                    "label_ids": msg.get("labelIds", []),
                }
            )
        output: Any = {"query": query, "messages": messages}
    elif integration_id == "google_drive":
        access_token = get_google_access_token()
        if not access_token:
            raise ValueError("No Google access token is available for Drive.")
        headers = {"Authorization": f"Bearer {access_token}"}
        query = str(arguments.get("query", "") or "starred = true").strip()
        page_size = _coerce_positive_int(arguments.get("page_size"), default=10, maximum=50)
        url = "https://www.googleapis.com/drive/v3/files?" + urlencode(
            {
                "q": query,
                "pageSize": page_size,
                "fields": "files(id,name,mimeType,modifiedTime,owners(displayName),webViewLink)",
            }
        )
        listing = _http_json(url, headers=headers)
        output = {"query": query, "files": listing.get("files", [])}
    elif integration_id == "slack":
        token = get_slack_bot_token()
        if not token:
            raise ValueError("No Slack bot token is available.")
        headers = {"Authorization": f"Bearer {token}"}
        if action == "list_channels":
            limit = _coerce_positive_int(arguments.get("limit"), default=20, maximum=100)
            payload = _http_json(
                "https://slack.com/api/conversations.list?" + urlencode({"limit": limit}),
                headers=headers,
            )
            output = {"channels": payload.get("channels", [])[:limit]}
        elif action == "read_messages":
            channel = str(arguments.get("channel", "") or "").strip()
            if not channel:
                raise ValueError("integration:slack:read_messages requires `channel`.")
            limit = _coerce_positive_int(arguments.get("limit"), default=20, maximum=100)
            payload = _http_json(
                "https://slack.com/api/conversations.history?" + urlencode({"channel": channel, "limit": limit}),
                headers=headers,
            )
            output = {"channel": channel, "messages": payload.get("messages", [])[:limit]}
        else:
            raise ValueError(f"Unsupported Slack integration action: {action}")
    elif integration_id == "microsoft_graph":
        access_token = get_microsoft_graph_access_token()
        if not access_token:
            raise ValueError("No Microsoft Graph access token is available.")
        headers = {"Authorization": f"Bearer {access_token}"}
        limit = _coerce_positive_int(arguments.get("limit"), default=10, maximum=50)
        output = _http_json(
            f"https://graph.microsoft.com/v1.0/me/drive/root/children?$top={limit}",
            headers=headers,
        )
    else:
        raise ValueError(f"Unsupported communication integration: {integration_id}")

    summary = _stringify_output(output)
    return DirectToolExecution(
        ok=True,
        output=output,
        summary=summary,
        state_updates={"direct_tool_last_result": {"tool_id": tool.tool_id, "status": "ok", "summary": summary}},
    )


def _execute_github_integration(state: dict, tool: DirectToolDefinition, action: str, arguments: dict[str, Any]) -> DirectToolExecution:
    from tasks.github_client import GitHubClient

    client = GitHubClient(token=str(state.get("github_token", "") or os.getenv("GITHUB_TOKEN", "")).strip())
    working_root = _resolve_working_directory(state)

    def _require_repo_target() -> tuple[str, str]:
        owner_value, repo_value = _resolve_github_repo_target(state, arguments)
        if not owner_value or not repo_value:
            raise ValueError(
                "GitHub direct tools require a repository target in `owner/repo` form or separate `owner` and `name` fields."
            )
        return owner_value, repo_value

    def _require_repo_dir() -> "Path":
        from pathlib import Path

        repo_dir_raw = str(arguments.get("repo_dir", "") or "").strip()
        if not repo_dir_raw:
            raise ValueError("This GitHub local-repo tool requires `repo_dir`.")
        repo_dir = _resolve_path_within_root(working_root, repo_dir_raw)
        if not repo_dir.exists():
            raise FileNotFoundError(f"Repository directory does not exist: {repo_dir}")
        return Path(repo_dir)

    try:
        if action == "get_repo":
            owner, repo = _require_repo_target()
            output: Any = client.get_repo(owner, repo)
        elif action == "list_issues":
            owner, repo = _require_repo_target()
            issue_state = str(arguments.get("state", "") or "open").strip() or "open"
            per_page = _coerce_positive_int(arguments.get("per_page"), default=30, maximum=100)
            output = client.list_issues(owner, repo, state=issue_state, per_page=per_page)
        elif action == "get_issue":
            owner, repo = _require_repo_target()
            number = _coerce_positive_int(arguments.get("number"), default=0)
            if number < 1:
                raise ValueError("integration:github:get_issue requires `number`.")
            output = client.get_issue(owner, repo, number)
        elif action == "list_pull_requests":
            owner, repo = _require_repo_target()
            pr_state = str(arguments.get("state", "") or "open").strip() or "open"
            output = client.list_pull_requests(owner, repo, state=pr_state)
        elif action == "get_pull_request":
            owner, repo = _require_repo_target()
            number = _coerce_positive_int(arguments.get("number"), default=0)
            if number < 1:
                raise ValueError("integration:github:get_pull_request requires `number`.")
            output = client.get_pull_request(owner, repo, number)
        elif action == "list_branches":
            owner, repo = _require_repo_target()
            output = client.list_branches(owner, repo)
        elif action == "clone_repo":
            from pathlib import Path

            owner, repo = _require_repo_target()
            to_dir_raw = str(arguments.get("to_dir", "") or "").strip()
            destination = _resolve_path_within_root(working_root, to_dir_raw, default_name=repo)
            depth = max(0, int(arguments.get("depth", 0) or 0))
            output_path = client.clone_repo_authenticated(owner, repo, Path(destination), depth=depth)
            output = {"repo_dir": str(output_path), "owner": owner, "repo": repo, "depth": depth}
        elif action == "current_branch":
            repo_dir = _require_repo_dir()
            output = {"repo_dir": str(repo_dir), "branch": client.current_branch(repo_dir)}
        elif action == "diff":
            repo_dir = _require_repo_dir()
            output = {"repo_dir": str(repo_dir), "diff": client.diff(repo_dir)}
        elif action == "read_repo_file":
            repo_dir = _require_repo_dir()
            relative_path = str(arguments.get("path", "") or "").strip()
            if not relative_path:
                raise ValueError("integration:github:read_repo_file requires `path`.")
            output = {
                "repo_dir": str(repo_dir),
                "path": relative_path,
                "content": client.read_repo_file(repo_dir, relative_path),
            }
        elif action == "write_repo_file":
            repo_dir = _require_repo_dir()
            relative_path = str(arguments.get("path", "") or "").strip()
            if not relative_path:
                raise ValueError("integration:github:write_repo_file requires `path`.")
            content = str(arguments.get("content", "") or "")
            client.write_repo_file(repo_dir, relative_path, content)
            output = {"repo_dir": str(repo_dir), "path": relative_path, "written": True}
        elif action == "create_branch":
            repo_dir = _require_repo_dir()
            branch = str(arguments.get("branch", "") or "").strip()
            if not branch:
                raise ValueError("integration:github:create_branch requires `branch`.")
            output = {"repo_dir": str(repo_dir), "result": client.create_branch(repo_dir, branch), "branch": branch}
        elif action == "switch_branch":
            repo_dir = _require_repo_dir()
            branch = str(arguments.get("branch", "") or "").strip()
            if not branch:
                raise ValueError("integration:github:switch_branch requires `branch`.")
            output = {"repo_dir": str(repo_dir), "result": client.switch_branch(repo_dir, branch), "branch": branch}
        elif action == "commit":
            repo_dir = _require_repo_dir()
            message = str(arguments.get("message", "") or "").strip()
            if not message:
                raise ValueError("integration:github:commit requires `message`.")
            add_all = bool(arguments.get("add_all", True))
            output = {
                "repo_dir": str(repo_dir),
                "result": client.commit(repo_dir, message, add_all=add_all),
                "message": message,
            }
        elif action == "push":
            repo_dir = _require_repo_dir()
            remote = str(arguments.get("remote", "") or "origin").strip() or "origin"
            branch = str(arguments.get("branch", "") or "").strip()
            set_upstream = bool(arguments.get("set_upstream", False))
            if set_upstream:
                if not branch:
                    branch = client.current_branch(repo_dir)
                output = {
                    "repo_dir": str(repo_dir),
                    "result": client.push_set_upstream(repo_dir, branch, remote=remote),
                    "remote": remote,
                    "branch": branch,
                    "set_upstream": True,
                }
            else:
                output = {
                    "repo_dir": str(repo_dir),
                    "result": client.push(repo_dir, remote=remote, branch=branch),
                    "remote": remote,
                    "branch": branch,
                    "set_upstream": False,
                }
        elif action == "add_comment":
            owner, repo = _require_repo_target()
            number = _coerce_positive_int(arguments.get("number"), default=0)
            body = str(arguments.get("body", "") or "").strip()
            if number < 1:
                raise ValueError("integration:github:add_comment requires `number`.")
            if not body:
                raise ValueError("integration:github:add_comment requires `body`.")
            output = client.add_comment(owner, repo, number, body)
        elif action == "create_pull_request":
            owner, repo = _require_repo_target()
            title = str(arguments.get("title", "") or "").strip()
            head = str(arguments.get("head", "") or "").strip()
            body = str(arguments.get("body", "") or "").strip()
            base = str(arguments.get("base", "") or "main").strip() or "main"
            if not title:
                raise ValueError("integration:github:create_pull_request requires `title`.")
            if not head:
                raise ValueError("integration:github:create_pull_request requires `head`.")
            output = client.create_pull_request(owner, repo, title, body, head, base)
        elif action == "merge_pull_request":
            owner, repo = _require_repo_target()
            number = _coerce_positive_int(arguments.get("number"), default=0)
            commit_title = str(arguments.get("commit_title", "") or "").strip()
            merge_method = str(arguments.get("merge_method", "") or "merge").strip() or "merge"
            if number < 1:
                raise ValueError("integration:github:merge_pull_request requires `number`.")
            output = client.merge_pull_request(owner, repo, number, commit_title, merge_method)
        else:
            raise ValueError(f"Unsupported GitHub integration action: {action}")
    except ValueError as exc:
        error_message = str(exc).strip() or "GitHub integration execution failed."
        error_code = "missing_github_repo" if "repository target" in error_message.lower() else "integration_error"
        return DirectToolExecution(
            ok=False,
            summary=error_message,
            error_code=error_code,
            error_message=error_message,
            state_updates={
                "direct_tool_last_result": {
                    "tool_id": tool.tool_id,
                    "status": "error",
                    "summary": error_message,
                }
            },
        )
    except Exception as exc:
        error_message = str(exc).strip() or "GitHub integration execution failed."
        return DirectToolExecution(
            ok=False,
            summary=error_message,
            error_code="integration_error",
            error_message=error_message,
            state_updates={
                "direct_tool_last_result": {
                    "tool_id": tool.tool_id,
                    "status": "error",
                    "summary": error_message,
                }
            },
        )

    summary = _stringify_output(output)
    return DirectToolExecution(
        ok=True,
        output=output,
        summary=summary,
        state_updates={"direct_tool_last_result": {"tool_id": tool.tool_id, "status": "ok", "summary": summary}},
    )


def _execute_integration_tool(state: dict, tool: DirectToolDefinition, arguments: dict[str, Any]) -> DirectToolExecution:
    integration_id = str(tool.metadata.get("integration_id", "") or "").strip()
    action = str(tool.metadata.get("action", "") or "").strip()
    gate = _require_integration_access(state, tool, integration_id)
    if gate is not None:
        return gate

    try:
        if integration_id == "aws":
            return _execute_aws_integration(state, tool, action, arguments)
        if integration_id in {"gmail", "google_drive", "slack", "microsoft_graph"}:
            return _execute_communication_integration(state, tool, integration_id, action, arguments)
        if integration_id == "github":
            return _execute_github_integration(state, tool, action, arguments)
    except Exception as exc:
        error_message = str(exc).strip() or "Integration tool execution failed."
        return DirectToolExecution(
            ok=False,
            summary=error_message,
            error_code="integration_error",
            error_message=error_message,
            state_updates={
                "direct_tool_last_result": {
                    "tool_id": tool.tool_id,
                    "status": "error",
                    "summary": error_message,
                }
            },
        )

    return DirectToolExecution(
        ok=False,
        summary=f"Unsupported direct integration action: {tool.tool_id}",
        error_code="unsupported_integration_action",
        error_message=f"Unsupported direct integration action: {tool.tool_id}",
    )


def execute_direct_tool(state: dict, tool: DirectToolDefinition, arguments: dict[str, Any]) -> DirectToolExecution:
    if tool.kind == "skill":
        return _execute_skill_tool(state, tool, arguments)
    if tool.kind == "mcp":
        return _execute_mcp_tool(state, tool, arguments)
    if tool.kind == "integration":
        return _execute_integration_tool(state, tool, arguments)
    return DirectToolExecution(
        ok=False,
        summary=f"Unsupported direct tool kind: {tool.kind}",
        error_code="unsupported_tool_kind",
        error_message=f"Unsupported direct tool kind: {tool.kind}",
    )


def run_direct_tool_loop(
    state: dict,
    *,
    max_rounds: int = 4,
) -> dict[str, Any]:
    tools = build_direct_tool_catalog(state)
    if not tools:
        return {"status": "fallback", "reason": "No direct tools are available."}

    tool_map = _tool_lookup(tools)
    if _native_tool_calling_supported(state):
        try:
            result = _run_native_direct_tool_loop(state, tools=tools, tool_map=tool_map, max_rounds=max_rounds)
            if str(result.get("status", "") or "").strip().lower() != "fallback":
                return result
        except Exception as exc:
            state["direct_tool_native_fallback_reason"] = f"{type(exc).__name__}: {exc}"

    history: list[dict[str, Any]] = []
    state.setdefault("direct_tool_trace", [])

    for round_index in range(1, max_rounds + 1):
        prompt = _direct_tool_prompt(state=state, tools=tools, history=history, round_index=round_index)
        try:
            with agent_model_context("orchestrator_agent"):
                response = llm.invoke(prompt)
        except Exception as exc:
            return {
                "status": "fallback",
                "reason": f"Direct tool router LLM call failed: {type(exc).__name__}: {exc}",
            }

        raw_output = normalize_llm_text(response.content if hasattr(response, "content") else response)
        try:
            decision = _parse_direct_tool_decision(raw_output)
        except Exception as exc:
            return {"status": "fallback", "reason": f"Direct tool router returned invalid JSON: {exc}"}

        action = str(decision.get("action", "") or "").strip().lower()
        reason = str(decision.get("reason", "") or "").strip()
        if action == "fallback":
            return {"status": "fallback", "reason": reason or "Direct tool router requested orchestrator fallback."}
        if action == "final":
            response_text = str(decision.get("response", "") or "").strip()
            if response_text:
                return {
                    "status": "final",
                    "response": response_text,
                    "trace": history,
                }
            return {"status": "fallback", "reason": "Direct tool router returned an empty final response."}
        if action != "call_tool":
            return {"status": "fallback", "reason": f"Unsupported direct tool action: {action or '<empty>'}"}

        tool_id = str(decision.get("tool_id", "") or "").strip()
        tool = tool_map.get(tool_id)
        if tool is None:
            history.append(
                {
                    "round": round_index,
                    "action": "error",
                    "tool_id": tool_id,
                    "reason": f"Unknown tool_id `{tool_id}`.",
                }
            )
            continue

        arguments = decision.get("arguments", {})
        if not isinstance(arguments, dict):
            history.append(
                {
                    "round": round_index,
                    "action": "error",
                    "tool_id": tool_id,
                    "reason": "Tool arguments must be a JSON object.",
                }
            )
            continue

        log_task_update("Direct Tools", f"Calling {tool_id}", json.dumps(arguments, ensure_ascii=False))
        execution = execute_direct_tool(state, tool, arguments)
        if execution.state_updates:
            state.update(execution.state_updates)

        event = {
            "round": round_index,
            "action": "call_tool",
            "tool_id": tool_id,
            "reason": reason,
            "arguments": arguments,
            "ok": bool(getattr(execution, "ok", False)),
            "summary": str(getattr(execution, "summary", "") or "").strip(),
            "error_code": str(getattr(execution, "error_code", "") or "").strip(),
        }
        history.append(event)
        state["direct_tool_trace"] = list(history)

        if execution.awaiting_input:
            return {
                "status": "awaiting_input",
                "response": execution.summary or str(state.get("pending_user_question", "") or "").strip(),
                "trace": history,
            }

    if history:
        return {
            "status": "fallback",
            "reason": "Direct tool loop exhausted without reaching a final answer.",
            "trace": history,
        }
    return {"status": "fallback", "reason": "Direct tool loop did not execute any tools."}
