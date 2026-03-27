# Changelog

All notable changes to this repository should be documented in this file.

The project is still pre-`1.0`, and older history before this file may be incomplete.

The format is inspired by Keep a Changelog and uses simple repository-focused sections.

## [Unreleased]

### Added

- a versioned external plugin SDK contract with manifest guidance and example agent/provider plugins
- a unified integration lifecycle covering declaration, configuration, setup detection, health reporting, routing eligibility, docs, and tests
- a single developer verification entrypoint with explicit `compile`, `unit`, `smoke`, `docs`, `docker`, and `integration` buckets
- product-facing workflow walkthroughs for deep research, local-drive intelligence, `superRAG`, coding delivery, and local command execution
- this public repo layer: contributing guidance, release checklist, and GitHub issue/PR templates

### Changed

- repository docs now position the five core workflows as the recommended entry path
- plugin discovery now exposes SDK/runtime metadata through registry, CLI, and gateway surfaces
- verification docs and CI now align on `python scripts/verify.py`
- setup-aware routing and integration docs now share one declared contract

### Fixed

- validation gaps between documented setup steps and actual runtime verification expectations
- plugin metadata handling for external contributors who need a stable manifest contract

## [0.1.0]

### Added

- initial Python package metadata and CLI entrypoint
- setup-aware registry, runtime orchestration, and persistence foundations
- built-in workflow agents, plugin loading, gateway surface, and docs set
