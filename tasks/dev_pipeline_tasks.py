"""
dev_pipeline_tasks.py — Multi-agent dev project pipeline orchestrator.

Provides `dev_pipeline_agent(state)` which orchestrates the complete
end-to-end project generation flow in a single agent call:

  blueprint → [approval gate] → scaffold → db → auth → backend →
  frontend → deps → [tests] → security_scan → [devops] → verify →
  [auto-fix loop ×3] → post_setup → zip export

Activated when state["dev_pipeline_mode"] is True.
Intended for `kendr run --dev "…"` or `kendr generate "…"`.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
import zipfile
from pathlib import Path
from typing import Callable

from tasks.a2a_agent_utils import begin_agent_session, publish_agent_output
from tasks.utils import log_task_update, write_text_file

_AGENT_NAME = "dev_pipeline_agent"

AGENT_METADATA = {
    "dev_pipeline_agent": {
        "name": _AGENT_NAME,
        "display_name": "Dev Pipeline Agent",
        "description": (
            "End-to-end multi-agent software project generation pipeline. "
            "Orchestrates blueprint → scaffold → build → test → verify → zip export."
        ),
        "skills": [
            "project generation",
            "full-stack development",
            "pipeline orchestration",
            "blueprint design",
            "scaffolding",
            "testing",
            "devops",
            "zip export",
        ],
        "input_keys": [
            "user_query",
            "project_build_mode",
            "dev_pipeline_mode",
            "project_name",
            "project_root",
            "project_stack",
            "auto_approve",
            "skip_test_agent",
            "skip_devops_agent",
            "skip_reviews",
            "dev_pipeline_max_fix_rounds",
        ],
        "output_keys": [
            "blueprint_json",
            "blueprint_status",
            "dev_pipeline_zip_path",
            "dev_pipeline_status",
            "dev_pipeline_stages_completed",
            "dev_pipeline_error",
        ],
    }
}


def _print_banner(message: str, width: int = 72) -> None:
    bar = "─" * width
    sys.stdout.write(f"\n{bar}\n  {message}\n{bar}\n")
    sys.stdout.flush()


def _ask_approval(prompt: str, auto_approve: bool) -> bool:
    """Return True if approved. Blocks for interactive y/n unless auto_approve."""
    if auto_approve:
        log_task_update("DevPipeline", "Auto-approved: " + prompt[:120])
        return True
    sys.stdout.write(f"\n{prompt}\n\nApprove? [y/N]: ")
    sys.stdout.flush()
    try:
        answer = sys.stdin.readline().strip().lower()
    except (EOFError, OSError):
        answer = ""
    return answer in ("y", "yes", "approve", "ok")


def _run_stage(
    name: str,
    agent_fn: Callable[[dict], dict],
    state: dict,
    stages_completed: list[str],
) -> dict:
    """Run a single pipeline stage, updating state and tracking completions."""
    _print_banner(f"[{name}] starting…")
    t0 = time.monotonic()
    try:
        state = agent_fn(state)
        elapsed = time.monotonic() - t0
        stages_completed.append(name)
        log_task_update("DevPipeline", f"Stage '{name}' completed in {elapsed:.1f}s.")
        _print_banner(f"[{name}] done ({elapsed:.1f}s)")
    except Exception as exc:
        elapsed = time.monotonic() - t0
        log_task_update("DevPipeline", f"Stage '{name}' failed after {elapsed:.1f}s: {exc}")
        _print_banner(f"[{name}] FAILED — {exc}")
        raise
    return state


def _zip_project(project_root: Path, output_path: Path) -> str:
    """Create a zip archive of the generated project. Returns zip path string."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for item in sorted(project_root.rglob("*")):
            if item.is_file():
                arcname = item.relative_to(project_root.parent)
                skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", "dist", "build"}
                if any(part in skip_dirs for part in arcname.parts):
                    continue
                try:
                    zf.write(str(item), str(arcname))
                except Exception:
                    pass
    return str(output_path)


def dev_pipeline_agent(state: dict) -> dict:
    """
    End-to-end project generation pipeline agent.

    Runs synchronously through all build stages in sequence. Activates when
    state["dev_pipeline_mode"] is True. Provides an interactive blueprint
    approval gate (skipped when auto_approve=True) and an auto-fix retry loop
    (up to dev_pipeline_max_fix_rounds, default 3) using coding_agent when the
    verifier reports failures.
    """
    active_task, task_content, _ = begin_agent_session(state, _AGENT_NAME)
    state["dev_pipeline_agent_calls"] = state.get("dev_pipeline_agent_calls", 0) + 1

    auto_approve: bool = bool(state.get("auto_approve") or state.get("auto_approve_blueprint"))
    skip_tests: bool = bool(state.get("skip_test_agent", False))
    skip_devops: bool = bool(state.get("skip_devops_agent", False))
    max_fix_rounds: int = int(state.get("dev_pipeline_max_fix_rounds", 3) or 3)

    stages_completed: list[str] = []
    state["dev_pipeline_stages_completed"] = stages_completed
    state["dev_pipeline_status"] = "running"
    state["dev_pipeline_error"] = ""

    _print_banner("Kendr Dev Pipeline — starting full project generation")

    # ── Lazy imports (avoid circular imports at module load time) ──────────────
    try:
        from tasks.project_blueprint_tasks import project_blueprint_agent
        from tasks.project_scaffold_tasks import project_scaffold_agent
        from tasks.database_architect_tasks import database_architect_agent
        from tasks.auth_security_tasks import auth_security_agent
        from tasks.backend_builder_tasks import backend_builder_agent
        from tasks.frontend_builder_tasks import frontend_builder_agent
        from tasks.dependency_manager_tasks import dependency_manager_agent
        from tasks.test_tasks import test_agent
        from tasks.security_scanner_tasks import security_scanner_agent
        from tasks.devops_tasks import devops_agent
        from tasks.project_verifier_tasks import project_verifier_agent
        from tasks.coding_tasks import coding_agent
        from tasks.post_setup_tasks import post_setup_agent
    except ImportError as exc:
        state["dev_pipeline_status"] = "error"
        state["dev_pipeline_error"] = f"Import error: {exc}"
        log_task_update("DevPipeline", f"Import failure: {exc}")
        return state

    # ── Stage 1: Blueprint ─────────────────────────────────────────────────────
    try:
        state = _run_stage("blueprint", project_blueprint_agent, state, stages_completed)
    except Exception as exc:
        state["dev_pipeline_status"] = "error"
        state["dev_pipeline_error"] = f"Blueprint stage failed: {exc}"
        return state

    # ── Blueprint approval gate ────────────────────────────────────────────────
    blueprint_md = state.get("draft_response", "")
    blueprint_status = str(state.get("blueprint_status", "draft"))
    if blueprint_status != "approved":
        if not _ask_approval(
            f"Blueprint generated.\n\n{blueprint_md[:2000]}\n\n"
            "Project will be created at: " + str(state.get("project_root", "(working dir)")),
            auto_approve,
        ):
            state["dev_pipeline_status"] = "cancelled"
            state["dev_pipeline_error"] = "Blueprint rejected by user."
            log_task_update("DevPipeline", "User rejected blueprint. Pipeline cancelled.")
            _print_banner("Pipeline cancelled — blueprint not approved.")
            return state
        state["blueprint_status"] = "approved"
        state["blueprint_waiting_for_approval"] = False
        log_task_update("DevPipeline", "Blueprint approved — continuing to build.")

    # ── Stage 2: Scaffold ──────────────────────────────────────────────────────
    try:
        state = _run_stage("scaffold", project_scaffold_agent, state, stages_completed)
    except Exception as exc:
        state["dev_pipeline_status"] = "error"
        state["dev_pipeline_error"] = f"Scaffold stage failed: {exc}"
        return state

    # ── Stage 3: Database architect ────────────────────────────────────────────
    try:
        state = _run_stage("database", database_architect_agent, state, stages_completed)
    except Exception as exc:
        log_task_update("DevPipeline", f"Database stage failed (non-fatal): {exc}")

    # ── Stage 4: Auth & security helpers ──────────────────────────────────────
    blueprint = state.get("blueprint_json") or {}
    auth_type = str((blueprint.get("tech_stack") or {}).get("auth", "")).lower()
    if auth_type and auth_type not in ("none", "no", ""):
        try:
            state = _run_stage("auth", auth_security_agent, state, stages_completed)
        except Exception as exc:
            log_task_update("DevPipeline", f"Auth stage failed (non-fatal): {exc}")

    # ── Stage 5: Backend ───────────────────────────────────────────────────────
    try:
        state = _run_stage("backend", backend_builder_agent, state, stages_completed)
    except Exception as exc:
        log_task_update("DevPipeline", f"Backend stage failed (non-fatal): {exc}")

    # ── Stage 6: Frontend ──────────────────────────────────────────────────────
    has_frontend = bool((blueprint.get("frontend_components") or blueprint.get("frontend", {}) or {}) if blueprint else {})
    if has_frontend:
        try:
            state = _run_stage("frontend", frontend_builder_agent, state, stages_completed)
        except Exception as exc:
            log_task_update("DevPipeline", f"Frontend stage failed (non-fatal): {exc}")

    # ── Stage 7: Dependency manager ────────────────────────────────────────────
    try:
        state = _run_stage("deps", dependency_manager_agent, state, stages_completed)
    except Exception as exc:
        log_task_update("DevPipeline", f"Deps stage failed (non-fatal): {exc}")

    # ── Stage 8: Tests ────────────────────────────────────────────────────────
    if not skip_tests:
        try:
            state = _run_stage("tests", test_agent, state, stages_completed)
        except Exception as exc:
            log_task_update("DevPipeline", f"Test stage failed (non-fatal): {exc}")

    # ── Stage 9: Security scanner ─────────────────────────────────────────────
    try:
        state = _run_stage("security_scan", security_scanner_agent, state, stages_completed)
    except Exception as exc:
        log_task_update("DevPipeline", f"Security scan failed (non-fatal): {exc}")

    # ── Stage 10: DevOps ──────────────────────────────────────────────────────
    if not skip_devops:
        try:
            state = _run_stage("devops", devops_agent, state, stages_completed)
        except Exception as exc:
            log_task_update("DevPipeline", f"DevOps stage failed (non-fatal): {exc}")

    # ── Stage 11: Verify + auto-fix retry loop ────────────────────────────────
    verifier_passed = False
    for fix_round in range(max_fix_rounds + 1):
        try:
            state = _run_stage(
                f"verify{'_fix_' + str(fix_round) if fix_round > 0 else ''}",
                project_verifier_agent,
                state,
                stages_completed,
            )
        except Exception as exc:
            log_task_update("DevPipeline", f"Verifier failed on round {fix_round}: {exc}")

        verifier_status = str(state.get("project_verifier_status", "")).lower()
        verifier_passed = verifier_status in ("pass", "passed", "ok", "success", "")
        if verifier_passed:
            log_task_update("DevPipeline", f"Verifier passed on round {fix_round}.")
            break

        if fix_round < max_fix_rounds:
            verifier_output = str(state.get("project_verifier_output", "") or state.get("draft_response", ""))
            fix_prompt = (
                f"Fix the following project verification failures (attempt {fix_round + 1}/{max_fix_rounds}):\n\n"
                f"{verifier_output[:3000]}"
            )
            log_task_update("DevPipeline", f"Verification failed; invoking coding_agent for auto-fix round {fix_round + 1}.")
            state["current_objective"] = fix_prompt
            state["task"] = fix_prompt
            try:
                state = _run_stage(f"auto_fix_{fix_round + 1}", coding_agent, state, stages_completed)
            except Exception as exc:
                log_task_update("DevPipeline", f"Auto-fix round {fix_round + 1} failed: {exc}")
        else:
            log_task_update("DevPipeline", "Max auto-fix rounds exhausted; continuing to post-setup anyway.")

    # ── Stage 12: Post-setup ──────────────────────────────────────────────────
    try:
        state = _run_stage("post_setup", post_setup_agent, state, stages_completed)
    except Exception as exc:
        log_task_update("DevPipeline", f"Post-setup stage failed (non-fatal): {exc}")

    # ── Zip export ────────────────────────────────────────────────────────────
    project_root_str = str(state.get("project_root", "")).strip()
    project_name = str(state.get("project_name", "project")).strip() or "project"
    if project_root_str:
        project_root_path = Path(project_root_str).resolve()
        if project_root_path.exists():
            zip_path = project_root_path.parent / f"{project_name}.zip"
            try:
                zip_result = _zip_project(project_root_path, zip_path)
                state["dev_pipeline_zip_path"] = zip_result
                write_text_file("dev_pipeline_zip_path.txt", zip_result)
                log_task_update("DevPipeline", f"Project zipped to: {zip_result}")
                _print_banner(f"Project export: {zip_result}")
            except Exception as exc:
                log_task_update("DevPipeline", f"Zip export failed (non-fatal): {exc}")
                state["dev_pipeline_zip_path"] = ""
        else:
            log_task_update("DevPipeline", f"project_root not found for zip: {project_root_path}")
            state["dev_pipeline_zip_path"] = ""
    else:
        state["dev_pipeline_zip_path"] = ""

    # ── Final summary ─────────────────────────────────────────────────────────
    state["dev_pipeline_status"] = "complete"
    state["dev_pipeline_stages_completed"] = stages_completed
    summary_lines = [
        f"Dev Pipeline complete. Stages: {', '.join(stages_completed)}.",
    ]
    if state.get("dev_pipeline_zip_path"):
        summary_lines.append(f"Project archive: {state['dev_pipeline_zip_path']}")
    summary = "\n".join(summary_lines)
    state["draft_response"] = summary
    log_task_update("DevPipeline", summary)
    _print_banner("Kendr Dev Pipeline — COMPLETE")

    state = publish_agent_output(
        state,
        _AGENT_NAME,
        summary,
        "dev_pipeline_complete",
        recipients=["orchestrator_agent"],
    )
    return state
