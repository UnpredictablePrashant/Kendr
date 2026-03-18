# Super Agent Research Stack

This project now includes a deeper research stack for investigating people, companies, organizations, groups, and related entities.

## New Agents

- `access_control_agent`
- `web_crawl_agent`
- `document_ingestion_agent`
- `ocr_agent`
- `entity_resolution_agent`
- `knowledge_graph_agent`
- `timeline_agent`
- `source_verification_agent`
- `people_research_agent`
- `company_research_agent`
- `relationship_mapping_agent`
- `news_monitor_agent`
- `compliance_risk_agent`
- `structured_data_agent`
- `memory_index_agent`
- `citation_agent`

## Required Environment Variables

- `OPENAI_API_KEY`
  Used for orchestration, structured extraction, OCR via vision, and embeddings.
- `SERP_API_KEY`
  Used for Google search and news retrieval.

## Optional Environment Variables

- `OPENAI_MODEL`
- `OPENAI_VISION_MODEL`
- `OPENAI_EMBEDDING_MODEL`
- `QDRANT_URL`
- `QDRANT_COLLECTION`
- `RESEARCH_USER_AGENT`

## Docker Services

- `qdrant`
  Vector database for semantic memory.
- `app`
  Main orchestration runtime.
- `research-mcp`
  MCP server for search, crawl, document parsing, OCR, and entity brief tools.
- `vector-mcp`
  MCP server for vector indexing and semantic retrieval.

## Startup

```bash
docker compose up --build
```

## Current API Coverage

No extra paid APIs are required beyond OpenAI and SerpAPI for the current implementation.

## Recommended Future Integrations

If you want stronger corporate and people intelligence, these are the next APIs to consider:

- People Data Labs
- Crunchbase
- Clearbit or Apollo
- OpenCorporates
- SEC/EDGAR connectors
- sanction or watchlist feeds
- Firecrawl or Browserbase for richer site extraction
