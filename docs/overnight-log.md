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

### Cycle 19 — Project access enforcement — ✅ done (expanded after review)

**Goal:** Close the standing security gap: any authenticated user could read/modify any reference and call any project endpoint, because none of the single-ref or per-project endpoints checked ownership. Memory has flagged this since Cycle 1.

**Initial v1 scope** (helpers + obvious endpoints):
- New `backend/app/services/access.py` with `user_can_access_project`, `user_can_access_reference`, `require_reference_access`, `require_project_access`. 404 (not 403) on foreign access so existence is not leaked.
- Wired to `GET/PATCH/DELETE /references/{id}`, `/file`, `/bibtex`, `/reprocess`, `/citations`. `/batch` filters in-memory to accessible refs.
- Wired to project endpoints: `GET/PATCH/DELETE /projects/{id}`, `/restructure-suggestions`, `/apply-restructure-action`, `/restructure-log`, `/digests*`, `/radar`. `list_projects` filters by `Project.created_by == current_user.id`.

**Critical review by Claude + Gemini in parallel** — first time the reviewers were both right and both vital. They flagged six surfaces I'd missed and one really sneaky bug:

| # | Issue | Found by | Severity |
|---|-------|----------|----------|
| 1 | `PATCH /projects/{id}/settings` unprotected — writes stored API keys, librarian prompt, model overrides | Both | Critical (cred leak) |
| 2 | `GET /projects/{id}/bibtex` (bulk export of every ref in project) | Claude | High |
| 3 | Watch-request endpoints (POST/GET/DELETE) unprotected | Claude | High |
| 4 | **`_resolve_project_id` cross-user injection** — user could move their ref into another user's project by passing a foreign `collection_id` | Gemini | High (silent data loss) |
| 5 | `GET /references` and `/stats/summary` returned all users' data when no `project_id` passed | Gemini | High |
| 6 | `routers/collections.py` entirely unprotected — anyone could rename/delete any collection | Gemini | High |
| 7 | `GET /search` unscoped | Gemini | High |
| 8 | NULL `created_by` lockout risk for legacy rows | Claude | Low (single-user deploy not affected) |

**Expanded (Cycle 19b) and pushed in the same commit:**
- All five missed project endpoints now require access.
- `_resolve_project_id` takes an optional `user_id` and verifies both the destination collection's project AND the resolved project belong to the user. All five call sites pass `current_user.id`.
- `list_references` and `stats` filter to `Reference.created_by == user.id OR Reference.project_id IN (user's projects)` via a `_user_scope_filter` helper.
- `collections.py` gets a `_require_collection_access` helper and a `_user_project_filter` subquery; all six endpoints check ownership.
- `search.py` now **requires** `project_id` and validates access — returns 400 if it's missing rather than silently leaking. The frontend `Library.jsx` already passes the active project, so no client-side breakage.
- `review.py` `get_queue` filters to the user's projects (plus orphan queue items with no project_id); `decide` checks queue-item project access.

**Verification:** Backend container picked up the changes via `--reload`, `/health` returns 200, no import errors. Single-user owns every project + reference in the existing data, so they retain full access. Test instance should behave identically to before for the legitimate user but reject foreign IDs.

**Still inherited, not fixed in this cycle:**
- Search-monitor endpoints already filter by `SearchMonitor.user_id == current_user.id` from earlier work, so they were already correct.
- Librarian chat endpoint (`/librarian/chat`) uses `project_id` from the request body — it would benefit from the same project-access check on that field. Noting for a future small follow-up.

---

### Cycle 18 — Restructure audit log — ✅ done

**Built:** `restructure_actions` audit table (project_id, user_id, action_type, action_payload JSONB, result JSONB, applied_at) with composite index `(project_id, applied_at DESC)`. Every successful apply through `apply-restructure-action` now records the full action payload + result via a `_record` helper called just before returning. For `merge_collections` the source's id/name are captured to local vars before `db.delete(src)` because the autoflush triggered by the INSERT would otherwise detach the object. New `GET /projects/{id}/restructure-log` returns the most recent N (default 20, capped 100) entries. RestructurePage gains an "Applied actions" card above the analyse button that lists each entry with a friendly summary ("Created 'AI Alignment' with 3 references", "Renamed 'X' → 'Y'", etc.) and a relative timestamp. Cache invalidation hooked so applies and the log stay in sync.

**Critical review** (Gemini + Claude in parallel) — both confirmed the implementation is sound:
- SQL injection / escaping: bind parameters with `CAST(:a AS jsonb)` + `json.dumps` is the correct pattern; no double-encoding on read since SQLAlchemy auto-decodes JSONB.
- Transactional integrity: `_record` is inside the request transaction, so if the audit insert fails the whole action rolls back — auditlog stays consistent with reality.
- `src_id_was` / `src_name_was` capture before delete: confirmed necessary (Claude's explanation — autoflush from the audit INSERT would expire the deleted `src`).

Claude flagged one real concern: the new GET endpoint doesn't verify project ownership. Same standing gap as every other `/projects/{id}/...` endpoint (Phase 4 membership work) — not a new vulnerability, but worth noting because audit-log payloads embed user_ids. NOT fixed in this cycle; piecemeal patching of this gap creates inconsistency. Will be addressed when the membership model lands.

Verdict: clean implementation, no code changes from review.

---

### Cycle 17 — Optional rejection reasons → monitor learning — ✅ done

**Built:** new `rejection_reason TEXT` column on `review_queue`. The `ReviewDecision` schema accepts an optional reason and the `decide` endpoint persists it (strip + truncate to 1000 chars). The Cycle 12 monitor-improvement prompt in `suggest_monitor_improvements` now renders rejected items as `- title  (reason: ...)` when a reason is present, with an explicit instruction to weight reasons heavily. Frontend `QueueItem` opens an inline reason input on Reject; shift-click skips the prompt for fast rejection; Enter to submit, Escape to cancel. Rejected items in the history view display the reason in italics under the card body.

**Critical review** (Gemini + Claude in parallel) — first cycle this run where the reviewers strongly disagreed.

Gemini flagged five issues; on cross-check four were false positives:
- "ReviewDecision missing action field" — FALSE. The action field is still present; Gemini hallucinated.
- "strip()[:1000] or None whitespace logic broken" — FALSE. Walked through: whitespace input becomes `""` after strip, then `"" or None` correctly returns None. Correct as written.
- "Empty string leaves old reason in place" — TRUE technically but out of UI scope (the input only appears on pending items, can't reject the same item twice).
- "getattr on item could fail if item is a dict" — FALSE. Items come from `.scalars().all()` which yields ORM instances, not dicts.

The one real bug Gemini did find: **loading state is never reset in a finally** in the `decide()` handler. If `onDecide` throws (network error mid-request) the spinner gets stuck forever. Fixed by wrapping the await in try/finally. Pre-existing pattern in the same file but worth fixing while I was here.

Claude found no real bugs and explicitly confirmed several design choices were correct (the `or None` fallback, the shift-click pattern, the 5th-param default not breaking callers). Verdict for tonight: Claude was the more reliable reviewer, but Gemini's false positives took ~5 min to disprove rather than just trusting either blindly. Running both is still the right call — the one real bug Gemini caught would have shipped otherwise.

---

### Cycle 16 — Ollama diagnostics panel — ✅ done

**Built:** `GET /config/ollama/diagnostics` that probes the configured URL + four common alternatives (`host.docker.internal`, `172.17.0.1`, `localhost`, `ollama:11434`) in parallel, measures latency, fetches `/api/ps` and `/api/tags` from whichever URL responds, and returns categorised remediation. Frontend gets a Diagnose button next to the existing Test button on the Ollama section, with a collapsible result panel showing per-URL probe status, currently-loaded models with VRAM size, and remediation steps.

**Critical review** (Gemini + Claude in parallel) caught three real bugs:

1. **`get_ollama_models(force=True)` used the configured URL** rather than the discovered `any_reachable`. So if the configured URL was dead but a fallback worked, `loaded_models` was populated but `installed_models` came back empty — exactly the scenario the user would be using diagnostics for. Both reviewers flagged it. Fixed by inlining the `/api/tags` call against `any_reachable` directly.
2. **Sequential probes blocked the request for up to 15s** (5 candidates × 3s timeout). Wrapped each probe in a coroutine and `asyncio.gather`. Worst case is now ~3s.
3. **Missing `X` icon import** would have crashed `ConfigPage.jsx` at runtime when the panel rendered (Gemini caught this — Claude missed).

Also fixed but minor: `size_mb` rendered `0` when both `size_vram` and `size` were missing — now returns `None` so the frontend can show "size unknown".

**SSRF noted but pre-existing:** the candidate list is hardcoded internal hosts and `settings.ollama_base_url` is env-sourced, so today this isn't exploitable. Worth keeping in mind if we ever expose "set Ollama URL via UI" — then the endpoint becomes an authenticated SSRF probe.
