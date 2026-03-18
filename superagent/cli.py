from __future__ import annotations

import argparse
import json
import os

from .discovery import build_registry
from .runtime import AgentRuntime


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="superagent", description="Plugin-driven multi-agent runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the orchestrator for a single query.")
    run_parser.add_argument("query", nargs="*", help="User query to process.")
    run_parser.add_argument("--max-steps", type=int, default=20, help="Maximum orchestration steps.")
    run_parser.add_argument("--json", action="store_true", help="Emit the final state as JSON.")

    agent_list = subparsers.add_parser("agents", help="List or inspect discovered agents.")
    agent_list.add_argument("action", choices=["list", "show"])
    agent_list.add_argument("name", nargs="?")
    agent_list.add_argument("--json", action="store_true")

    plugin_list = subparsers.add_parser("plugins", help="List discovered plugins.")
    plugin_list.add_argument("action", choices=["list"])
    plugin_list.add_argument("--json", action="store_true")

    subparsers.add_parser("gateway", help="Run the HTTP gateway server.")
    subparsers.add_parser("web", help="Alias for gateway server.")
    subparsers.add_parser("setup-ui", help="Run the OAuth/setup UI.")
    daemon_parser = subparsers.add_parser("daemon", help="Run the always-on monitor and heartbeat loop.")
    daemon_parser.add_argument(
        "--poll-interval",
        type=int,
        default=int(os.getenv("DAEMON_POLL_INTERVAL", "30")),
        help="Main daemon poll interval in seconds.",
    )
    daemon_parser.add_argument(
        "--heartbeat-interval",
        type=int,
        default=int(os.getenv("DAEMON_HEARTBEAT_INTERVAL", "300")),
        help="Heartbeat interval in seconds.",
    )
    daemon_parser.add_argument("--once", action="store_true", help="Run one monitor pass and exit.")
    return parser


def _cmd_run(args: argparse.Namespace) -> int:
    query = " ".join(args.query).strip() or input("Enter your query: ").strip()
    registry = build_registry()
    runtime = AgentRuntime(registry)
    result = runtime.run_query(query, state_overrides={"max_steps": args.max_steps})
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(result.get("final_output") or result.get("draft_response", ""))
    return 0


def _cmd_agents(args: argparse.Namespace) -> int:
    registry = build_registry()
    if args.action == "list":
        payload = [
            {
                "name": agent.name,
                "description": agent.description,
                "plugin": agent.plugin_name,
                "skills": agent.skills,
            }
            for agent in registry.agents.values()
        ]
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            for item in payload:
                print(f"{item['name']}: {item['description']} [{item['plugin']}]")
        return 0

    if not args.name:
        raise SystemExit("agents show requires an agent name")
    agent = registry.agents.get(args.name)
    if not agent:
        raise SystemExit(f"Unknown agent: {args.name}")
    payload = {
        "name": agent.name,
        "description": agent.description,
        "plugin": agent.plugin_name,
        "skills": agent.skills,
        "input_keys": agent.input_keys,
        "output_keys": agent.output_keys,
        "requirements": agent.requirements,
        "metadata": agent.metadata,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _cmd_plugins(args: argparse.Namespace) -> int:
    registry = build_registry()
    payload = [
        {
            "name": plugin.name,
            "source": plugin.source,
            "description": plugin.description,
            "version": plugin.version,
            "kind": plugin.kind,
        }
        for plugin in registry.plugins.values()
    ]
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        for item in payload:
            print(f"{item['name']}: {item['description']} [{item['kind']}]")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        return _cmd_run(args)
    if args.command == "agents":
        return _cmd_agents(args)
    if args.command == "plugins":
        return _cmd_plugins(args)
    if args.command in {"gateway", "web"}:
        from gateway_server import main as gateway_main

        gateway_main()
        return 0
    if args.command == "setup-ui":
        from setup_ui import main as setup_main

        setup_main()
        return 0
    if args.command == "daemon":
        from .daemon import run_daemon

        return run_daemon(
            poll_interval_seconds=args.poll_interval,
            heartbeat_interval_seconds=args.heartbeat_interval,
            once=args.once,
        )
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
