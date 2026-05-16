"""
Alexandria's project onboarding intelligence.
When a project is created, Alexandria analyses the description and goals
to suggest an initial collection taxonomy and watch queries.
"""
import json
import re
from app.services.llm import complete_text


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:]
            if part.strip().startswith("{"):
                raw = part.strip()
                break
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    fixed2 = re.sub(r',\s*([}\]])', r'\1', fixed)
    return json.loads(fixed2)


async def generate_initial_structure(
    name: str,
    description: str,
    domain: str,
    goals: str,
    model: str | None = None,
) -> dict:
    from app.config import settings
    model = model or settings.default_librarian_model
    prompt = f"""You are Alexandria, an expert research librarian. A research team is setting up a new knowledge management project.

Project name: {name}
Domain: {domain}
Description: {description}
Research goals: {goals}

Design an optimal collection taxonomy for organising their references. Return valid JSON only (no markdown fences):
{{
  "welcome_message": "A personalised welcome from Alexandria (2-3 sentences, warm and scholarly)",
  "collections": [
    {{
      "name": "Collection name",
      "description": "What this collection covers",
      "children": [
        {{"name": "Sub-collection", "description": "..."}}
      ]
    }}
  ],
  "suggested_watch_queries": [
    {{
      "name": "Query name",
      "query": "search terms",
      "rationale": "Why this is worth monitoring"
    }}
  ],
  "initial_guidance": "A paragraph of guidance on how to use this library structure effectively"
}}"""

    raw = await complete_text(model, prompt, max_tokens=2000)
    return _parse_json(raw)


async def suggest_restructure(
    project_name: str,
    current_collections: list[dict],
    recent_references: list[dict],
    model: str = "claude-sonnet-4-6",
) -> dict:
    """Ask Alexandria for structured, executable restructure actions.

    Returns:
        {summary, actions: [...]} where each action is a dict with `type` and
        type-specific fields referencing real collection / reference IDs.
        Callers must validate IDs against the project before applying.
    """
    prompt = f"""You are Alexandria, the research librarian for {project_name}.

CURRENT COLLECTIONS (id, name, description, parent_id, ref_count):
{json.dumps(current_collections, indent=2)}

RECENT REFERENCES (id, title, tags, current collection_id, year):
{json.dumps(recent_references, indent=2)}

Propose concrete, executable restructure actions. Every action MUST reference real
IDs from the data above — do not invent IDs. Prefer 3-6 high-signal actions over
many low-impact ones. If the library is well-organised, return an empty actions list.

Action types and required fields:

1. create_collection — make a new collection, optionally populated immediately
   {{"type": "create_collection", "name": "...", "description": "...",
     "parent_id": <id or null>, "populate_with_reference_ids": [<ids>],
     "priority": "high|medium|low", "reasoning": "why this helps"}}

2. rename_collection — change name/description of an existing collection
   {{"type": "rename_collection", "collection_id": <id>,
     "new_name": "...", "new_description": "..." (or null to keep),
     "priority": "...", "reasoning": "..."}}

3. move_references — move refs into an existing collection
   {{"type": "move_references", "reference_ids": [<ids>],
     "target_collection_id": <id>,
     "priority": "...", "reasoning": "..."}}

4. merge_collections — move all refs from source to target, then delete source
   {{"type": "merge_collections", "source_collection_id": <id>,
     "target_collection_id": <id>,
     "priority": "...", "reasoning": "..."}}

Rules:
- Use the real IDs shown above. If you can't justify a move with a real ref ID, drop it.
- A reference's "tags" field is a strong signal — group by tag patterns.
- Don't propose merging a collection that has sub-collections (children) — that case is unsafe.
- Keep `reasoning` to one short sentence. Specific is better than general.

Return JSON only (no markdown fences):
{{
  "summary": "Brief overall assessment (1-2 sentences)",
  "actions": [ ... ]
}}"""

    raw = await complete_text(model, prompt, max_tokens=2000)
    parsed = _parse_json(raw)
    if "actions" not in parsed:
        # Tolerate legacy `recommendations` key from earlier prompt versions
        parsed["actions"] = parsed.pop("recommendations", [])
    return parsed
