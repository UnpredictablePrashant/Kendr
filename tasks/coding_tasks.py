import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

from tasks.a2a_agent_utils import begin_agent_session, publish_agent_output
from tasks.utils import OUTPUT_DIR, log_task_update, resolve_output_path, write_text_file


RESPONSES_API_URL = "https://api.openai.com/v1/responses"
DEFAULT_CODEX_MODEL = os.getenv("OPENAI_CODEX_MODEL", "gpt-5.3-codex")
DEFAULT_REASONING_EFFORT = os.getenv("OPENAI_CODEX_REASONING_EFFORT", "medium")


def _read_context_files(file_paths: list[str], working_directory: Path) -> tuple[str, list[str]]:
    sections = []
    missing_files = []

    for raw_path in file_paths:
        path = Path(raw_path)
        if not path.is_absolute():
            path = working_directory / path

        if not path.exists():
            missing_files.append(str(path))
            continue

        sections.append(f"File: {path}\n---\n{path.read_text(encoding='utf-8')}\n---")

    return "\n\n".join(sections), missing_files


def _build_coding_prompt(
    task: str,
    language: str,
    extra_instructions: str,
    target_write_path: str | None,
    context_blob: str,
    missing_files: list[str],
) -> str:
    write_instruction = (
        f"Return the full replacement file contents for this path: {target_write_path}."
        if target_write_path
        else "Return the code artifact directly. Do not assume any file write unless told."
    )
    missing_context = "\n".join(missing_files) if missing_files else "None"

    return f"""
You are the coding agent in a multi-agent ecosystem.

Write production-ready code for the requested task. Keep non-code text minimal.
{write_instruction}
Do not wrap the code in markdown fences.

Return EXACTLY in this format:
SUMMARY: one-line summary
LANGUAGE: {language or "best-fit"}
CODE:
full code here

Task:
{task}

Additional instructions:
{extra_instructions or "None"}

Missing context files:
{missing_context}

Relevant context:
{context_blob or "No file context provided."}
""".strip()


def _extract_output_text(payload: dict) -> str:
    if payload.get("output_text"):
        return payload["output_text"]

    chunks = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def _parse_coding_response(raw_output: str) -> tuple[str, str, str]:
    summary = "Generated code."
    language = "text"
    code = raw_output.strip()

    if "CODE:" not in raw_output:
        return summary, language, _strip_code_fences(code)

    code_lines = []
    in_code = False

    for line in raw_output.splitlines():
        if in_code:
            code_lines.append(line)
            continue

        if line.startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip() or summary
        elif line.startswith("LANGUAGE:"):
            language = line.split(":", 1)[1].strip() or language
        elif line.startswith("CODE:"):
            in_code = True
            remainder = line.split(":", 1)[1].lstrip()
            if remainder:
                code_lines.append(remainder)

    code = "\n".join(code_lines).strip()
    return summary, language, _strip_code_fences(code)


def _strip_code_fences(code: str) -> str:
    stripped = code.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        inner = stripped.splitlines()
        if len(inner) >= 2:
            return "\n".join(inner[1:-1]).strip()
    return stripped


def _call_codex_cli(prompt: str, model: str, working_directory: Path, timeout_seconds: int) -> str:
    temp_output_path = Path(resolve_output_path("coding_agent_codex_cli_last_message.txt"))
    command = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--cd",
        str(working_directory),
        "--output-last-message",
        str(temp_output_path),
        "-m",
        model,
        prompt,
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "codex exec failed")
    return temp_output_path.read_text(encoding="utf-8").strip()


def _call_openai_sdk(prompt: str, model: str, reasoning_effort: str, api_key: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input=prompt,
        reasoning={"effort": reasoning_effort},
    )
    raw_text = getattr(response, "output_text", None)
    if raw_text:
        return raw_text.strip()
    return _extract_output_text(response.model_dump())


def _call_responses_http(prompt: str, model: str, reasoning_effort: str, api_key: str, timeout_seconds: int) -> str:
    request_body = json.dumps(
        {
            "model": model,
            "input": prompt,
            "reasoning": {"effort": reasoning_effort},
        }
    ).encode("utf-8")
    request = Request(
        RESPONSES_API_URL,
        data=request_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return _extract_output_text(payload)


def _resolve_backend(preferred_backend: str, api_key: str | None) -> list[str]:
    if preferred_backend != "auto":
        return [preferred_backend]

    backends = []
    if shutil.which("codex"):
        backends.append("codex-cli")
    if api_key:
        backends.extend(["openai-sdk", "responses-http"])
    return backends


def coding_agent(state):
    active_task, task_content, _ = begin_agent_session(state, "coding_agent")
    state["coding_agent_calls"] = state.get("coding_agent_calls", 0) + 1
    call_number = state["coding_agent_calls"]

    task = state.get("coding_task") or task_content or state.get("current_objective") or state.get("user_query", "").strip()
    if not task:
        raise ValueError("coding_agent requires 'coding_task' or 'user_query' in state.")

    working_directory = Path(state.get("coding_working_directory", ".")).resolve()
    target_write_path = state.get("coding_write_path")
    context_files = state.get("coding_context_files", [])
    language = state.get("coding_language", "best-fit")
    extra_instructions = state.get("coding_instructions", "")
    preferred_backend = state.get("coding_backend", "auto")
    model = state.get("coding_model", DEFAULT_CODEX_MODEL)
    reasoning_effort = state.get("coding_reasoning_effort", DEFAULT_REASONING_EFFORT)
    timeout_seconds = int(state.get("coding_timeout", 90))
    api_key = os.getenv("OPENAI_API_KEY")

    log_task_update("Coding Agent", f"Generation pass #{call_number} started.")
    log_task_update(
        "Coding Agent",
        f"Preparing coding prompt with backend preference '{preferred_backend}' and model '{model}'.",
        task,
    )

    context_blob, missing_files = _read_context_files(context_files, working_directory)
    prompt = _build_coding_prompt(
        task=task,
        language=language,
        extra_instructions=extra_instructions,
        target_write_path=target_write_path,
        context_blob=context_blob,
        missing_files=missing_files,
    )

    backend_errors = []
    raw_output = ""
    backend_used = None

    for backend in _resolve_backend(preferred_backend, api_key):
        try:
            if backend == "codex-cli":
                raw_output = _call_codex_cli(prompt, model, working_directory, timeout_seconds)
            elif backend == "openai-sdk":
                raw_output = _call_openai_sdk(prompt, model, reasoning_effort, api_key or "")
            elif backend == "responses-http":
                raw_output = _call_responses_http(prompt, model, reasoning_effort, api_key or "", timeout_seconds)
            else:
                raise ValueError(f"Unsupported coding backend: {backend}")
            backend_used = backend
            break
        except Exception as exc:
            backend_errors.append(f"{backend}: {exc}")

    if not backend_used:
        raise RuntimeError("coding_agent could not generate code.\n" + "\n".join(backend_errors))

    summary, detected_language, code = _parse_coding_response(raw_output)
    state["coding_summary"] = summary
    state["coding_language"] = detected_language
    state["coding_code"] = code
    state["coding_model"] = model
    state["coding_backend_used"] = backend_used
    state["coding_raw_output"] = raw_output

    raw_filename = f"coding_agent_raw_{call_number}.txt"
    code_filename = f"coding_agent_code_{call_number}.txt"
    report_filename = f"coding_agent_output_{call_number}.txt"

    write_text_file(raw_filename, raw_output)
    write_text_file(code_filename, code)

    written_path = None
    if target_write_path:
        written_path = Path(target_write_path)
        if not written_path.is_absolute():
            written_path = working_directory / written_path
        written_path.parent.mkdir(parents=True, exist_ok=True)
        written_path.write_text(code, encoding="utf-8")
        state["coding_written_path"] = str(written_path)

    report_lines = [
        f"Backend: {backend_used}",
        f"Model: {model}",
        f"Reasoning effort: {reasoning_effort}",
        f"Summary: {summary}",
        f"Language: {detected_language}",
        f"Target write path: {written_path or 'none'}",
        f"Context files: {', '.join(context_files) if context_files else 'none'}",
        f"Missing context files: {', '.join(missing_files) if missing_files else 'none'}",
        "",
        "Generated Code:",
        code,
    ]
    report = "\n".join(report_lines).strip()

    write_text_file(report_filename, report)

    state["draft_response"] = report
    log_task_update(
        "Coding Agent",
        f"Code generation finished with backend '{backend_used}'. Saved artifacts to {OUTPUT_DIR}/{report_filename}.",
        report,
    )
    state = publish_agent_output(
        state,
        "coding_agent",
        report,
        f"coding_result_{call_number}",
        recipients=["orchestrator_agent", "worker_agent"],
    )
    return state
