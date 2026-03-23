# SampleTasks

This file shows example ways to run the multi-agent system using the `superagent` command.

## Quick Sanity Check

```bash
superagent --help
superagent agents list
superagent plugins list
```

Run one query:

```bash
superagent run "analyze this company and build a report"
```

Run with stricter step limit:

```bash
superagent run --max-steps 12 "summarize key risks for a fintech startup"
```

Get machine-readable output:

```bash
superagent run --json "build a short research brief on OpenAI"
```

## Case Study 1: Company Intelligence Brief

Goal: Produce a quick, source-backed brief on a company.

```bash
superagent run "Create an intelligence brief on Stripe: business model, products, competitors, recent strategy moves, and top risks."
```

Expected behavior:
- Routes through search/research/report-style agents when configured.
- Produces final narrative output in terminal.
- Stores run artifacts under `output/runs/<run_id>/`.

## Case Study 2: People + Organization Mapping

Goal: Map relationships between people, companies, and events.

```bash
superagent run "Research Satya Nadella's recent public interviews and connect themes to Microsoft product priorities."
```

Expected behavior:
- Uses entity/timeline/research flow when available.
- Produces structured notes and a summarized output.
- Artifacts and logs are saved per run.

## Case Study 3: Deal Advisory (Series A/B Screening)

Goal: Find and screen prospects in a target sector.

```bash
superagent run "Identify India-based B2B SaaS startups likely in Series A/B range, then provide a screened shortlist with rationale."
```

Expected behavior:
- Invokes deal-advisory agents (prospecting, stage screening, sector intelligence) when setup supports it.
- Produces shortlist + reasoning in final output.
- Writes intermediate outputs for traceability in the run folder.

## Case Study 4: Research Proposal and Prior Art

Goal: Compare a research idea against literature and patents.

```bash
superagent run "Review this proposal topic: low-cost edge AI for crop disease detection; summarize prior art, key papers, and novelty gaps."
```

Expected behavior:
- Uses proposal/literature/patent workflow if available.
- Generates evidence-oriented summary and novelty assessment.
- Saves step-by-step artifacts in `output/runs/<run_id>/`.

## Case Study 5: Defensive Security Review (Authorized Scope)

Goal: Generate a defensive security findings summary.

```bash
superagent run "For authorized target https://example.com, perform passive recon and provide top security findings with remediation priorities."
```

Expected behavior:
- Uses defensive security agents only when security setup is available.
- Produces findings-focused output with recommendations.
- Evidence artifacts are written to the run folder.

## Case Study 6: Travel Planning Flow

Goal: Build practical travel routing suggestions.

```bash
superagent run "Plan best travel options from Bangalore to Singapore next month with likely flight windows and routing advice."
```

Expected behavior:
- Travel agents are used only if required setup (including `SERP_API_KEY`) is configured.
- If unavailable, runtime will fall back to other eligible agents.

## Useful Companion Commands

Inspect one agent:

```bash
superagent agents show company_research_agent --json
```

Run daemon once (monitor pass):

```bash
superagent daemon --once
```

Run gateway mode:

```bash
superagent gateway
```

## Notes

- Agent routing is setup-aware: unconfigured integrations are filtered out automatically.
- Every run writes logs and artifacts into `output/runs/<run_id>/` (including `execution.log` and `final_output.txt`).
- Use `--json` when integrating `superagent` output into another app or pipeline.
