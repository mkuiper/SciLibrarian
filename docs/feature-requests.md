# SciLibrarian Feature Requests

Date: 2026-05-07
Author: Codex review pass

This file captures product ideas from the code review discussion. These should
be treated as staged development candidates, not as one large implementation
batch. The strongest direction is to make SciLibrarian excellent at answering:

- What do we know?
- What changed recently?
- What should I read next?
- Which sources support that answer?

## Development Principle

Prioritize trust and synthesis over raw ingestion volume. Researchers need
high-signal triage, evidence trails, and durable research memory more than they
need another place to accumulate unread PDFs.

Build these features incrementally. The recommended foundation work is:

1. Complete project scoping for references, monitors, review queues and digests.
2. Add reliable evidence links from summaries and assistant answers back to
   source references.
3. Improve search quality and ranking.
4. Then layer higher-level synthesis and team workflow on top.

## Candidate Features

### 1. Research Radar

A project homepage panel that shows what changed since the last check-in.

Possible contents:

- newly approved references;
- pending review items grouped by source and topic;
- emerging themes across new papers;
- surprising or contradictory claims;
- new datasets, benchmarks or evaluation methods;
- high-signal additions based on citation count, source quality or monitor fit;
- recommended next reads.

Why it matters:

Researchers often need a short situational briefing before deciding what to
read. A radar view would make the system useful even when users only have a few
minutes.

### 2. Better Search

Replace the current simple substring search with ranked PostgreSQL full-text
search.

Possible capabilities:

- ranking by title, abstract, summary and full-text matches;
- snippets showing the matching paragraph;
- filters by year, source type, tag, collection, read status and starred state;
- server-side pagination;
- later: hybrid lexical plus embedding search.

Why it matters:

Researchers need to find the relevant passage, not just the document. Basic
ranked search with snippets will provide immediate value before a full vector
search system is needed.

### 3. Citation Graph And Related Work

For each reference, show how it connects to other literature.

Possible capabilities:

- references cited by the paper;
- papers that cite this paper;
- related papers from Semantic Scholar or OpenAlex;
- key predecessor papers;
- papers that share datasets, benchmarks or methods;
- duplicate detection using DOI, arXiv ID, URL and title similarity.

Why it matters:

Research understanding depends on context. A related-work view helps users see
whether a paper is foundational, derivative, isolated or part of an active line
of work.

### 4. Claim And Finding Extraction

Extract structured research claims from ingested documents.

Possible fields:

- main result;
- method or intervention;
- dataset or benchmark;
- assumptions;
- limitations;
- evidence strength;
- relevance to project goals;
- open questions raised by the paper.

Why it matters:

This turns the library from a document archive into an evidence base. It also
creates better inputs for digests, literature reviews and assistant answers.

### 5. Researcher Reading Workflow

Expand reading state beyond unread/reading/read.

Possible states and actions:

- skimmed;
- important;
- needs replication;
- cite in report;
- assign to colleague;
- follow up later;
- monitor for updates;
- add private or shared annotation.

Why it matters:

Research is collaborative and task-oriented. Reading status alone does not
capture why a paper matters or what should happen next.

### 6. Living Literature Review

Generate an editable synthesis document for each project or collection.

Possible capabilities:

- sectioned literature review maintained from approved references;
- explicit citations back to references;
- change summary when new papers alter the synthesis;
- user edits preserved between AI-assisted updates;
- export to Markdown, DOCX or BibTeX-backed formats.

Why it matters:

Researchers usually need a working synthesis, not just chat answers. A living
review could become the central artifact of a project.

### 7. Monitor Learning From Review Decisions

Make monitors improve based on approval and rejection history.

Possible capabilities:

- summarize why recent rejections were off-target;
- suggest query refinements;
- adjust source weighting;
- generate negative keywords or exclusion criteria;
- show monitor precision over time.

Why it matters:

Without feedback loops, automated monitors can become noisy. Learning from
review decisions preserves trust and reduces review burden.

### 8. Evidence Trails For AI Output

Every generated answer, summary and digest should expose its sources.

Possible capabilities:

- cited references for each assistant answer;
- exact snippets or page numbers when available;
- confidence or coverage notes;
- clear distinction between library-grounded claims and web/model inferences;
- links from digest sections back to source references.

Why it matters:

Researchers will not trust opaque synthesis. Evidence trails are core product
functionality, not polish.

### 9. Strong Deduplication

Detect duplicate references before and after ingestion.

Possible matching keys:

- DOI;
- arXiv ID;
- Semantic Scholar paper ID;
- normalized URL;
- title similarity;
- PDF fingerprint where possible.

Why it matters:

The same paper will arrive from arXiv, Semantic Scholar, OpenAlex, direct PDF
upload and web links. Duplicate clutter degrades search, digests and trust.

### 10. Team Workflow And Permissions

Add a deliberate collaboration model.

Possible capabilities:

- project members and roles;
- shared versus private notes;
- review assignments;
- activity history;
- project-level access control;
- notification settings for monitors and digests.

Why it matters:

If this is used by a research group or institute, the app needs explicit team
semantics. Until then, backend scoping should be conservative and clear.

## Suggested Implementation Sequence

### Phase 1: Trust Foundation

- finish project scoping for monitors and review queue;
- enforce project access consistently across direct reference endpoints;
- repair local/Docker verification workflow;
- add source citation plumbing to assistant and digest outputs.

### Phase 2: Retrieval Quality

- implement PostgreSQL full-text search with ranking and snippets;
- add server-side pagination and filters;
- improve deduplication using DOI, arXiv ID and normalized URL.

### Phase 3: Research Synthesis

- add claim/finding extraction;
- create a research radar view;
- improve monthly digests with explicit evidence links.

### Phase 4: Collaboration

- define project membership and roles;
- add review assignments and shared annotations;
- add monitor quality metrics and learning from review decisions.

### Phase 5: Advanced Context

- add citation graph and related-work views;
- add hybrid embedding search if lexical search is no longer sufficient;
- add living literature review generation and update workflows.
