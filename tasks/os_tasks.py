import os
import platform
import shutil
import subprocess

from tasks.a2a_agent_utils import begin_agent_session, publish_agent_output
from tasks.utils import OUTPUT_DIR, llm, log_task_update, write_text_file


def _detect_host_os() -> str:
    system_name = platform.system().lower()
    if "windows" in system_name:
        return "windows"
    if "darwin" in system_name:
        return "macos"
    if "linux" in system_name:
        return "linux"
    return system_name or "unknown"


def _resolve_shell(target_os: str, requested_shell: str | None = None) -> tuple[str | None, list[str], str]:
    shell_candidates = []

    if requested_shell:
        shell_candidates.append(requested_shell)
    elif target_os == "windows":
        shell_candidates.extend(["powershell", "pwsh", "cmd"])
    else:
        shell_candidates.extend(["bash", "sh"])

    for candidate in shell_candidates:
        shell_path = shutil.which(candidate)
        if not shell_path and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            shell_path = candidate
        if shell_path:
            shell_name = os.path.basename(shell_path).lower()
            if shell_name in {"powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
                return shell_path, ["-Command"], shell_name
            if shell_name in {"cmd", "cmd.exe"}:
                return shell_path, ["/C"], shell_name
            return shell_path, ["-lc"], shell_name

    return None, [], requested_shell or target_os


def _build_command_from_request(user_query: str, target_os: str) -> tuple[str, str, str, int]:
    prompt = f"""
    You are the OS execution agent in a multi-agent system.

    Convert the user's request into exactly one command for the target operating system.
    Keep the reasoning short and operational. Do not add markdown fences.

    Target OS: {target_os}
    User request: {user_query}

    Return EXACTLY in this format:
    Thought: short execution summary
    Command: one command only
    WorkingDirectory: . or absolute path
    TimeoutSeconds: integer
    """
    response = llm.invoke(prompt)
    raw_output = response.content.strip() if hasattr(response, "content") else str(response).strip()

    thought = "Generated a command from the user request."
    command = ""
    working_directory = "."
    timeout_seconds = 120

    for line in raw_output.splitlines():
        if line.lower().startswith("thought:"):
            thought = line.split(":", 1)[1].strip() or thought
        elif line.lower().startswith("command:"):
            command = line.split(":", 1)[1].strip()
        elif line.lower().startswith("workingdirectory:"):
            working_directory = line.split(":", 1)[1].strip() or "."
        elif line.lower().startswith("timeoutseconds:"):
            timeout_value = line.split(":", 1)[1].strip()
            if timeout_value.isdigit():
                timeout_seconds = int(timeout_value)

    if not command:
        raise ValueError("OS agent could not derive a command from the model output.")

    return thought, command, working_directory, timeout_seconds


def _format_execution_report(
    host_os: str,
    target_os: str,
    shell_name: str,
    command: str,
    working_directory: str,
    timeout_seconds: int,
    completed: subprocess.CompletedProcess[str] | None = None,
    error_message: str | None = None,
) -> str:
    stdout = ""
    stderr = ""
    return_code = "not-run"

    if completed is not None:
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        return_code = str(completed.returncode)

    lines = [
        f"Host OS: {host_os}",
        f"Target OS: {target_os}",
        f"Shell: {shell_name}",
        f"Working directory: {working_directory}",
        f"Timeout seconds: {timeout_seconds}",
        f"Command: {command}",
        f"Return code: {return_code}",
        "",
        "STDOUT:",
        stdout or "<empty>",
        "",
        "STDERR:",
        stderr or "<empty>",
    ]

    if error_message:
        lines.extend(["", f"Error: {error_message}"])

    return "\n".join(lines)


def os_agent(state):
    active_task, task_content, _ = begin_agent_session(state, "os_agent")
    state["os_agent_calls"] = state.get("os_agent_calls", 0) + 1

    host_os = _detect_host_os()
    target_os = (state.get("target_os") or host_os).lower()
    requested_shell = state.get("shell")
    explicit_command = state.get("os_command")
    timeout_seconds = int(state.get("os_timeout", 120))
    working_directory = state.get("os_working_directory", ".")

    log_task_update(
        "OS Agent",
        f"Execution pass #{state['os_agent_calls']} started on host OS '{host_os}' targeting '{target_os}'.",
    )

    if explicit_command:
        thought = "Using the explicit command provided in state."
        command = explicit_command
    else:
        thought, command, working_directory, timeout_seconds = _build_command_from_request(
            task_content or state.get("current_objective") or state["user_query"],
            target_os,
        )

    shell_path, shell_args, shell_name = _resolve_shell(target_os, requested_shell)
    if not shell_path:
        error_message = f"No supported shell was found for target OS '{target_os}'."
        report = _format_execution_report(
            host_os,
            target_os,
            requested_shell or "unavailable",
            command,
            working_directory,
            timeout_seconds,
            error_message=error_message,
        )
        state["os_result"] = report
        state["os_success"] = False
        state["os_return_code"] = None
        write_text_file(f"os_agent_output_{state['os_agent_calls']}.txt", report)
        log_task_update("OS Agent", error_message, report)
        return state

    resolved_working_directory = os.path.abspath(working_directory)
    log_task_update("OS Agent", thought)
    log_task_update(
        "OS Agent",
        f"Running command with shell '{shell_name}' in '{resolved_working_directory}'.",
        command,
    )

    try:
        completed = subprocess.run(
            [shell_path, *shell_args, command],
            capture_output=True,
            text=True,
            cwd=resolved_working_directory,
            timeout=timeout_seconds,
            check=False,
        )
        report = _format_execution_report(
            host_os,
            target_os,
            shell_name,
            command,
            resolved_working_directory,
            timeout_seconds,
            completed=completed,
        )
        state["os_success"] = completed.returncode == 0
        state["os_return_code"] = completed.returncode
    except Exception as exc:
        completed = None
        report = _format_execution_report(
            host_os,
            target_os,
            shell_name,
            command,
            resolved_working_directory,
            timeout_seconds,
            error_message=str(exc),
        )
        state["os_success"] = False
        state["os_return_code"] = None

    state["os_command"] = command
    state["os_shell"] = shell_name
    state["os_host"] = host_os
    state["os_target"] = target_os
    state["os_result"] = report
    state["draft_response"] = report

    output_name = f"os_agent_output_{state['os_agent_calls']}.txt"
    write_text_file(output_name, report)
    log_task_update("OS Agent", f"Execution report saved to {OUTPUT_DIR}/{output_name}", report)
    state = publish_agent_output(
        state,
        "os_agent",
        report,
        f"os_agent_result_{state['os_agent_calls']}",
        recipients=["orchestrator_agent", "worker_agent"],
    )
    return state
