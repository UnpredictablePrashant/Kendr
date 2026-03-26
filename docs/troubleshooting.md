# Troubleshooting

This guide covers the most common first-run and setup issues implied by the current runtime and docs.

## Start With Setup Status

When something does not appear to route correctly, check setup first:

```bash
superagent setup status
superagent agents list
superagent plugins list
```

The runtime filters unconfigured capabilities out of the available agent set.

## Working Directory Required

SuperAgent needs a working directory for artifacts and intermediate state.

If a run fails before execution, set one of:

```bash
superagent workdir here
```

or:

```bash
superagent run --current-folder "Create a short research brief on OpenAI."
```

## The Run Stops On A Plan

This is expected behavior.

Planning is a first-class stage, and the runtime can pause for approval before execution. Long-document workflows add a second approval stage for section planning.

## A Feature Does Not Trigger

Likely causes:

- the required provider is not configured
- the required local tool is not installed
- the feature belongs to a beta or experimental workflow and needs more setup than the core path

Check:

- `.env`
- `superagent setup status`
- [Integrations](integrations.md)

## Gateway Or Setup UI Is Not Reachable

Default ports:

- gateway: `8790`
- setup UI: `8787`

Start them explicitly if needed:

```bash
superagent gateway
superagent setup ui
```

## Browser Features Do Not Work Fully

Some browser features require Playwright plus installed browser binaries:

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

Headed browser mode also requires a real display session or virtual display support on Linux.

## Docker Stack Is Not Available

Docker is optional for normal local CLI use.

Use it when you want:

- containerized Qdrant
- MCP services
- the fuller service stack

If Docker is not installed, you can still use the CLI and local setup path for many workflows.

## Security Workflow Won't Start

Security workflows require explicit authorization flags and notes. Some deeper scans also depend on local tools like `nmap` or `zap-baseline.py`.

If a security feature is missing, confirm both:

- scope and authorization flags are present
- local tooling is installed or auto-install is enabled

## Verification Caveats

The current repo documents these limits:

- live end-to-end external API workflows are not fully verified
- Docker runtime execution is not fully verified
- MCP client interoperability is not fully verified
- heavy-load vector indexing behavior is not fully verified

Treat the stable workflows as the best-supported path today.

## Useful Recovery Commands

```bash
superagent --help
superagent help run
superagent setup status
superagent daemon --once
```

For repository-level checks:

```bash
python3 -m unittest discover -s tests -v
./scripts/ci_check.sh
```
