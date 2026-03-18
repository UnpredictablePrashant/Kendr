import os

from fastmcp import FastMCP

from tasks.research_infra import DEFAULT_QDRANT_COLLECTION, search_memory, upsert_memory_records


mcp = FastMCP("super-agent-vector")


@mcp.tool
def index_texts(source: str, texts: list[str], collection_name: str = DEFAULT_QDRANT_COLLECTION) -> dict:
    records = [
        {
            "source": source,
            "text": text,
            "payload": {"source_type": "mcp_index", "source": source, "chunk_index": index},
        }
        for index, text in enumerate(texts)
        if text and text.strip()
    ]
    return upsert_memory_records(records, collection_name=collection_name)


@mcp.tool
def semantic_search(query: str, top_k: int = 5, collection_name: str = DEFAULT_QDRANT_COLLECTION) -> list[dict]:
    return search_memory(query, top_k=top_k, collection_name=collection_name)


if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8002"))
    transport = os.getenv("MCP_TRANSPORT", "http")
    mcp.run(transport=transport, host=host, port=port)
