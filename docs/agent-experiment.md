# Agent Experiment Log

A running log of experiments delegating SciLibrarian work to external CLI agents (gemini CLI, claude CLI, codex CLI). Each entry captures the spec handed to the agent, what came back, what needed correction, and the verdict on whether to keep using that agent for similar work.

## Setup

Agents available on this machine (as of 2026-05-16):

| CLI | Version | Path |
|-----|---------|------|
| `gemini` | 0.42.0 | `/home/mike/.local/opt/node-v24.14.1-linux-x64/bin/gemini` |
| `claude` | 2.1.143 (Claude Code) | `/home/mike/.local/bin/claude` |
| `codex` | codex-cli 0.130.0 | `/home/mike/.local/opt/node-v24.14.1-linux-x64/bin/codex` |

Working principle: the orchestrating agent (this Claude session) writes a self-contained spec, the delegated agent edits the working tree, and I review the diff before committing. Worktree isolation is an option if a task carries higher risk.

---

## Experiment 1 — Bulk BibTeX export per project / collection

**Date:** 2026-05-16
**Delegated to:** Gemini CLI 0.42.0, `--approval-mode auto_edit`
**Working tree:** main branch, clean before experiment

### Why this task

Small, well-scoped, no frontend work, no migrations, single concern, reuses an existing helper (`_to_bibtex`). Easy to spec and easy to review.

### Spec handed to Gemini

```
TASK: Add two FastAPI endpoints that export multiple references as BibTeX.

Endpoints:
  - GET /projects/{project_id}/bibtex   → all references with this project_id
  - GET /collections/{collection_id}/bibtex → all references with this collection_id

Both return:
  - Content-Type: text/x-bibtex; charset=utf-8
  - Content-Disposition: attachment; filename="project_<id>.bib" (or "collection_<id>.bib")
  - Body: concatenation of BibTeX entries separated by blank lines

Implementation rules:
  - Reuse the existing `_to_bibtex(ref: Reference) -> str` from
    backend/app/routers/references.py (import it, do NOT copy or rewrite).
  - Add /projects/{id}/bibtex to backend/app/routers/projects.py
  - Add /collections/{id}/bibtex to backend/app/routers/collections.py
  - Use the existing DB and CurrentUser dependencies (see backend/app/dependencies.py).
  - Query references via SQLAlchemy async select; eager-load
    Reference.tags via selectinload so the helper doesn't trigger lazy loads.
  - Return 404 if the project / collection doesn't exist.
  - If a project / collection has zero references, return an empty body (200), not 404.

Out of scope:
  - No frontend changes.
  - No new tests.
  - No new helper functions.
  - No changes to existing endpoints or _to_bibtex.

Style:
  - Match the existing code style in those files (async def, type hints,
    snake_case, no comments unless non-obvious).

When done:
  - Run `python3 -c "import ast; [ast.parse(open(f).read()) for f in
    ['backend/app/routers/projects.py','backend/app/routers/collections.py']]"`
    to confirm both files still parse.
  - Stop. Do not commit. I will review and commit.
```

### Result

Gemini completed the task in a single non-interactive run (`gemini -p "..." --yolo --skip-trust`) with no human in the loop. It edited both target files, ran the syntax check I asked it to, and produced a brief summary at the end.

Wall-clock: ~30 seconds.

Tool calls observed in the output:
- One `replace` call failed with "expected 1 occurrence but found 3" — Gemini recovered automatically (presumably switched to a larger context window for the edit) and the second attempt succeeded.
- Final run of the `ast.parse` syntax check.

### Review notes

The functional behaviour matched the spec:
- ✅ Both endpoints created at the right paths.
- ✅ `_to_bibtex` imported from `app.routers.references` (not copied).
- ✅ `selectinload(Reference.tags)` used to avoid lazy loads.
- ✅ 404 on missing project / collection.
- ✅ Empty body (200) on zero references — `"\n\n".join([])` returns `""`.

Style nits I cleaned up by hand after Gemini stopped:
1. **Inline imports inside the function body** — `from app.models.reference import Reference`, `from sqlalchemy.orm import selectinload`. Defensible (avoids any future circular-import risk) but the file already imports model classes at module top, so I hoisted them up for consistency.
2. **Redundant `Content-Type` header** — both `media_type="text/x-bibtex"` *and* `headers={"Content-Type": "text/x-bibtex; charset=utf-8"}`. FastAPI ends up using the header, but having two sources of truth is bug-prone. Collapsed to `media_type="text/x-bibtex; charset=utf-8"`.
3. **Docstrings added even though the file doesn't use them** — minor style mismatch with the surrounding code, removed.
4. **Intermediate variables (`result`, `stmt`, `bibtex_content`)** where chained expressions read more cleanly — squashed.

None of these are correctness issues; all are taste. The fact that Gemini's first replace failed and it recovered without help is a nice signal.

### Verdict

**Useful for small, well-specified, single-concern tasks.** The spec ran straight through and produced working code. The defects were stylistic, not functional, and a re-prompt with explicit "no docstrings, no intermediate vars, hoist imports" would likely have produced output I'd commit unchanged. For tasks where the spec is harder to write fully (UI work, anything requiring cross-file context), the prompt cost outweighs the time saved — I'd reach for an `Explore` subagent first instead. For boilerplate-shaped backend additions like this one, gemini headless is a net positive even after the cleanup pass.

Time accounting (rough):
- Spec writing: ~5 min
- Gemini execution: ~30 s
- Diff review: ~3 min
- Cleanup edits: ~5 min
- Total: ~13 min — vs. probably ~10 min if I'd just written it myself. Break-even on this task. The win comes if you can run several such tasks in parallel.

---

## Experiment 2 — Critical review of Cycle 11 diff

**Date:** 2026-05-16
**Delegated to:** Gemini CLI 0.42.0 (review of uncommitted diff)
**Working tree:** Cycle 11 changes — quote search, pagination, compare view

### Why this delegation

The user asked specifically about using frontier-lab agents for critical review. First attempt was **Codex CLI's `codex review --uncommitted`** subcommand — purpose-built for this and offered structured findings JSON. However Codex's Linux sandbox (bubblewrap) failed in this environment (`bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted`) even with `--dangerously-bypass-approvals-and-sandbox`, and Codex refused to inspect the diff at all. Codex review would have been ideal here if the sandbox worked.

Fell back to **piping the diff to Gemini** with a focused review prompt covering: FTS migration safety, ORM/migration alignment, count/data drift, click-target edge cases, URL-param injection, batch-endpoint DoS/security.

### Findings Gemini reported

| # | Finding | Verdict |
|---|---------|---------|
| 1 | IDOR on `GET /references/batch` — no project / ownership scope, any auth user can read any ref by ID | **TRUE.** Matches the known pre-existing gap on `/{id}` endpoints. New endpoint shouldn't widen the surface. |
| 2 | "Search mode will fail to paginate — services/search.py wasn't updated for limit/offset/COUNT" | **FALSE.** `full_text_search` already accepted limit/offset and returned total before the diff; the diff only touched the FTS index/query expression. Gemini missed that the function signature was untouched. |
| 3 | `ALTER TABLE ADD COLUMN ... GENERATED ALWAYS AS ... STORED` rewrites the table under `AccessExclusiveLock` | **TRUE but acceptable.** Brief at our scale (hundreds → low thousands of refs), would be a real issue at 10M+ rows. Worth noting in design-decisions. |
| 4 | SQLAlchemy `Computed(persisted=True)` correctly matches `STORED`, omits column from INSERT/UPDATE | **CONFIRMED.** Validation, not a finding. |
| 5 | Compare UI event handling sound — checkbox `stopPropagation`, `handleCardClick` doesn't double-fire | **CONFIRMED.** Validation. |
| 6 | `/batch` endpoint preserves order via dict + list-comprehension reordering; URL-length DoS isn't a concern | **CONFIRMED.** Validation. |

### Actions taken in response

- **Finding 1 (IDOR):** Added optional `project_id` query parameter to `/references/batch`. ComparePage now reads the active project from `useProject()` and passes it. This brings `/batch` in line with the `GET /references` list-endpoint pattern (`project_id` as a filter). The deeper fix — actual ownership enforcement on every direct reference endpoint — is still the standing security gap, but the new endpoint at least doesn't widen it.
- **Finding 2 (false positive):** Verified by reading `services/search.py` — limit/offset/total were already in place. No action.
- **Finding 3 (lock):** Acceptable at this scale; not changing the migration. Already noted in the Cycle 11 design-decisions entry about the `STORED` storage trade-off. Adding a margin note for future scale.

### Verdict on Gemini-as-reviewer

**Worth doing.** Caught a real issue (IDOR) and gave one false positive that took 30 seconds to verify. Compared with not having the review: I would likely have shipped `/batch` without project-scoping, perpetuating the pattern. Compared with `codex review` (didn't work here due to sandbox), Gemini's freeform prose is harder to parse than Codex's structured findings JSON would have been — but freeform was enough.

Gotchas observed:
- The Gemini CLI emitted a long bundled stack trace about `NumericalClassifierStrategy` failing to route — looked alarming but the actual review output came through fine after it. The error is in Gemini's model-routing telemetry, not the response.
- Gemini's confidence on the false positive (#2) was high. Always verify claims against the actual code before acting on them.

Time accounting:
- Codex sandbox debugging: ~3 min (wasted)
- Diff capture + Gemini prompt: ~1 min
- Gemini response: ~20 s
- Verifying findings: ~3 min
- Applying real fix (IDOR): ~3 min
- Total: ~10 min for one real catch worth multiples of that.
