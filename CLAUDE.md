# CLAUDE.md

Instructions for Claude Code (and any Claude-based agent) working in this
repository.

## Read this first, every session, in this order

1. `docs/context.md` — the project spec: architecture, schema, dataset,
   scope. Source of truth for *what* this project is.
2. `docs/context.md` §15 — status log, what's actually been built so far.
3. `docs/prompts/master.md` — the global operating rules (scope
   discipline, memory/status-log discipline, environment, database
   rules, code style, testing, definition-of-done discipline). These
   rules apply in full to everything you do here and are **not**
   repeated in this file.
4. `docs/prompts/phase-N-*.md` — the specific task for this session.

This repo is built across multiple memoryless chat sessions and multiple
tools (Claude Code, Codex, Antigravity). `master.md` covers how to behave
given that. Read it before writing any code — this file only adds what's
specific to Claude.

## Claude-specific notes

- If you use Claude's Skills or subagent features while working in this
  repo, they're incidental tooling — nothing in this project's
  architecture depends on Claude-specific capabilities. Don't introduce
  a dependency that would break the project if a different tool (Codex,
  Antigravity) picked up the next phase.
- Where `AGENTS.md` and this file overlap, follow both. If you find an
  actual contradiction between them, or between either of them and
  `master.md`, treat that as a bug — flag it and fix the stale file
  rather than silently picking one.
- Setup commands (venv, install, migrate, run) live in `AGENTS.md` —
  not duplicated here, to avoid the two files drifting.
