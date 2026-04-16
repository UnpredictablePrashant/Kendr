"""
kendr/rag_manager.py — Super-RAG Knowledge Base Manager

Manages named knowledge bases (KBs) with:
  - Configurable vector backends (chromadb / qdrant / pgvector)
  - Multi-source ingestion: local folders, file uploads, URLs, databases, OneDrive
  - Reranker pipeline: none | keyword | rrf | cross_encoder | cohere
  - Agent-integration roster: which agents can access each KB
  - Persistent config at ~/.kendr/rag_config.json
  - Indexes by calling existing research_infra embed/upsert infrastructure
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------
_CONFIG_DIR = Path(os.getenv("KENDR_CONFIG_DIR", "~/.kendr")).expanduser()
_RAG_CONFIG_PATH = _CONFIG_DIR / "rag_config.json"
_UPLOADS_DIR = _CONFIG_DIR / "rag_uploads"
_DEFAULT_CHROMA_PATH = _CONFIG_DIR / "rag" / "chroma"

_CONFIG_LOCK = threading.Lock()

_DEFAULT_EMBEDDING_MODEL = "openai:text-embedding-3-small"
_DEFAULT_TOP_K = 8
_DEFAULT_RERANK_TOP_K = 20

_ALL_BACKENDS = ["chromadb", "qdrant", "pgvector"]
_ALL_RERANKERS = ["none", "keyword", "rrf", "cross_encoder", "cohere"]
_SOURCE_TYPES = ["folder", "file", "url", "database", "onedrive"]

_SUPPORTED_AGENTS = [
    "superrag_agent",
    "github_agent",
    "worker_agent",
    "reviewer_agent",
    "report_agent",
    "orchestrator_agent",
]


# ---------------------------------------------------------------------------
# Low-level config I/O
# ---------------------------------------------------------------------------
def _load_config() -> dict:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not _RAG_CONFIG_PATH.exists():
        return {"version": 1, "active_kb_id": "", "knowledge_bases": {}}
    try:
        return json.loads(_RAG_CONFIG_PATH.read_text("utf-8"))
    except Exception:
        return {"version": 1, "active_kb_id": "", "knowledge_bases": {}}


def _save_config(cfg: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _RAG_CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), "utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kb_id(name: str) -> str:
    return hashlib.md5(f"{name}:{time.time()}".encode()).hexdigest()[:12]


def _source_id() -> str:
    return uuid.uuid4().hex[:12]


def _collection_name(kb_id: str) -> str:
    return f"kendr_rag_{kb_id}"


# ---------------------------------------------------------------------------
# Public KB CRUD
# ---------------------------------------------------------------------------
def list_kbs() -> list[dict]:
    with _CONFIG_LOCK:
        cfg = _load_config()
    active_id = str(cfg.get("active_kb_id", "") or "").strip()
    results: list[dict] = []
    for kb in cfg.get("knowledge_bases", {}).values():
        item = dict(kb)
        item["is_active"] = bool(active_id and str(item.get("id", "")).strip() == active_id)
        results.append(item)
    return results


def get_kb(kb_id: str) -> dict | None:
    with _CONFIG_LOCK:
        cfg = _load_config()
    return cfg.get("knowledge_bases", {}).get(kb_id)


def get_active_kb() -> dict | None:
    with _CONFIG_LOCK:
        cfg = _load_config()
    active_id = cfg.get("active_kb_id", "")
    if not active_id:
        kbs = list(cfg.get("knowledge_bases", {}).values())
        return kbs[0] if kbs else None
    return cfg.get("knowledge_bases", {}).get(active_id)


def resolve_kb(kb_ref: str = "", *, use_active_if_empty: bool = True, require_indexed: bool = False) -> dict:
    """Resolve a KB by id or name, optionally falling back to the active KB."""
    kb_ref = str(kb_ref or "").strip()
    if not kb_ref:
        if not use_active_if_empty:
            raise ValueError("Knowledge base reference is required.")
        kb = get_active_kb()
        if not kb:
            raise ValueError("No active knowledge base is configured.")
    else:
        kb = get_kb(kb_ref)
        if not kb:
            kb_lower = kb_ref.lower()
            matches = [item for item in list_kbs() if str(item.get("name", "")).strip().lower() == kb_lower]
            if not matches:
                raise ValueError(f"Knowledge base not found: {kb_ref}")
            if len(matches) > 1:
                raise ValueError(f"Knowledge base name is ambiguous: {kb_ref}")
            kb = matches[0]

    status = str(kb.get("status", "") or "").strip().lower()
    if require_indexed and status != "indexed":
        raise ValueError(
            f"Knowledge base '{kb.get('name', kb.get('id', 'unknown'))}' is not indexed yet."
        )
    return kb


def set_active_kb(kb_id: str) -> None:
    with _CONFIG_LOCK:
        cfg = _load_config()
        cfg["active_kb_id"] = kb_id
        _save_config(cfg)


def create_kb(name: str, description: str = "") -> dict:
    name = name.strip()
    if not name:
        raise ValueError("KB name cannot be empty.")
    kid = _kb_id(name)
    now = _now()
    kb = {
        "id": kid,
        "name": name,
        "description": description,
        "collection_name": _collection_name(kid),
        "created_at": now,
        "updated_at": now,
        "vector_config": {
            "backend": "chromadb",
            "chromadb_path": str(_DEFAULT_CHROMA_PATH),
            "qdrant_url": os.getenv("QDRANT_URL", ""),
            "qdrant_api_key": "",
            "pgvector_url": "",
            "embedding_model": _DEFAULT_EMBEDDING_MODEL,
        },
        "reranker_config": {
            "algorithm": "none",
            "cohere_api_key": "",
            "cross_encoder_model": "cross-encoder/ms-marco-MiniLM-L-6-v2",
            "top_k": _DEFAULT_TOP_K,
            "rerank_top_k": _DEFAULT_RERANK_TOP_K,
            "keyword_weight": 0.3,
        },
        "sources": [],
        "enabled_agents": [],
        "status": "empty",
        "stats": {"total_chunks": 0, "total_items": 0, "last_indexed_at": ""},
        "index_log": [],
    }
    with _CONFIG_LOCK:
        cfg = _load_config()
        cfg.setdefault("knowledge_bases", {})[kid] = kb
        if not cfg.get("active_kb_id"):
            cfg["active_kb_id"] = kid
        _save_config(cfg)
    return kb


def delete_kb(kb_id: str) -> bool:
    with _CONFIG_LOCK:
        cfg = _load_config()
        kbs = cfg.get("knowledge_bases", {})
        if kb_id not in kbs:
            return False
        del kbs[kb_id]
        if cfg.get("active_kb_id") == kb_id:
            remaining = list(kbs.keys())
            cfg["active_kb_id"] = remaining[0] if remaining else ""
        _save_config(cfg)
    return True


def update_kb_field(kb_id: str, **kwargs) -> dict | None:
    with _CONFIG_LOCK:
        cfg = _load_config()
        kb = cfg.get("knowledge_bases", {}).get(kb_id)
        if not kb:
            return None
        for key, val in kwargs.items():
            if isinstance(val, dict) and isinstance(kb.get(key), dict):
                kb[key].update(val)
            else:
                kb[key] = val
        kb["updated_at"] = _now()
        _save_config(cfg)
        return kb


# ---------------------------------------------------------------------------
# Source management
# ---------------------------------------------------------------------------
def add_source(
    kb_id: str,
    source_type: str,
    *,
    label: str = "",
    path: str = "",
    url: str = "",
    db_url: str = "",
    recursive: bool = True,
    max_files: int = 300,
    max_pages: int = 20,
    extensions: str = "",
    tables: str = "",
    schema: str = "",
    same_domain: bool = False,
    onedrive_path: str = "",
) -> dict:
    if source_type not in _SOURCE_TYPES:
        raise ValueError(f"source_type must be one of: {_SOURCE_TYPES}")

    config: dict[str, Any] = {}
    if source_type == "folder":
        if not path:
            raise ValueError("path is required for folder sources.")
        resolved = str(Path(path).expanduser().resolve())
        if not os.path.isdir(resolved):
            raise ValueError(f"Directory not found: {resolved}")
        config = {
            "path": resolved,
            "recursive": recursive,
            "max_files": max_files,
            "extensions": extensions,
        }
        label = label or os.path.basename(resolved)
    elif source_type == "file":
        if not path:
            raise ValueError("path is required for file sources.")
        resolved = str(Path(path).expanduser().resolve())
        if not os.path.isfile(resolved):
            raise ValueError(f"File not found: {resolved}")
        config = {"path": resolved}
        label = label or os.path.basename(resolved)
    elif source_type == "url":
        if not url:
            raise ValueError("url is required for URL sources.")
        config = {"url": url, "max_pages": max_pages, "same_domain": same_domain}
        label = label or url[:60]
    elif source_type == "database":
        if not db_url:
            raise ValueError("db_url is required for database sources.")
        config = {"db_url": db_url, "tables": tables, "schema": schema}
        label = label or _sanitize_db_url(db_url)
    elif source_type == "onedrive":
        config = {"onedrive_path": onedrive_path}
        label = label or f"OneDrive:{onedrive_path or '/'}"

    source = {
        "source_id": _source_id(),
        "type": source_type,
        "label": label,
        "config": config,
        "status": "pending",
        "added_at": _now(),
        "indexed_at": "",
        "stats": {"chunks": 0, "items": 0},
        "error": "",
    }

    with _CONFIG_LOCK:
        cfg = _load_config()
        kb = cfg.get("knowledge_bases", {}).get(kb_id)
        if not kb:
            raise ValueError(f"KB not found: {kb_id}")
        kb["sources"].append(source)
        kb["updated_at"] = _now()
        _save_config(cfg)
    return source


def remove_source(kb_id: str, source_id: str) -> bool:
    with _CONFIG_LOCK:
        cfg = _load_config()
        kb = cfg.get("knowledge_bases", {}).get(kb_id)
        if not kb:
            return False
        before = len(kb["sources"])
        kb["sources"] = [s for s in kb["sources"] if s["source_id"] != source_id]
        kb["updated_at"] = _now()
        _save_config(cfg)
    return len(kb["sources"]) < before


def upload_file_to_kb(kb_id: str, filename: str, data: bytes) -> dict:
    kb = get_kb(kb_id)
    if not kb:
        raise ValueError(f"KB not found: {kb_id}")
    safe_name = re.sub(r"[^a-zA-Z0-9._\-]", "_", os.path.basename(filename))
    dest_dir = _UPLOADS_DIR / kb_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_name
    dest.write_bytes(data)
    return add_source(kb_id, "file", path=str(dest), label=filename)


# ---------------------------------------------------------------------------
# Vector + reranker config helpers
# ---------------------------------------------------------------------------
def update_vector_config(kb_id: str, config: dict) -> dict | None:
    allowed = {"backend", "chromadb_path", "qdrant_url", "qdrant_api_key", "pgvector_url", "embedding_model"}
    clean = {k: v for k, v in config.items() if k in allowed}
    return update_kb_field(kb_id, vector_config=clean)


def update_reranker_config(kb_id: str, config: dict) -> dict | None:
    allowed = {"algorithm", "cohere_api_key", "cross_encoder_model", "top_k", "rerank_top_k", "keyword_weight"}
    clean = {k: v for k, v in config.items() if k in allowed}
    return update_kb_field(kb_id, reranker_config=clean)


def toggle_agent(kb_id: str, agent_name: str, enabled: bool) -> dict | None:
    with _CONFIG_LOCK:
        cfg = _load_config()
        kb = cfg.get("knowledge_bases", {}).get(kb_id)
        if not kb:
            return None
        agents = list(kb.get("enabled_agents", []))
        if enabled and agent_name not in agents:
            agents.append(agent_name)
        elif not enabled and agent_name in agents:
            agents.remove(agent_name)
        kb["enabled_agents"] = agents
        kb["updated_at"] = _now()
        _save_config(cfg)
        return kb


def get_supported_agents() -> list[str]:
    try:
        from tasks import _discover_agents
        discovered = list(_discover_agents().keys())
        return discovered if discovered else _SUPPORTED_AGENTS
    except Exception:
        return _SUPPORTED_AGENTS


# ---------------------------------------------------------------------------
# Vector backend factory (KB-aware)
# ---------------------------------------------------------------------------
def _get_backend_for_kb(kb: dict):
    """
    Return a VectorBackend instance configured for this KB's vector_config.
    Falls back to the global get_vector_backend() if backend=chromadb or qdrant
    uses the default env-based config.
    """
    vc = kb.get("vector_config", {})
    backend = vc.get("backend", "chromadb")

    if backend == "qdrant":
        from qdrant_client import QdrantClient
        from tasks.vector_backends import QdrantBackend
        url = vc.get("qdrant_url") or os.getenv("QDRANT_URL", "http://localhost:6333")
        api_key = vc.get("qdrant_api_key") or os.getenv("QDRANT_API_KEY", "")
        client = QdrantClient(url=url, api_key=api_key or None)
        b = QdrantBackend.__new__(QdrantBackend)
        b._url = url
        b._client = client
        return b

    if backend == "pgvector":
        pg_url = vc.get("pgvector_url", "")
        if not pg_url:
            raise ValueError("pgvector_url is required for pgvector backend.")
        from tasks.vector_backends import PGVectorBackend  # type: ignore[attr-defined]
        return PGVectorBackend(pg_url)

    # Default: chromadb (local path)
    import chromadb as _chromadb
    from tasks.vector_backends import ChromaBackend
    path = vc.get("chromadb_path") or str(_DEFAULT_CHROMA_PATH)
    Path(path).mkdir(parents=True, exist_ok=True)
    b = ChromaBackend.__new__(ChromaBackend)
    b._client = _chromadb.PersistentClient(path=path)
    b._collections = {}
    return b


def _embed_texts_for_kb(kb: dict, texts: list[str]) -> list[list[float]]:
    from tasks.research_infra import embed_texts, get_openai_client
    model_spec = kb.get("vector_config", {}).get("embedding_model", _DEFAULT_EMBEDDING_MODEL)
    if model_spec.startswith("openai:"):
        model = model_spec[len("openai:"):]
    else:
        model = model_spec
    client = get_openai_client()
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


# ---------------------------------------------------------------------------
# Reranking
# ---------------------------------------------------------------------------
def _rerank_hits(hits: list[dict], query: str, reranker_cfg: dict) -> list[dict]:
    algorithm = reranker_cfg.get("algorithm", "none")
    top_k = int(reranker_cfg.get("top_k", _DEFAULT_TOP_K))

    if algorithm == "none":
        return hits[:top_k]

    if algorithm == "keyword":
        weight = float(reranker_cfg.get("keyword_weight", 0.3))
        q_tokens = set(query.lower().split())
        for hit in hits:
            text_tokens = set(str(hit.get("text", "")).lower().split())
            overlap = len(q_tokens & text_tokens) / max(len(q_tokens), 1)
            vec_score = float(hit.get("score") or 0)
            hit["score"] = vec_score * (1 - weight) + overlap * weight
        hits.sort(key=lambda h: h.get("score", 0), reverse=True)
        return hits[:top_k]

    if algorithm == "rrf":
        for rank, hit in enumerate(hits):
            hit["_rrf"] = 1.0 / (60 + rank + 1)
        hits.sort(key=lambda h: h.get("_rrf", 0), reverse=True)
        return hits[:top_k]

    if algorithm == "cross_encoder":
        try:
            from sentence_transformers import CrossEncoder
            model_name = reranker_cfg.get("cross_encoder_model", "cross-encoder/ms-marco-MiniLM-L-6-v2")
            model = CrossEncoder(model_name)
            pairs = [(query, str(h.get("text", ""))) for h in hits]
            scores = model.predict(pairs)
            for hit, score in zip(hits, scores):
                hit["score"] = float(score)
            hits.sort(key=lambda h: h.get("score", 0), reverse=True)
            return hits[:top_k]
        except ImportError:
            pass
        return hits[:top_k]

    if algorithm == "cohere":
        try:
            import cohere
            api_key = reranker_cfg.get("cohere_api_key") or os.getenv("COHERE_API_KEY", "")
            if not api_key:
                return hits[:top_k]
            co = cohere.Client(api_key)
            docs = [str(h.get("text", "")) for h in hits]
            result = co.rerank(query=query, documents=docs, top_n=top_k, model="rerank-multilingual-v3.0")
            reranked = []
            for r in result.results:
                hit = dict(hits[r.index])
                hit["score"] = r.relevance_score
                reranked.append(hit)
            return reranked
        except ImportError:
            pass
        return hits[:top_k]

    return hits[:top_k]


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------
_index_jobs: dict[str, dict] = {}
_index_lock = threading.Lock()


def get_index_job(kb_id: str) -> dict | None:
    with _index_lock:
        return _index_jobs.get(kb_id)


def index_kb(kb_id: str, source_ids: list[str] | None = None) -> dict:
    """
    Trigger asynchronous indexing for all (or specific) sources in a KB.
    Returns a job status dict immediately.
    """
    kb = get_kb(kb_id)
    if not kb:
        raise ValueError(f"KB not found: {kb_id}")

    with _index_lock:
        existing = _index_jobs.get(kb_id, {})
        if existing.get("status") == "running":
            return existing
        job = {
            "kb_id": kb_id,
            "status": "running",
            "started_at": _now(),
            "finished_at": "",
            "sources_total": 0,
            "sources_done": 0,
            "chunks_indexed": 0,
            "errors": [],
            "log": [],
        }
        _index_jobs[kb_id] = job

    def _run():
        try:
            _do_index(kb_id, source_ids, job)
        except Exception as exc:
            with _index_lock:
                job["status"] = "error"
                job["errors"].append(str(exc))
                job["finished_at"] = _now()
            _persist_index_log(kb_id, job)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return dict(job)


def _do_index(kb_id: str, source_ids: list[str] | None, job: dict) -> None:
    from tasks.research_infra import chunk_text, crawl_urls, parse_documents

    kb = get_kb(kb_id)
    if not kb:
        raise ValueError(f"KB not found: {kb_id}")

    sources = kb.get("sources", [])
    if source_ids:
        sources = [s for s in sources if s["source_id"] in source_ids]

    job["sources_total"] = len(sources)
    backend = _get_backend_for_kb(kb)
    collection = kb["collection_name"]
    chunk_size = 1200
    overlap = 150

    total_chunks = 0
    total_items = 0

    for src in sources:
        sid = src["source_id"]
        stype = src["type"]
        cfg = src.get("config", {})
        job["log"].append(f"[{stype}] {src['label']} — indexing…")
        _set_source_status(kb_id, sid, "indexing")
        try:
            docs: list[dict] = []
            if stype in ("folder", "file"):
                path = cfg.get("path", "")
                recursive = cfg.get("recursive", True)
                max_files = int(cfg.get("max_files", 300))
                exts_raw = cfg.get("extensions", "")
                exts = {e.strip().lower() for e in exts_raw.split(",") if e.strip()} or None
                paths = _collect_paths(path, recursive=recursive, max_files=max_files, extensions=exts)
                parsed = parse_documents(paths, continue_on_error=True, ocr_images=False)
                for item in parsed:
                    docs.append({
                        "source": str(item.get("path", path)),
                        "text": str(item.get("text", "") or ""),
                        "metadata": {"source_type": stype, "path": str(item.get("path", ""))},
                    })
            elif stype == "url":
                urls = [cfg.get("url", "")]
                max_pages = int(cfg.get("max_pages", 20))
                same_domain = bool(cfg.get("same_domain", False))
                pages = crawl_urls(urls, max_pages=max_pages, same_domain=same_domain)
                for p in pages:
                    text = str(p.get("text", "") or "").strip()
                    if text:
                        docs.append({
                            "source": p.get("url", ""),
                            "text": text,
                            "metadata": {"source_type": "url"},
                        })
            elif stype == "database":
                db_url = cfg.get("db_url", "")
                tables = cfg.get("tables", "")
                schema = cfg.get("schema", "")
                docs = _ingest_db(db_url, tables=tables, schema=schema)
            elif stype == "onedrive":
                onedrive_path = cfg.get("onedrive_path", "")
                docs = _ingest_onedrive(onedrive_path)

            records: list[dict] = []
            for doc in docs:
                text = str(doc.get("text", "") or "").strip()
                if not text:
                    continue
                chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
                for idx, chunk in enumerate(chunks):
                    records.append({
                        "id": abs(hash(f"{kb_id}:{sid}:{doc.get('source','')}:{idx}")),
                        "text": chunk,
                        "source": doc.get("source", ""),
                        "payload": {**doc.get("metadata", {}), "source": doc.get("source", ""), "kb_id": kb_id},
                    })

            if records:
                batch_size = 64
                for i in range(0, len(records), batch_size):
                    batch = records[i: i + batch_size]
                    texts = [r["text"] for r in batch]
                    vectors = _embed_texts_for_kb(kb, texts)
                    backend.ensure_collection(collection, vector_size=len(vectors[0]) if vectors else 1536)
                    backend.upsert(collection, batch, vectors)

            chunk_count = len(records)
            item_count = len(docs)
            total_chunks += chunk_count
            total_items += item_count
            _set_source_status(kb_id, sid, "indexed", chunks=chunk_count, items=item_count)
            job["log"].append(f"  ✓ {item_count} items, {chunk_count} chunks indexed")
        except Exception as exc:
            _set_source_status(kb_id, sid, "error", error=str(exc))
            job["errors"].append(f"{src['label']}: {exc}")
            job["log"].append(f"  ✗ error: {exc}")

        job["sources_done"] += 1
        job["chunks_indexed"] = total_chunks

    job["status"] = "done" if not job["errors"] else "done_with_errors"
    job["finished_at"] = _now()

    # Persist stats back to KB
    with _CONFIG_LOCK:
        cfg2 = _load_config()
        kb2 = cfg2.get("knowledge_bases", {}).get(kb_id)
        if kb2:
            kb2["stats"]["total_chunks"] = total_chunks
            kb2["stats"]["total_items"] = total_items
            kb2["stats"]["last_indexed_at"] = _now()
            kb2["status"] = "indexed"
            _save_config(cfg2)

    _persist_index_log(kb_id, job)


def _persist_index_log(kb_id: str, job: dict) -> None:
    with _CONFIG_LOCK:
        cfg = _load_config()
        kb = cfg.get("knowledge_bases", {}).get(kb_id)
        if kb:
            log_entry = {
                "started_at": job.get("started_at", ""),
                "finished_at": job.get("finished_at", ""),
                "status": job.get("status", ""),
                "chunks_indexed": job.get("chunks_indexed", 0),
                "errors": job.get("errors", []),
            }
            kb.setdefault("index_log", []).append(log_entry)
            kb["index_log"] = kb["index_log"][-20:]
            _save_config(cfg)


def _set_source_status(kb_id: str, source_id: str, status: str, *, chunks: int = 0, items: int = 0, error: str = "") -> None:
    with _CONFIG_LOCK:
        cfg = _load_config()
        kb = cfg.get("knowledge_bases", {}).get(kb_id)
        if not kb:
            return
        for src in kb.get("sources", []):
            if src["source_id"] == source_id:
                src["status"] = status
                if status == "indexed":
                    src["indexed_at"] = _now()
                    src["stats"] = {"chunks": chunks, "items": items}
                if error:
                    src["error"] = error
                break
        _save_config(cfg)


# ---------------------------------------------------------------------------
# Query / retrieval
# ---------------------------------------------------------------------------
def query_kb(kb_id: str, query: str, top_k: int | None = None) -> dict:
    kb = get_kb(kb_id)
    if not kb:
        raise ValueError(f"KB not found: {kb_id}")

    reranker_cfg = kb.get("reranker_config", {})
    effective_top_k = top_k or int(reranker_cfg.get("top_k", _DEFAULT_TOP_K))
    fetch_k = int(reranker_cfg.get("rerank_top_k", _DEFAULT_RERANK_TOP_K))
    fetch_k = max(fetch_k, effective_top_k)

    backend = _get_backend_for_kb(kb)
    collection = kb["collection_name"]
    backend.ensure_collection(collection)

    query_vectors = _embed_texts_for_kb(kb, [query])
    raw_hits = backend.search(collection, query_vectors[0], top_k=fetch_k)

    hits = _rerank_hits(raw_hits, query, {**reranker_cfg, "top_k": effective_top_k})

    citations = []
    for rank, hit in enumerate(hits, start=1):
        meta = hit.get("metadata") or hit.get("payload") or {}
        citations.append({
            "rank": rank,
            "source": hit.get("source", meta.get("source", "?")),
            "score": round(float(hit.get("score") or 0), 4),
            "text_preview": str(hit.get("text", ""))[:200],
            "source_type": meta.get("source_type", ""),
        })

    return {
        "kb_id": kb_id,
        "kb_name": kb.get("name", ""),
        "query": query,
        "hits": hits,
        "citations": citations,
        "total_hits": len(hits),
        "algorithm": reranker_cfg.get("algorithm", "none"),
    }


def build_research_grounding(
    query: str,
    *,
    kb_ref: str = "",
    top_k: int = 8,
    use_active_if_empty: bool = True,
    require_indexed: bool = True,
) -> dict:
    """Resolve a KB and return a prompt-ready grounding packet for research flows."""
    kb = resolve_kb(kb_ref, use_active_if_empty=use_active_if_empty, require_indexed=require_indexed)
    result = query_kb(str(kb.get("id", "")).strip(), query, top_k=top_k)
    hits = result.get("hits", []) if isinstance(result.get("hits", []), list) else []

    normalized_citations: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    deduped_source_ids: list[str] = []
    context_blocks: list[str] = []
    seen_hit_keys: set[tuple[str, str]] = set()

    for rank, hit in enumerate(hits, start=1):
        meta = hit.get("metadata") or hit.get("payload") or {}
        source_ref = str(hit.get("source", "") or meta.get("source", "") or "").strip()
        if not source_ref:
            source_ref = f"kb://{kb.get('id', '')}/hit/{rank}"
        chunk_index = str(meta.get("chunk_index", "")).strip()
        hit_key = (source_ref, chunk_index)
        if hit_key in seen_hit_keys:
            continue
        seen_hit_keys.add(hit_key)
        if source_ref not in seen_sources:
            seen_sources.add(source_ref)
            deduped_source_ids.append(source_ref)

        source_type = str(meta.get("source_type", "") or "").strip()
        label = source_ref
        path_value = ""
        url_value = ""
        if source_ref.startswith("file://"):
            path_value = source_ref[7:]
            label = Path(path_value).name or source_ref
            url_value = source_ref
        elif "://" in source_ref:
            url_value = source_ref
            try:
                parsed = re.sub(r"\s+", " ", source_ref).strip()
                label = parsed if parsed.startswith("db://") else source_ref
            except Exception:
                label = source_ref
        else:
            path_value = source_ref
            try:
                url_value = Path(source_ref).expanduser().resolve().as_uri()
                label = Path(source_ref).name or source_ref
            except Exception:
                url_value = source_ref
                label = source_ref

        preview = str(hit.get("text", "") or "").strip()
        normalized = {
            "rank": rank,
            "source_id": source_ref,
            "url": url_value,
            "path": path_value,
            "label": label,
            "score": round(float(hit.get("score") or 0), 4),
            "source_type": source_type,
            "chunk_index": meta.get("chunk_index"),
            "text_preview": preview[:240],
            "kb_provenance": {
                "kb_id": str(kb.get("id", "")).strip(),
                "kb_name": str(kb.get("name", "")).strip(),
            },
        }
        normalized_citations.append(normalized)
        context_blocks.append(
            "\n".join(
                [
                    f"[KB Source {rank}] {label}",
                    f"Source ref: {source_ref}",
                    f"KB: {kb.get('name', '')}",
                    f"Source type: {source_type or 'unknown'}",
                    f"Score: {normalized['score']}",
                    preview[:1800] or "No retrieved text.",
                ]
            )
        )

    prompt_context = ""
    if context_blocks:
        prompt_context = (
            "Knowledge Base Grounding:\n"
            f"- KB: {kb.get('name', '')}\n"
            f"- Hits: {len(hits)}\n\n"
            + "\n\n".join(context_blocks[:8])
        )

    return {
        "kb_id": str(kb.get("id", "")).strip(),
        "kb_name": str(kb.get("name", "")).strip(),
        "kb_status": str(kb.get("status", "")).strip(),
        "query": query,
        "top_k": int(top_k or 8),
        "raw_hits": hits,
        "citations": normalized_citations,
        "deduped_source_ids": deduped_source_ids,
        "prompt_context": prompt_context,
        "hit_count": len(hits),
        "used": bool(hits),
    }


def generate_answer(kb_id: str, query: str, top_k: int = 8) -> dict:
    """Query + LLM answer generation with citations."""
    result = query_kb(kb_id, query, top_k=top_k)
    hits = result.get("hits", [])
    if not hits:
        return {**result, "answer": "No indexed content found for this query. Try indexing sources first."}

    try:
        from tasks.research_infra import llm_text
        context_blocks = []
        for i, hit in enumerate(hits[:8], start=1):
            source = hit.get("source", "?")
            text = str(hit.get("text", ""))[:1800]
            score = hit.get("score")
            context_blocks.append(f"[{i}] source={source} score={score}\n{text}")

        prompt = f"""You are a helpful assistant answering questions based on the retrieved knowledge base context.

Question: {query}

Retrieved context:
{chr(10).join(context_blocks)}

Instructions:
- Answer using only the context above.
- If the context is insufficient, say what is missing.
- Add a short "Sources" section at the end listing the relevant source identifiers.
""".strip()
        answer = llm_text(prompt)
    except Exception as exc:
        answer = f"[LLM generation failed: {exc}] Raw hits: {len(hits)} chunks retrieved."

    return {**result, "answer": answer}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _sanitize_db_url(url: str) -> str:
    """Strip passwords from DB URL for display."""
    return re.sub(r"://([^:]+):[^@]+@", r"://\1:***@", url)


def _collect_paths(root: str, recursive: bool, max_files: int, extensions: set[str] | None) -> list[str]:
    from tasks.research_infra import LOCAL_DRIVE_SUPPORTED_EXTENSIONS
    p = Path(root).expanduser().resolve()
    exts = extensions or set(LOCAL_DRIVE_SUPPORTED_EXTENSIONS)
    files: list[str] = []
    if p.is_file():
        return [str(p)]
    candidates = p.rglob("*") if recursive else p.glob("*")
    for item in sorted(candidates):
        if not item.is_file():
            continue
        if item.suffix.lower() not in exts:
            continue
        files.append(str(item))
        if len(files) >= max_files:
            break
    return files


def _ingest_db(db_url: str, tables: str = "", schema: str = "") -> list[dict]:
    try:
        from sqlalchemy import MetaData, Table, create_engine, func, inspect, select
    except ImportError as exc:
        raise ValueError("Database ingestion requires SQLAlchemy. Run: pip install sqlalchemy") from exc
    engine = create_engine(db_url)
    inspector = inspect(engine)
    target_schema = schema.strip() or None
    explicit_tables = set(t.strip() for t in tables.split(",") if t.strip())
    table_names = inspector.get_table_names(schema=target_schema)
    if explicit_tables:
        table_names = [t for t in table_names if t in explicit_tables]

    docs: list[dict] = []
    for table_name in table_names[:100]:
        try:
            columns = inspector.get_columns(table_name, schema=target_schema)
            col_lines = [f"- {c.get('name')} ({c.get('type')})" for c in columns]
            schema_text = f"Table: {table_name}\nColumns:\n" + "\n".join(col_lines)
            docs.append({
                "source": f"db://{table_name}#schema",
                "text": schema_text,
                "metadata": {"source_type": "database_schema", "table": table_name},
            })
            table_obj = Table(table_name, MetaData(), autoload_with=engine, schema=target_schema)
            with engine.connect() as conn:
                rows = conn.execute(select(table_obj).limit(30)).fetchall()
            for idx, row in enumerate(rows, start=1):
                row_text = "\n".join(f"{k}: {v}" for k, v in dict(row._mapping).items())
                docs.append({
                    "source": f"db://{table_name}#row_{idx}",
                    "text": f"Table {table_name} row {idx}:\n{row_text}",
                    "metadata": {"source_type": "database_row", "table": table_name},
                })
        except Exception:
            pass
    return docs


def _ingest_onedrive(onedrive_path: str = "") -> list[dict]:
    try:
        from kendr.providers import get_microsoft_graph_access_token
        token = get_microsoft_graph_access_token()
        if not token:
            raise ValueError("Microsoft Graph access token not available. Configure Microsoft integration first.")
        from tasks.superrag_tasks import _iter_onedrive_files, _download_url_bytes
        from tasks.research_infra import parse_documents
        items = _iter_onedrive_files(token, onedrive_path, max_files=200)
        import tempfile
        docs: list[dict] = []
        with tempfile.TemporaryDirectory() as tmp:
            for idx, item in enumerate(items, start=1):
                url = item.get("@microsoft.graph.downloadUrl")
                if not url:
                    continue
                name = item.get("name", f"file_{idx}")
                dest = os.path.join(tmp, f"{idx:05d}_{name}")
                try:
                    data = _download_url_bytes(url)
                    Path(dest).write_bytes(data)
                    parsed = parse_documents([dest], continue_on_error=True)[0]
                    docs.append({
                        "source": f"onedrive://{item.get('id','')}/{name}",
                        "text": str(parsed.get("text", "") or ""),
                        "metadata": {"source_type": "onedrive", "name": name},
                    })
                except Exception:
                    pass
        return docs
    except Exception as exc:
        raise ValueError(f"OneDrive ingestion failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Status / diagnostics
# ---------------------------------------------------------------------------
def kb_status(kb_id: str) -> dict:
    kb = get_kb(kb_id)
    if not kb:
        return {"error": f"KB not found: {kb_id}"}

    job = get_index_job(kb_id)
    vc = kb.get("vector_config", {})
    rc = kb.get("reranker_config", {})

    # Check backend availability
    backend_ok = False
    backend_note = ""
    try:
        b = _get_backend_for_kb(kb)
        backend_ok = True
    except Exception as exc:
        backend_note = str(exc)

    return {
        "id": kb["id"],
        "name": kb["name"],
        "description": kb.get("description", ""),
        "status": kb.get("status", "empty"),
        "stats": kb.get("stats", {}),
        "sources": len(kb.get("sources", [])),
        "enabled_agents": kb.get("enabled_agents", []),
        "vector_backend": vc.get("backend", "chromadb"),
        "backend_ok": backend_ok,
        "backend_note": backend_note,
        "embedding_model": vc.get("embedding_model", _DEFAULT_EMBEDDING_MODEL),
        "reranker": rc.get("algorithm", "none"),
        "current_index_job": job,
    }
