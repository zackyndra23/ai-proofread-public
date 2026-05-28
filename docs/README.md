# `docs/` — AI Proofread documentation

Cross-session knowledge base for the **AItegrity Core — AI Proofread** service. Loaded alongside `CLAUDE.md` at the repo root and the project memory in `~/.claude/projects/.../memory/`.

## What's here

| File | Purpose |
|---|---|
| [PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md) | Identity, tech stack, repo layout, tenants/locales, branch strategy, recent work, how to run locally |
| [PIPELINE.md](./PIPELINE.md) | Full pipeline walkthrough: HTML Freeze → Mask (3 layers) → LLM → Unmask → Reformat → Reverse HTML → Persist |
| [ENDPOINTS.md](./ENDPOINTS.md) | All HTTP routes, headers, DTOs, request/response shapes, examples |
| [CONVENTIONS.md](./CONVENTIONS.md) | Hard invariants (token preservation, shared counters, span overlap, `+`-freeze, ID mobile regex constraints, WIB timestamps) |
| [ENVIRONMENT.md](./ENVIRONMENT.md) | Env var reference grounded in `app/core/config.py`; flags discrepancies with the README |

## How this set differs from `README.md`

`README.md` at the repo root is the **product / onboarding** README — written for someone integrating with the service. The files in this folder are the **engineering reference**, written against the code as it actually exists. Where the two disagree (and they do), trust this folder and the code; reconcile the README in the same change that introduces the divergence.

Known divergences as of `Last updated` 2026-04-28:

- DTO accepts locales `en | id | ms` (no `th`, `ms` not `my`). README still says `en, id, th, my`.
- Endpoints live under `/v1/...` only. README's `/aitegrity-core/aiproofread/`, `/html_tag_freeze`, `/reverse_html_tag`, `/html_preview`, `/pii_datamasking`, `/llm-claude`, `/unmask`, `/reformating` are not in the active routes.
- `RATE_LIMIT_WINDOW_SEC` defaults to `60` in code; README example uses `1`.
- Security toggles (`SQL_INJECTION`, `HTML_FORMAT`, `REJECT_SYMBOL_ONLY`) and the semantic-text guard (`TEXT_SEMANTIC_MIN_CHARS`, `TEXT_SEMANTIC_MIN_WORDS`, `LLM_SEMANTIC_VALIDATION`) are not in the README.

## Maintenance

Each file carries its own `Last updated` line at the top. After any change, update the relevant file(s) and bump that line. See [`CONVENTIONS.md` §14](./CONVENTIONS.md#14-doc-maintenance-contract) for the full mapping of change-type → doc-to-update.

`CLAUDE.md` at the repo root should stay short and point here for detail.
