# Changelog

All notable changes to this repository should be documented in this file.

The project is still pre-`1.0`, and older history before this file may be incomplete.

The format is inspired by Keep a Changelog and uses simple repository-focused sections.

## [Unreleased]

---

## [0.2.0] — 2026-04-01

This release introduces the web UI and project workspace, making kendr accessible in the browser without losing any CLI functionality.

### Added

**Web UI (`kendr ui`)**
- full web interface on `http://localhost:5000` — chat, project workspace, config, run history, and LLM model manager
- project workspace: open any local Git repository and chat with an AI that reads your codebase
- `kendr.md` auto-detect: if the file exists it is loaded automatically; if not, kendr generates one by scanning the project structure
- live progress log stream in project chat (SSE) — shows each step (reading kendr.md, scanning files, calling LLM) in real time
- model selector dropdown in project chat input bar — switch LLM provider and model per question
- context-window usage bar — shows tokens used vs model limit, colour-coded (teal → amber → red)
- per-reply context metadata in chat bubble: model name and exact token counts
- shell automation mode — `💻` toggle in chat header; auto-approves mutating commands with terminal-style output rendering
- recent chats panel per project with colour-coded status dots

**Planner output**
- planner `draft_response` is now JSON (`{"type": "plan_approval", "steps": [...], "summary": ...}`)
- chat UI renders plan JSON as a visual plan card with step list, agent badges, and status icons
- clarification requests rendered as a styled question list card

**LLM routing**
- `get_context_window()` in `llm_router.py` — context-window size lookup for OpenAI / Anthropic / Google / Ollama / Mistral / Groq models
- `/api/models` endpoint returns `context_window` per provider and `active_context_window`

**Distribution**
- `pyproject.toml` updated to v0.2.0 with proper classifiers, keywords, optional dependency groups (`anthropic`, `google`, `ollama`, `qdrant`, `cloud`, `browser`, `telegram`, `full`, `dev`)
- `MANIFEST.in` added to include non-Python assets in sdist
- `scripts/install.sh` (Linux/macOS) rewritten with coloured output, Python version check, optional `--full` flag
- `scripts/install.ps1` (Windows) rewritten with coloured output, Python version check, optional `-Full` flag

### Changed

- project chat now routes to `/api/project/ask` (direct LLM call with kendr.md context) instead of the planner — eliminates incorrect scaffold output when asking questions about existing projects
- repository docs updated to reflect web UI as the primary interface alongside the CLI

### Fixed

- project chat sending Q&A questions to the planner, which triggered project scaffold steps instead of answering the question

## [0.1.0]

### Added

- initial Python package metadata and CLI entrypoint
- setup-aware registry, runtime orchestration, and persistence foundations
- built-in workflow agents, plugin loading, gateway surface, and docs set
