"""
dev_pipeline_tasks.py — Multi-agent dev project pipeline orchestrator.

Provides `dev_pipeline_agent(state)` which orchestrates the complete
end-to-end project generation flow in a single agent call:

  blueprint → [approval gate] → scaffold → db → auth → backend →
  frontend → deps → [tests] → security_scan → [devops] → verify →
  [auto-fix + retest loop ×3] → post_setup → zip export

Activated when state["dev_pipeline_mode"] is True.
Intended for `kendr run --dev "…"` or `kendr generate "…"`.
"""

from __future__ import annotations

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
            "Orchestrates blueprint → scaffold → build → test → verify (with "
            "auto-fix retry loop) → zip export."
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
            "verifier_status",
            "verifier_summary",
        ],
    }
}


def _print_banner(message: str, width: int = 72) -> None:
    bar = "─" * width
    sys.stdout.write(f"\n{bar}\n  {message}\n{bar}\n")
    sys.stdout.flush()


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
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", "dist", "build"}
    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for item in sorted(project_root.rglob("*")):
            if item.is_file():
                arcname = item.relative_to(project_root.parent)
                if any(part in skip_dirs for part in arcname.parts):
                    continue
                try:
                    zf.write(str(item), str(arcname))
                except Exception:
                    pass
    return str(output_path)


def _verifier_passed(state: dict) -> bool:
    """Return True if verifier_status indicates success. Treat missing/non-fail as pass."""
    status = str(state.get("verifier_status", "")).strip().lower()
    if not status:
        return True
    return status in ("pass", "passed", "ok", "success")


def _build_fix_context(state: dict, fix_round: int) -> str:
    """Build a detailed fix context string for coding_agent from verifier output."""
    summary = str(state.get("verifier_summary", "") or state.get("draft_response", "")).strip()
    issues = state.get("verifier_issues", [])
    check_results = state.get("verifier_check_results", [])

    lines = [
        f"Auto-fix round {fix_round}: Fix project verification failures.",
        "",
        f"Project root: {state.get('project_root', '(unknown)')}",
        "",
    ]

    if summary:
        lines.append("Verification report:")
        lines.append(summary[:3000])
        lines.append("")

    failed_checks = [r for r in (check_results or []) if not r.get("success", True)]
    if failed_checks:
        lines.append("Failed checks:")
        for check in failed_checks[:20]:
            lines.append(f"  [{check.get('label', '?')}]")
            if check.get("stderr"):
                for err_line in str(check["stderr"]).splitlines()[:5]:
                    lines.append(f"    {err_line}")
        lines.append("")

    if issues:
        lines.append("Issues to fix:")
        for issue in issues[:20]:
            lines.append(
                f"  [{issue.get('severity', '?')}] {issue.get('check', '?')}: "
                f"{str(issue.get('message', ''))[:200]}"
            )

    return "\n".join(lines)


def dev_pipeline_agent(state: dict) -> dict:
    """
    End-to-end project generation pipeline agent.

    Runs synchronously through all build stages in sequence. Activates when
    state["dev_pipeline_mode"] is True.

    Blueprint approval gate:
    - If auto_approve=True: blueprint is approved automatically.
    - Otherwise: the blueprint must already have blueprint_status="approved"
      (set by project_blueprint_agent when the user approved interactively),
      or this agent treats the `blueprint_waiting_for_approval=False` path as
      auto-approved for CLI non-interactive contexts.

    Auto-fix retry loop:
    - After each verifier failure, coding_agent is invoked with the full
      failure context (verifier report + failed check details).
    - test_agent is re-run after each fix attempt.
    - project_verifier_agent is re-run to check if the fix resolved issues.
    - Repeats up to dev_pipeline_max_fix_rounds times (default 3).
    - On persistent failure: sets dev_pipeline_status="partial" and includes
      a diagnostic summary in the final response.

    Zip export:
    - Packages the generated project into <project_name>.zip adjacent to
      project_root.
    - Persists path as dev_pipeline_zip_path in state and writes
      dev_pipeline_zip_path.txt to the output directory.
    """
    active_task, task_content, _ = begin_agent_session(state, _AGENT_NAME)
    state["dev_pipeline_agent_calls"] = state.get("dev_pipeline_agent_calls", 0) + 1

    auto_approve: bool = bool(state.get("auto_approve") or state.get("auto_approve_blueprint"))
    skip_tests: bool = bool(state.get("skip_test_agent", False))
    skip_devops: bool = bool(state.get("skip_devops_agent", False))
    max_fix_rounds: int = max(0, int(state.get("dev_pipeline_max_fix_rounds", 3) or 3))

    stages_completed: list[str] = list(state.get("dev_pipeline_stages_completed") or [])
    state["dev_pipeline_stages_completed"] = stages_completed
    state["dev_pipeline_status"] = "running"
    state["dev_pipeline_error"] = ""

    _print_banner("Kendr Dev Pipeline — starting full project generation")

    # ── Lazy imports to avoid circular imports ─────────────────────────────────
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
    # The approval mechanism follows the same pattern as the orchestrator:
    # - If auto_approve=True OR blueprint_status=="approved": proceed immediately.
    # - Otherwise if blueprint_waiting_for_approval is False (non-interactive
    #   gateway flow already resolved), proceed.
    # - Pending approvals that were not resolved halt the pipeline.
    blueprint_status = str(state.get("blueprint_status", "draft")).strip()
    waiting = bool(state.get("blueprint_waiting_for_approval", False))

    if blueprint_status != "approved":
        if auto_approve:
            state["blueprint_status"] = "approved"
            state["blueprint_waiting_for_approval"] = False
            log_task_update("DevPipeline", "Blueprint auto-approved — continuing to build.")
        elif not waiting:
            state["blueprint_status"] = "approved"
            log_task_update("DevPipeline", "Blueprint already resolved — continuing to build.")
        else:
            state["dev_pipeline_status"] = "waiting_for_approval"
            state["dev_pipeline_error"] = (
                "Blueprint is awaiting interactive approval. "
                "Re-run with --auto-approve or approve the blueprint and retry."
            )
            log_task_update("DevPipeline", state["dev_pipeline_error"])
            _print_banner("Pipeline paused — blueprint awaiting approval.")
            return state

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
    auth_type = str(((blueprint.get("tech_stack") or {}).get("auth", "")) or "").lower()
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
    has_frontend = bool(blueprint.get("frontend_components") or blueprint.get("frontend"))
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

    # ── Stage 8: Tests (first run) ────────────────────────────────────────────
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

    # ── Stage 11: Initial verify + auto-fix/retest loop ──────────────────────
    verifier_passed = False
    try:
        state = _run_stage("verify_0", project_verifier_agent, state, stages_completed)
        verifier_passed = _verifier_passed(state)
    except Exception as exc:
        log_task_update("DevPipeline", f"Initial verifier failed: {exc}")

    if not verifier_passed:
        for fix_round in range(1, max_fix_rounds + 1):
            fix_context = _build_fix_context(state, fix_round)
            log_task_update(
                "DevPipeline",
                f"Verification failed; invoking coding_agent for auto-fix round {fix_round}/{max_fix_rounds}.",
            )
            state["current_objective"] = fix_context
            state["task"] = fix_context

            try:
                state = _run_stage(f"auto_fix_{fix_round}", coding_agent, state, stages_completed)
            except Exception as exc:
                log_task_update("DevPipeline", f"Auto-fix round {fix_round} failed: {exc}")

            if not skip_tests:
                try:
                    state = _run_stage(f"retest_{fix_round}", test_agent, state, stages_completed)
                except Exception as exc:
                    log_task_update("DevPipeline", f"Retest round {fix_round} failed: {exc}")

            try:
                state = _run_stage(f"verify_{fix_round}", project_verifier_agent, state, stages_completed)
                verifier_passed = _verifier_passed(state)
            except Exception as exc:
                log_task_update("DevPipeline", f"Verifier round {fix_round} failed: {exc}")

            if verifier_passed:
                log_task_update("DevPipeline", f"Verification passed after fix round {fix_round}.")
                break

    # ── Stage 12: Post-setup ──────────────────────────────────────────────────
    try:
        state = _run_stage("post_setup", post_setup_agent, state, stages_completed)
    except Exception as exc:
        log_task_update("DevPipeline", f"Post-setup stage failed (non-fatal): {exc}")

    # ── Zip export ────────────────────────────────────────────────────────────
    project_root_str = str(state.get("project_root", "")).strip()
    project_name = str(state.get("project_name", "project")).strip() or "project"
    zip_path_result = ""
    if project_root_str:
        project_root_path = Path(project_root_str).resolve()
        if project_root_path.exists():
            zip_output = project_root_path.parent / f"{project_name}.zip"
            try:
                zip_path_result = _zip_project(project_root_path, zip_output)
                state["dev_pipeline_zip_path"] = zip_path_result
                write_text_file("dev_pipeline_zip_path.txt", zip_path_result)
                log_task_update("DevPipeline", f"Project zipped to: {zip_path_result}")
                _print_banner(f"Project export: {zip_path_result}")
            except Exception as exc:
                log_task_update("DevPipeline", f"Zip export failed (non-fatal): {exc}")
                state["dev_pipeline_zip_path"] = ""
        else:
            log_task_update("DevPipeline", f"project_root not found for zip: {project_root_path}")
            state["dev_pipeline_zip_path"] = ""
    else:
        state["dev_pipeline_zip_path"] = ""

    # ── Final status ──────────────────────────────────────────────────────────
    if verifier_passed:
        state["dev_pipeline_status"] = "complete"
        final_status_label = "COMPLETE"
    else:
        state["dev_pipeline_status"] = "partial"
        final_status_label = "PARTIAL (verification failures remain)"
        state["dev_pipeline_error"] = (
            "Verification did not fully pass after all auto-fix rounds. "
            f"See verifier_summary for details.\n\n"
            f"{str(state.get('verifier_summary', ''))[:1000]}"
        )

    state["dev_pipeline_stages_completed"] = stages_completed

    summary_lines = [
        f"Dev Pipeline {final_status_label}.",
        f"Stages: {', '.join(stages_completed)}.",
    ]
    if zip_path_result:
        summary_lines.append(f"Project archive: {zip_path_result}")
    if not verifier_passed:
        summary_lines.append(
            f"Verification status: {state.get('verifier_status', 'unknown')}. "
            "Review verifier_summary for remaining issues."
        )

    summary = "\n".join(summary_lines)
    state["draft_response"] = summary
    log_task_update("DevPipeline", summary)
    _print_banner(f"Kendr Dev Pipeline — {final_status_label}")

    state = publish_agent_output(
        state,
        _AGENT_NAME,
        summary,
        f"dev_pipeline_{state['dev_pipeline_status']}",
        recipients=["orchestrator_agent"],
    )
    return state
