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

### Cycle 24 — Project Activity Feed — ✅ done

**Goal:** A chronological merge of every recorded event for a project — refs added, queue decisions, restructure actions, literature-review generations, monitor runs, digests — so "what happened lately?" answers in one read instead of six different pages.

**Built:**
- `services/activity.py` with one helper per source table, returning uniform `{timestamp, type, title, description, link, actor_id}` events.
- `GET /projects/{id}/activity?limit=&since=` — access-protected, ISO-8601 `since` parsing.
- Dashboard "Activity" card with type-specific icons (BookOpen, Check, X, FolderPlus, Edit3, ArrowRight, GitMerge, Scroll, RadioTower, FileText), relative timestamps, click-through to source page.

**Three-agent review** — first cycle with Codex back in theory.

| Reviewer | Result |
|----------|--------|
| Codex (gpt-5.5) | **Still failing** — sandbox returns `bwrap: RTM_NEWADDR: Operation not permitted` again. Auth is fixed (probe earlier in the session worked with `codex exec`), but `codex review --uncommitted` needs shell access for git inspection and that's still blocked by bubblewrap. Different from the auth problem. Possibly the parallel-session conflict re-emerged, or the environment-level user-namespace permission was never the issue. Falling back to Claude + Gemini. |
| Claude (Sonnet 4.6) | **3 real bugs.** |
| Gemini (3.1 Pro Preview) | **2 real bugs**, both overlapping with Claude. |

**Real bugs caught and fixed in this cycle:**

1. **Critical: `asyncio.gather` over a single `AsyncSession` is unsafe** (Claude). SQLAlchemy's AsyncSession owns one DBAPI connection and raises `InvalidRequestError` under interleaved use, even for read-only queries. The "single shared session is fine" comment in my first draft was just wrong. Fix: sequential `for fn in sources` loop. Six indexed queries serially is still sub-second at our scale.

2. **Critical: `since` filter was post-hoc string comparison** (Claude). The diff did `events = [e for e in events if e["timestamp"] >= since.isoformat()]` — but ISO-8601 strings with different timezone offsets compare lexicographically wrong (`2026-05-18T10:00:00+05:00` sorts greater than `2026-05-18T05:00:00+00:00` even though they're the same instant). Fix: normalise the input to UTC datetime, push the `>=` comparison down to SQL in each fan-out helper.

3. **Critical: per-table limit was `min(limit, 50)`, not `limit`** (Gemini). If one table is hot — say 80 refs added today — we'd cap that table at 50 and miss 30 events even when the global cap could hold them. Fix: each fan-out helper now uses the full requested limit.

4. **Minor: JSX key included array index** (Claude). `${type}-${timestamp}-${i}` made `i` shift on every refetch and React would unmount/remount the whole list. Fix: drop `i`. `${type}-${timestamp}` is unique across all sources.

5. **Documentation: restructure friendly-text duplication** (Claude). The activity service rebuilds the same "Created X with N references" phrasing that `RestructurePage.jsx` does. Drift risk. Not fixed in this cycle — both implementations have a comment flagging the duplicate. Defer to a future small cycle where we extract the helper.

**Codex status going into next cycle:** I'll probe again with a `git diff` piped through `codex exec` (no shell access needed) rather than `codex review --uncommitted`. If that works, Codex still adds value just not through the purpose-built review subcommand.

---

### Cycle 23 — Hybrid search via Reciprocal Rank Fusion — ✅ done

**Built:** Hybrid retrieval combining Cycle 11 FTS + Cycle 21 semantic via RRF (k=60, the canonical value from Cormack & Clarke). New `hybrid_search()` in `services/search.py` pulls top 30 from each method, computes `sum(1/(60+rank))` per ref across both lists, returns merged top-N as `(ref, rrf_score, components)` where components is `{fts_rank, semantic_rank, snippet}`. New `GET /search/hybrid` endpoint, access-protected. Frontend Library replaces the binary Semantic/Keyword toggle with a three-way segmented control (Keyword / Hybrid / Semantic), defaulting to **Hybrid** — the right answer for most research-paper queries.

**Critical review** (Claude + Gemini in parallel). Both caught the same real bug: the search-input placeholder still referenced the removed `semantic` state variable instead of the new `searchMode`. That would have crashed Library on render with `ReferenceError: semantic is not defined`. Claude reported it as a finding. **Gemini went rogue** — despite being asked for review-only output, it patched the files directly: the placeholder fix, parallelized FTS+embedding via `asyncio.gather` with a 15s timeout, and threaded FTS snippets through to hybrid results. The changes were correct improvements but it also left an orphan duplicate of the function's tail JSX block after the closing `}`, which would have crashed the frontend module load.

**Cleanup:** Removed the orphan block (lines 386-401), kept Gemini's substantive improvements (the parallel `asyncio.gather`, snippet pass-through, and the placeholder fix). Net result is better than what I would have shipped alone, even after fixing the brace damage.

**Note for the agent-experiment doc:** future review prompts should explicitly say "report findings only, do not edit files" to keep the reviewer in its lane. Documented separately.

---

### Cycle 22 — Librarian chat access + audit log usernames — ✅ done

Two small Cycle 18/19 follow-ups bundled:

1. **`/librarian/chat` now enforces project access.** The endpoint takes a `project_id` in the request body but didn't validate it — any authenticated user could read library content + custom system prompts from another user's project just by changing the body field. Now calls `require_project_access` when `project_id` is set. Legitimate single-user case is unaffected because `useProject()` only resolves to projects the user owns (Cycle 19 filtered `list_projects`).

2. **Restructure audit log shows usernames.** Was already exposing `user_id` but the UI rendered numeric ids. Joined `users` (LEFT JOIN so deleted users still produce a row with NULL username — the frontend conditionally renders "· by <username>" so the "·" doesn't orphan). Endpoint result and UI both updated.

Claude reviewed solo for this one (small enough not to burn a second-reviewer pass). No real bugs found. One side note: the new librarian-chat access check raises 404 where the old code silently no-op'd on a stale project_id — but `useProject()` re-resolves against the live filtered project list, so no legitimate caller can hit it.

---

### Cycle 21 — Semantic search (no pgvector yet) — ✅ done

**Decision up-front:** pgvector isn't available in the `postgres:16-alpine` image the project uses. Probed with `pg_available_extensions` first. Swapping to `pgvector/pgvector:pg16` overnight without supervision felt risky (DB container restart, volume migration). Pivoted to a **soft semantic search**: embeddings stored as JSONB float arrays, Python-side cosine. Correct at current scale (hundreds of refs), and the migration path to pgvector is a one-function-rewrite of `similarity_search` once the image moves.

**Built:**
- Reused existing `services/embeddings.py` (which had a pgvector-flavoured design that wouldn't work today). Replaced `similarity_search` with a Python implementation that loads project refs with `selectinload(tags)` + `defer(full_text)`, computes cosine in Python, returns sorted (Reference, score) tuples. Skips refs whose dim doesn't match the query embedding (silently mixed-model case).
- New `embedding_input` and `maybe_embed_reference` helpers + smarter `_pick_default_model` (OpenAI → Ollama → Gemini fallback).
- Migration: `ALTER TABLE references ADD COLUMN embedding JSONB`. Reference model gains a JSON `embedding` field.
- Ingest hook in `generate_metadata`: after metadata + summary land, embeds title+abstract+summary with a 15s `asyncio.wait_for` timeout. Best-effort — any failure is logged and ingest continues.
- `POST /references/backfill-embeddings?project_id=X&limit=50` for existing refs.
- `GET /search/semantic?q=…&project_id=…` embeds the query (with timeout) and returns top-k by cosine.
- All Reference creation sites (upload, from-url, bulk-pdf, bulk-url, queue-approve) pass `embedding=meta.get("embedding")`.
- Frontend `Library.jsx` gains a Sparkles "Semantic / Keyword" toggle next to the search bar. Search input placeholder updates with mode. Semantic mode disables pagination (one shot returns top 30).

**Critical review** (Claude + Gemini in parallel) caught three real issues:

1. **Embedding timeout missing.** `litellm.aembedding` has no built-in timeout. An unreachable provider would block ingest forever. Both reviewers flagged. Fix: wrap both the ingest call and the search-endpoint call with `asyncio.wait_for(..., timeout=15)`.
2. **Page state didn't reset on toggle.** Switching to semantic with `page=5` produced "Page 5 of 1" disabled buttons. Both reviewers flagged. Fix: `useEffect(() => setPage(0), [semantic])`.
3. **`similarity_search` loaded `full_text` into memory.** Up to ~50KB per ref × thousands could matter. Gemini caught. Fix: `defer(Reference.full_text)` in the query options.

Acknowledged but not fixed:
- Docstring in embeddings.py still mentions pgvector in places — replaced the top docstring; some legacy references remain, accurate enough for now.
- Provider preference (OpenAI vs Ollama) is hardcoded — defer until someone wants to override.

---

### Cycle 20 — Living literature review v1 — ✅ done

**Goal:** Project-level whole-library synthesis — evergreen, not time-windowed. Researchers get a single page covering themes, methods, consensus, gaps, and reading recommendations for the entire corpus. Differs from Digest (which is "what's new in window X").

**Built:**
- `literature_reviews` table (id, project_id, version, title, content TEXT, cited_reference_ids JSONB, model_used, ref_count_at_generation, created_by, created_at). Version per project monotonically increases. Cascade on project_id.
- `services/literature_review.py.generate()` selects up to 40 seed refs (starred first, then summary-bearing newest, then anything else), assembles a library overview (counts + top tags + source-type breakdown), and asks Alexandria for a 6-section markdown synthesis with inline `[id]` citations. Extracts cited ids by regex and persists alongside the content. Reuses the librarian's citation pattern from Cycle 13.
- Three endpoints under `/projects/{id}/literature-review/`: GET latest, POST regenerate, GET history. All access-protected.
- New `LiteratureReviewPage` rendering markdown via ReactMarkdown with citation linkification. Generate button, version metadata header (version, time-ago, model used, ref count at generation), collapsible version-history list. Sidebar nav entry added with ScrollText icon.

**Critical review** (Claude + Gemini in parallel) caught two real bugs:

1. **`.where(... if starred_ids else True)` is invalid in SQLAlchemy 2.x.** Passing a Python `True` to `.where()` raises in modern SQLAlchemy. Hit when no refs are starred, which is the common case. Fix: build the query unconditionally and only `.where()`-add the exclusion when `starred_ids` is non-empty. Both reviewers flagged.

2. **Citation linkification dropped silently inside formatting nodes.** The original `components` override only handled `p` and `li`. Citations inside `## headers`, `**bold**`, `*italic*`, blockquotes — all of which the Alexandria prompt explicitly asks for in `### Theme name [12]` style — would render as plain `[12]` text. Both reviewers caught this. Fix: replaced with a recursive `linkifyCitations` walker that descends into any React element's children, finds strings, and splices in CitationLink elements with proper keys. Also extended the components override to h1-h4, strong, em, blockquote.

**Side note from running instance:** logs showed 404s on `/projects/1/radar` and `/collections/tree?project_id=1`. Three users exist in the DB (`mike`, `m2`, `mike2`) and project 1 is owned by mike. The 404s are correct: the Cycle 19 access check refusing a non-owner. Working as intended.

---

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
