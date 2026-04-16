# RAG Delivery Plan

This plan turns Kendr's current `superRAG` and `kendr rag` surfaces into a single package-native, local-first RAG experience that works for a new user immediately after install.

## Product Goal

The target experience is:

- install Kendr
- set `OPENAI_API_KEY`
- point Kendr at a project or folder
- index it into a project-scoped knowledge base
- ask grounded questions with citations

No Docker, no manual vector-database setup, and no dummy sample content should be required for the default path.

## Current Repo Reality

The repo already contains real RAG building blocks:

- `tasks/superrag_tasks.py`: real ingestion for local files, URLs, databases, and OneDrive
- `tasks/research_infra.py`: document parsing, chunking, embeddings, upsert, retrieval
- `tasks/vector_backends.py`: ChromaDB fallback and Qdrant support
- `kendr/rag_manager.py`: knowledge-base CRUD, source management, indexing, querying, reranking
- `kendr/persistence/superrag_store.py`: SQLite session, ingestion, and chat persistence

The main gaps are productization gaps, not missing core capability:

- setup and registry metadata still imply Qdrant is mandatory
- local Chroma persistence was tied to the working directory instead of a stable app home
- install/bootstrap did not explicitly prepare RAG storage as a first-class runtime asset
- project categorization is not yet a first-class concept in KB/session metadata
- `superRAG` and `kendr rag` overlap conceptually but do not yet share one unified operator model

## Target Architecture

### 1. Local-First Storage

Default storage should live under `KENDR_HOME`:

- SQLite: runtime metadata and chat/session history
- ChromaDB: local vector persistence
- RAG staging/uploads: imported files and ingestion manifests

Default layout:

- `KENDR_HOME/agent_workflow.sqlite3`
- `KENDR_HOME/rag/chroma/`
- `KENDR_HOME/rag/uploads/`
- `KENDR_HOME/rag/manifests/`
- `KENDR_HOME/rag/cache/`

Qdrant stays optional and should be treated as an upgrade path for shared/team deployments, not as the default install dependency.

### 2. Unified Knowledge Model

Kendr should converge on one knowledge-base model used by both `superRAG` and `kendr rag`.

Core entities:

- `knowledge_base`
- `project`
- `source`
- `ingestion_run`
- `chunk_record`
- `chat_session`

Required metadata per KB:

- `kb_id`
- `name`
- `description`
- `project_id`
- `project_name`
- `project_root`
- `category`
- `tags`
- `vector_backend`
- `embedding_model`
- `status`
- `created_at`
- `updated_at`

Required metadata per chunk:

- `kb_id`
- `project_id`
- `source_id`
- `source_type`
- `source_path_or_url`
- `document_id`
- `chunk_index`
- `content_hash`
- `last_indexed_at`

### 3. Project-Centric Categorization

The primary beginner abstraction should be "project", not "collection name".

Each project should map to one default KB, while still allowing advanced users to create multiple KBs per project.

Minimum project fields:

- `project_id`
- `display_name`
- `root_path`
- `category`
- `stack`
- `description`
- `default_kb_id`

Suggested categories:

- `product_docs`
- `engineering_repo`
- `research_notes`
- `customer_support`
- `database_ops`
- `compliance`
- `mixed`

User-facing behavior:

- user selects or creates a project once
- source additions inherit the project automatically
- indexing and querying default to the project's active KB
- results always show which project/KB they came from

## Newbie Workflow

### Install and First Run

On install/bootstrap:

- create `KENDR_HOME`
- create local ChromaDB path
- create RAG upload/staging directories
- leave `QDRANT_URL` blank by default
- expose a quickstart command for first indexing

### First-Time KB Creation

Beginner-safe flow:

1. `kendr rag init`
2. choose project name
3. choose project root folder
4. optionally choose category
5. Kendr creates the project and its default KB
6. Kendr offers to index common folders like `docs/`, `src/`, `notes/`, `README*`

### Indexing

Beginner-safe command surface:

- `kendr rag init`
- `kendr rag add-source`
- `kendr rag index`
- `kendr rag ask`
- `kendr rag status`

Advanced operators remain available, but they should not be the first-time path.

## Ingestion Design

### Source Types

Supported source types should remain:

- folder
- file
- URL
- database
- OneDrive

Each source needs:

- stable `source_id`
- source-local config
- inclusion/exclusion rules
- fingerprint/hash
- last successful index timestamp
- last error

### Incremental Indexing

Incremental indexing is the next major requirement after local-first packaging.

Per source, Kendr should track:

- content hash
- file size
- mtime
- parser version
- chunking version
- embedding model version

Re-index only when one of those changes.

### Chunking Defaults

Default chunking should be opinionated and overridable:

- text/code/docs: 800 to 1200 chars
- overlap: 100 to 150 chars
- hard max for oversized binary/text extractions

Code repositories should eventually use parser-aware chunking for:

- Python
- TypeScript/JavaScript
- Markdown
- SQL
- JSON/YAML/TOML

## Retrieval Design

Phase target retrieval pipeline:

1. vector retrieve
2. metadata filter by project/KB/source type
3. optional rerank
4. grounded answer generation with citations

Minimum answer contract:

- answer text
- explicit statement when evidence is insufficient
- cited sources
- project and KB name in the response payload

## Command and UI Alignment

### CLI

Keep `kendr run --superrag-*` for compatibility, but make `kendr rag` the primary management surface.

Planned CLI additions:

- `kendr rag init`
- `kendr rag projects list`
- `kendr rag projects create`
- `kendr rag attach-project`
- `kendr rag reindex --changed-only`
- `kendr rag ask --project <name>`

### Web/Desktop UI

The RAG UI should expose:

- project selector
- KB selector
- source list with status
- index/reindex actions
- retrieval test box
- ingestion history
- citation preview

The first-run UI should guide the user through project creation and indexing instead of expecting them to know collection terminology.

## Implementation Phases

### Phase 1: Zero-Config Local Packaging

Files:

- `scripts/bootstrap_local_state.py`
- `tasks/vector_backends.py`
- `kendr/setup/catalog.py`
- `tasks/superrag_tasks.py`

Deliverables:

- stable local Chroma path under `KENDR_HOME`
- install/bootstrap creates RAG directories
- setup no longer hides RAG when Qdrant is absent
- docs explain local-first default clearly

### Phase 2: Unify `superRAG` and `rag_manager`

Files:

- `tasks/superrag_tasks.py`
- `kendr/rag_manager.py`
- `kendr/persistence/superrag_store.py`
- `kendr/persistence/core.py`

Deliverables:

- one shared KB/session metadata model
- common naming for session/KB/project
- one retrieval/indexing backend wrapper
- one status surface

### Phase 3: Project Model and Categorization

Files:

- `kendr/project_manager.py`
- `kendr/project_context.py`
- `kendr/rag_manager.py`
- `kendr/persistence/core.py`

Deliverables:

- first-class project metadata
- category and tag support
- default KB per project
- per-project indexing and querying

### Phase 4: Incremental Indexing and Real Source Manifests

Files:

- `tasks/superrag_tasks.py`
- `kendr/rag_manager.py`
- new manifest helpers under `kendr/` or `tasks/`

Deliverables:

- changed-only indexing
- source manifests and content hashes
- parser/chunker/embedder versioning
- resumable ingestion jobs

### Phase 5: UX Cleanup for New Users

Files:

- `kendr/cli.py`
- `kendr/ui_server.py`
- Electron renderer panels if needed
- `docs/quickstart.md`
- `docs/install.md`

Deliverables:

- `kendr rag init`
- guided first-run indexing
- simpler language: project, source, knowledge base
- clearer status and citation visibility

### Phase 6: Verification and Packaging Hardening

Files:

- `tests/test_setup_registry.py`
- `tests/test_superrag_smoke.py`
- `tests/test_research_infra.py`
- `scripts/verify.py`
- packaging/build scripts

Deliverables:

- tests for local-first RAG defaults
- tests for project-scoped indexing
- tests for retrieval/citation payload shape
- packaged desktop verification of local RAG paths

## Definition of Done

RAG should be considered complete for the default user path when all of these are true:

- installing Kendr creates a usable local RAG store without Qdrant
- setup marks RAG as available when only OpenAI is configured
- a user can create a project and index local docs in one guided flow
- the indexed data is stored per project/KB with stable metadata
- querying returns grounded answers with citations
- re-indexing avoids re-embedding unchanged content
- docs and setup screens explain the default path without infrastructure jargon

## Immediate Next Engineering Moves

The next implementation pass should focus on:

1. converging `superRAG` session metadata and `rag_manager` KB metadata into one schema
2. adding project IDs/categories/tags to persistence
3. introducing a guided `kendr rag init` command
4. adding incremental indexing manifests so repeated runs stop reprocessing unchanged files
