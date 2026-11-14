# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Web API (Python + FastAPI) that retrieves Antarctic weather data from the AEMET OpenData API, with an SQLite cache and a TypeScript front-end.

## Language

- Communicate with the developer in **Spanish**.
- Everything in the repository is in **English**: code, comments, docstrings, README, ADRs and commit messages.

## Working agreement

- Do not implement anything until the developer has approved the plan for that step.
- For every non-trivial decision, explain the alternatives considered and their trade-offs, so the developer can defend and modify it without assistance.
- For subtle topics (time zones, DST, caching, concurrency), stop and check understanding before moving on.
- Ask questions in small batches, one topic at a time, and never skip a point.
- Mark anything uncertain as **"to verify"** instead of assuming it, especially AEMET API details (endpoints, parameters, formats, limits, station identifiers).
- Never hardcode secrets. Configuration comes from environment variables; `.env` is git-ignored and `.env.example` documents every variable.

## Delivery order

The goal is to deliver everything. Work block by block: each block is finished, tested and documented before the next one starts. Never leave several blocks half-done in parallel.

1. **Part 1**: core API, DST test suite, demo mode, README.
2. **Part 2**: SQLite cache, resilience, logging.
3. **Part 3**: TypeScript front-end.
4. **Extras**: wind-energy metrics, CSV export, CI polish, other nice-to-haves.

Flag early if the plan does not fit the deadline. Anything left unfinished is listed as a TODO in the README, never delivered half-broken.

## Documentation

- The README is living documentation: update it in the same step a decision is implemented, inside the relevant section. Explain what was decided and why (context, alternatives, reasoning, consequences).
- Never write the README as a changelog and never reference commits ("Commit 1: ...", "In this commit ..."). When a decision changes, rewrite the text so it reflects the current state.
- Keep the README consistent with the ADRs in `docs/adr/`: the README gives the short explanation and links to the ADR for the full reasoning. Superseded decisions are recorded in the ADRs.
- Remind the developer to update `docs/AI_USAGE.md` at each milestone.

## Commits

- Small, meaningful commits following [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`, `ci:`, `build:`).
- Propose the commit message at each step, then ask the developer for permission to commit and push. Create the commit and push it only after explicit approval.

## Settled decisions

- **Stack**: Python + FastAPI.
- **Input time zone**: datetimes without an explicit time zone or offset are interpreted as `Europe/Madrid`. Every response states how the input was interpreted.
- **Output time zone**: datetimes are returned in `Europe/Madrid` and always include the UTC offset (e.g. `+02:00`).
- **Internal time handling**: always UTC with timezone-aware datetimes. Naive datetimes are never used.
- **Data quality**: aggregated rows include a `samples` column with the number of measurements used (computed at query time, not stored).
- **Demo mode**: the whole application runs without an AEMET API key.
- **Commands**: a Makefile provides shortcuts; the README lists the full equivalent command for every target.

## Out of scope

Do not implement. Mention only in the README as future evolution:
authentication/authorization, Kubernetes or cloud deployment, microservices, message queues, real PostgreSQL/Redis deployments, internationalization (i18n).

## Code quality

- Type hints everywhere.
- Transformation logic (parsing, time zone conversion, aggregation) lives in pure functions.
- Tests never call the real AEMET API: upstream calls are mocked or replayed from recorded fixtures.
