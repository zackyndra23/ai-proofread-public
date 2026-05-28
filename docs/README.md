# `docs/` — AI Proofread documentation

Cross-session engineering reference for the AI Proofread service. Loaded
alongside `CLAUDE.md` at the repo root.

## What's here

| File | Purpose |
|---|---|
| [PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md) | Identity, tech stack, repo layout, tenants/locales, how to run locally |
| [PIPELINE.md](./PIPELINE.md) | Full pipeline walkthrough: HTML Freeze → Mask (3 layers) → LLM → Unmask → Reformat → Reverse HTML → Persist |
| [ENDPOINTS.md](./ENDPOINTS.md) | All HTTP routes, headers, DTOs, request/response shapes, examples |
| [CONVENTIONS.md](./CONVENTIONS.md) | Hard invariants (token preservation, shared counters, span overlap, `+`-freeze, ID mobile regex constraints, WIB timestamps) |
| [ENVIRONMENT.md](./ENVIRONMENT.md) | Env var reference grounded in `app/core/config.py` |
| [superpowers/specs/](./superpowers/specs/) | Design specs for individual features |

## How this set differs from `README.md`

`README.md` at the repo root is the **product / onboarding** README — written
for a visitor who wants to understand what the service does and how to run it.
The files in this folder are the **engineering reference**, written against the
code as it actually exists. Where the two disagree, trust this folder and the
code.

## Maintenance

Each file carries its own `Last updated` line at the top. After any change,
update the relevant file(s) and bump that line. See
[`CONVENTIONS.md` §14](./CONVENTIONS.md#14-doc-maintenance-contract) for the
full mapping of change-type → doc-to-update.

`CLAUDE.md` at the repo root should stay short and point here for detail.
