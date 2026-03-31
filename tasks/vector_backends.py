from __future__ import annotations

import os
import sys
import urllib.request
import urllib.error
from abc import ABC, abstractmethod

DEFAULT_VECTOR_COLLECTION = os.getenv("QDRANT_COLLECTION", "research_memory")
DEFAULT_QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")

_BACKEND_CACHE: "VectorBackend | None" = None


class VectorBackend(ABC):
    @abstractmethod
    def ensure_collection(self, collection_name: str, vector_size: int = 1536):
        ...

    @abstractmethod
    def upsert(self, collection_name: str, records: list[dict], vectors: list[list[float]]) -> dict:
        ...

    @abstractmethod
    def search(self, collection_name: str, query_vector: list[float], top_k: int = 5) -> list[dict]:
        ...


class ChromaBackend(VectorBackend):
    def __init__(self) -> None:
        import chromadb

        working_dir = os.getenv("KENDR_WORKING_DIR") or "."
        persist_path = os.path.join(working_dir, ".chroma")
        self._client = chromadb.PersistentClient(path=persist_path)
        self._collections: dict[str, object] = {}

    def _get_collection(self, collection_name: str, vector_size: int = 1536):
        if collection_name not in self._collections:
            self._collections[collection_name] = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[collection_name]

    def ensure_collection(self, collection_name: str, vector_size: int = 1536):
        return self._get_collection(collection_name, vector_size)

    def upsert(self, collection_name: str, records: list[dict], vectors: list[list[float]]) -> dict:
        collection = self._get_collection(collection_name)
        ids = []
        embeddings = []
        documents = []
        metadatas = []
        for index, (record, vector) in enumerate(zip(records, vectors)):
            payload = dict(record.get("payload", {}))
            payload["text"] = record["text"]
            payload["source"] = record.get("source", "")
            record_id = record.get("id")
            if record_id is None:
                record_id = abs(hash(f"{record.get('source', '')}:{index}:{record['text'][:64]}"))
            ids.append(str(record_id))
            embeddings.append(vector)
            documents.append(record["text"])
            clean_meta = {k: (str(v) if not isinstance(v, (str, int, float, bool)) else v) for k, v in payload.items()}
            metadatas.append(clean_meta)
        collection.upsert(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
        return {"indexed": len(ids), "collection": collection_name}

    def search(self, collection_name: str, query_vector: list[float], top_k: int = 5) -> list[dict]:
        collection = self._get_collection(collection_name)
        count = collection.count()
        if count == 0:
            return []
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=min(top_k, count),
            include=["documents", "metadatas", "distances"],
        )
        matches = []
        for doc, meta, distance in zip(
            results.get("documents", [[]])[0],
            results.get("metadatas", [[]])[0],
            results.get("distances", [[]])[0],
        ):
            score = 1.0 - float(distance)
            matches.append({
                "score": score,
                "source": (meta or {}).get("source", ""),
                "text": doc or "",
                "metadata": meta or {},
            })
        return matches


class QdrantBackend(VectorBackend):
    def __init__(self, url: str) -> None:
        self._url = url
        self._client_cache = None

    def _client(self):
        if self._client_cache is None:
            from qdrant_client import QdrantClient
            self._client_cache = QdrantClient(url=self._url)
        return self._client_cache

    def ensure_collection(self, collection_name: str, vector_size: int = 1536):
        from qdrant_client.models import Distance, VectorParams

        client = self._client()
        existing = [item.name for item in client.get_collections().collections]
        if collection_name not in existing:
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
        return client

    def upsert(self, collection_name: str, records: list[dict], vectors: list[list[float]]) -> dict:
        from qdrant_client.models import PointStruct

        vector_size = len(vectors[0]) if vectors else 1536
        client = self.ensure_collection(collection_name, vector_size=vector_size)
        points = []
        for index, (record, vector) in enumerate(zip(records, vectors)):
            payload = dict(record.get("payload", {}))
            payload["text"] = record["text"]
            payload["source"] = record.get("source", "")
            record_id = record.get("id")
            if record_id is None:
                record_id = abs(hash(f"{record.get('source', '')}:{index}:{record['text'][:64]}"))
            points.append(PointStruct(id=record_id, vector=vector, payload=payload))
        client.upsert(collection_name=collection_name, points=points)
        return {"indexed": len(points), "collection": collection_name}

    def search(self, collection_name: str, query_vector: list[float], top_k: int = 5) -> list[dict]:
        client = self.ensure_collection(collection_name)
        results = client.query_points(collection_name=collection_name, query=query_vector, limit=top_k)
        points = getattr(results, "points", results)
        matches = []
        for item in points:
            payload = getattr(item, "payload", {}) or {}
            matches.append({
                "score": getattr(item, "score", None),
                "source": payload.get("source", ""),
                "text": payload.get("text", ""),
                "metadata": payload,
            })
        return matches


def _qdrant_reachable(url: str, timeout: float = 2.0) -> bool:
    try:
        req = urllib.request.Request(f"{url.rstrip('/')}/healthz", method="GET")
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


def get_vector_backend() -> VectorBackend:
    global _BACKEND_CACHE
    if _BACKEND_CACHE is not None:
        return _BACKEND_CACHE

    qdrant_url = os.getenv("QDRANT_URL", "").strip()
    if qdrant_url and _qdrant_reachable(qdrant_url):
        print(f"[vector] Using Qdrant at {qdrant_url}", file=sys.stderr)
        _BACKEND_CACHE = QdrantBackend(url=qdrant_url)
        return _BACKEND_CACHE

    try:
        print("[vector] Using ChromaDB (local)", file=sys.stderr)
        _BACKEND_CACHE = ChromaBackend()
        return _BACKEND_CACHE
    except ImportError:
        pass

    if qdrant_url:
        print(f"[vector] Falling back to Qdrant at {qdrant_url} (chromadb not installed)", file=sys.stderr)
        _BACKEND_CACHE = QdrantBackend(url=qdrant_url)
    else:
        print("[vector] Falling back to Qdrant at default URL (chromadb not installed, QDRANT_URL not set)", file=sys.stderr)
        _BACKEND_CACHE = QdrantBackend(url=DEFAULT_QDRANT_URL)
    return _BACKEND_CACHE
