# Overnight Development Log — 2026-05-16/17

User handed off at ~21:00 local with: "continue revision and development overnight. Pace yourself, do each review on the hour, keep notes of the bug findings and developments. Catch you in the morning."

Each cycle below = roughly one hour: pick next thing, implement, critical review with another agent, apply fixes, commit + push, write up. Long-form rationale lives in `docs/development-log.md` and `docs/design-decisions.md` as usual; this file is the running log for the night so the morning summary is one read.

## Plan (rough — may shift if a cycle reveals something better to do)

- Cycle 16: Ollama diagnostics panel (operational tooling — user has hit Ollama issues before)
- Cycle 17: Optional rejection reason at decide-time (feeds monitor learning from Cycle 12)
- Cycle 18: Restructure audit log (option C deferred from Cycle 14)
- Cycle 19: Project access enforcement (security gap — standing item)
- Cycle 20: Living literature review v1 — project-level synthesis
- Cycle 21: pgvector hybrid search skeleton
- Cycle 22+: catch-up / polish / morning summary

If any cycle uncovers something that wants more time, I'll slow down rather than push half-baked work.

## Cycle log

### Cycle 16 — Ollama diagnostics panel — ✅ done

**Built:** `GET /config/ollama/diagnostics` that probes the configured URL + four common alternatives (`host.docker.internal`, `172.17.0.1`, `localhost`, `ollama:11434`) in parallel, measures latency, fetches `/api/ps` and `/api/tags` from whichever URL responds, and returns categorised remediation. Frontend gets a Diagnose button next to the existing Test button on the Ollama section, with a collapsible result panel showing per-URL probe status, currently-loaded models with VRAM size, and remediation steps.

**Critical review** (Gemini + Claude in parallel) caught three real bugs:

1. **`get_ollama_models(force=True)` used the configured URL** rather than the discovered `any_reachable`. So if the configured URL was dead but a fallback worked, `loaded_models` was populated but `installed_models` came back empty — exactly the scenario the user would be using diagnostics for. Both reviewers flagged it. Fixed by inlining the `/api/tags` call against `any_reachable` directly.
2. **Sequential probes blocked the request for up to 15s** (5 candidates × 3s timeout). Wrapped each probe in a coroutine and `asyncio.gather`. Worst case is now ~3s.
3. **Missing `X` icon import** would have crashed `ConfigPage.jsx` at runtime when the panel rendered (Gemini caught this — Claude missed).

Also fixed but minor: `size_mb` rendered `0` when both `size_vram` and `size` were missing — now returns `None` so the frontend can show "size unknown".

**SSRF noted but pre-existing:** the candidate list is hardcoded internal hosts and `settings.ollama_base_url` is env-sourced, so today this isn't exploitable. Worth keeping in mind if we ever expose "set Ollama URL via UI" — then the endpoint becomes an authenticated SSRF probe.
