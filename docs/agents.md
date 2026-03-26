# Agents

This page documents the built-in agent families and how they are exposed in the runtime.

## How Agent Discovery Works

Built-in agents are discovered dynamically from task modules. A function is registered as an agent when:

- it lives in a scanned task module
- its name ends with `_agent`
- it is not excluded by the discovery layer

When present, `AGENT_METADATA` supplies:

- description
- skills
- input keys
- output keys
- requirements

## Workflow Status By Family

### Stable

- core planning, worker, reviewer, and report flow
- local-drive intelligence
- `superRAG`
- core intelligence and evidence-building flow

### Beta

- deep research
- long-document generation
- gateway/session routing
- communication surfaces
- monitoring and heartbeat
- AWS workflows
- travel workflows
- authorized defensive security workflow
- research proposal and patent workflows
- deal-advisory workflows

### Experimental

- generated-agent scaffolding and runtime factory flow
- voice and audio workflows
- future-facing social ecosystem analysis ideas described in the repo

## Full Built-In Inventory

### Core Workflow

- `planner_agent`
- `worker_agent`
- `reviewer_agent`
- `report_agent`
- `agent_factory_agent`

### Utility And Execution

- `os_agent`
- `coding_agent`
- `master_coding_agent`
- `excel_agent`
- `google_search_agent`
- `deep_research_agent`
- `long_document_agent`
- `reddit_agent`
- `location_agent`

### Intelligence And Research

- `superrag_agent`
- `access_control_agent`
- `web_crawl_agent`
- `document_ingestion_agent`
- `local_drive_agent`
- `ocr_agent`
- `image_agent`
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

### Research Documents And Patents

- `literature_search_agent`
- `patent_search_agent`
- `proposal_review_agent`
- `prior_art_analysis_agent`
- `claim_evidence_mapping_agent`

### Deal Advisory And Fundraising

- `prospect_identification_agent`
- `funding_stage_screening_agent`
- `sector_intelligence_agent`
- `company_meeting_brief_agent`
- `investor_positioning_agent`
- `financial_mis_analysis_agent`
- `deal_materials_agent`
- `investor_matching_agent`
- `investor_outreach_agent`

### Security Assessment

- `security_scope_guard_agent`
- `recon_agent`
- `web_recon_agent`
- `api_surface_mapper_agent`
- `scanner_agent`
- `exploit_agent`
- `evidence_agent`
- `unauthenticated_endpoint_audit_agent`
- `idor_bola_risk_agent`
- `security_headers_agent`
- `tls_assessment_agent`
- `dependency_audit_agent`
- `sast_review_agent`
- `prompt_security_agent`
- `ai_asset_exposure_agent`
- `security_findings_agent`
- `security_report_agent`

### Communication And Collaboration

- `communication_scope_guard_agent`
- `gmail_agent`
- `drive_agent`
- `telegram_agent`
- `whatsapp_agent`
- `slack_agent`
- `microsoft_graph_agent`
- `communication_hub_agent`

### Gateway And Runtime

- `channel_gateway_agent`
- `session_router_agent`
- `browser_automation_agent`
- `interactive_browser_agent`
- `scheduler_agent`
- `notification_dispatch_agent`
- `whatsapp_agent`

### Monitoring

- `heartbeat_agent`
- `monitor_rule_agent`
- `stock_monitor_agent`

### AWS

- `aws_scope_guard_agent`
- `aws_inventory_agent`
- `aws_cost_agent`
- `aws_automation_agent`

### Travel And Transport

- `flight_tracking_agent`
- `transport_route_agent`
- `travel_hub_agent`

### Voice And Audio

- `voice_catalog_agent`
- `speech_generation_agent`
- `speech_transcription_agent`

## Internal Runtime Helpers

The agent-factory flow also uses an internal runtime helper:

- `dynamic_agent_runner`

This is part of the generated-agent scaffold-and-run path, but it is not a built-in discovered `*_agent` entrypoint.

## Recommended Starting Point

For new users, start with:

- deep research
- local-drive intelligence
- `superRAG`
- coding project builder
- local command execution

Then expand into the more setup-heavy domain workflows as needed.
