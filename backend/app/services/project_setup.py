"""
Alexandria's project onboarding intelligence.
When a project is created, Alexandria analyses the description and goals
to suggest an initial collection taxonomy and watch queries.
"""
import json
import logging
import re
from app.services.llm import complete_text

logger = logging.getLogger(__name__)


def _try_parse_json(raw: str) -> dict | None:
    """Best-effort JSON extraction. Returns None instead of raising on failure."""
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
    for repair in (
        lambda s: s,
        lambda s: re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', s),
        lambda s: re.sub(r',\s*([}\]])', r'\1', re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', s)),
    ):
        try:
            return json.loads(repair(raw))
        except json.JSONDecodeError:
            continue
    return None


def _parse_json(raw: str) -> dict:
    """Strict variant — raises on failure. Used by setup paths where partial output is unusable."""
    parsed = _try_parse_json(raw)
    if parsed is None:
        raise json.JSONDecodeError("could not parse JSON after repair attempts", raw, 0)
    return parsed


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
    model: str | None = None,
) -> dict:
    """Ask Alexandria for structured, executable restructure actions.

    Args:
        model: explicit model name. If None, falls back to settings.default_librarian_model.
            Callers should pass the project's librarian_model setting (see the
            endpoint in routers/projects.py); a global override on top of that
            is handled inside complete_text via effective_model().

    Returns:
        {summary, actions: [...]} where each action is a dict with `type` and
        type-specific fields referencing real collection / reference IDs.

    Designed to degrade gracefully on smaller models (Ollama gemma, llama):
    if the model produces unparseable output we return an empty actions list
    with a helpful summary instead of raising, so the UI can show the user
    what happened rather than a generic 500.
    """
    from app.config import settings
    model = model or settings.default_librarian_model
    prompt = f"""You are Alexandria, librarian for "{project_name}". Output ONLY a JSON object — no markdown fences, no preamble, no commentary.

COLLECTIONS (each has id, name, description, parent_id, ref_count):
{json.dumps(current_collections)}

RECENT REFERENCES (each has id, title, tags, collection_id, year):
{json.dumps(recent_references)}

Propose 0-6 concrete restructure actions. Every id in your output MUST appear in the data above. Empty actions array is fine if the library is well-organised.

Schema:
{{
  "summary": "1-2 sentence overall assessment",
  "actions": [ /* zero or more action objects, each ONE of the four shapes below */ ]
}}

Action shapes (use real ids):
{{"type":"create_collection","name":"AI Alignment","description":"Papers on alignment techniques","parent_id":null,"populate_with_reference_ids":[12,19,23],"priority":"high","reasoning":"3 recent papers tagged 'alignment' have no home collection"}}
{{"type":"rename_collection","collection_id":5,"new_name":"Foundation Models","new_description":"Large pretrained models","priority":"medium","reasoning":"current name doesn't reflect what's actually in here"}}
{{"type":"move_references","reference_ids":[12,19],"target_collection_id":8,"priority":"high","reasoning":"both papers are about RLHF but currently uncategorised"}}
{{"type":"merge_collections","source_collection_id":12,"target_collection_id":5,"priority":"medium","reasoning":"both contain interpretability papers and the smaller collection only has 2 refs"}}

Rules:
- Use real ids from the data above. Drop the action if you can't.
- Prefer specific reasoning over generic ("groups RLHF papers" beats "improves organisation").
- Don't merge a collection that has sub-collections — the system will reject it anyway.

Return the JSON object now."""

    try:
        raw = await complete_text(model, prompt, max_tokens=2500)
    except Exception as e:
        logger.warning(f"suggest_restructure: model {model} call failed: {e}")
        return {
            "summary": f"The model ({model}) couldn't complete the analysis: {str(e)[:200]}. Try switching to a more capable model from the Configuration page.",
            "actions": [],
            "error": True,
        }

    parsed = _try_parse_json(raw)
    if parsed is None:
        logger.warning(
            f"suggest_restructure: couldn't parse JSON from {model}. "
            f"First 400 chars of response: {raw[:400]!r}"
        )
        return {
            "summary": (
                f"Alexandria's reply (from {model}) wasn't valid JSON. "
                "This often happens with smaller local models — try a more capable model "
                "(e.g. Claude or a larger Ollama like gemma4:31b or qwen3.6:35b) on the Configuration page."
            ),
            "actions": [],
            "error": True,
            "raw_excerpt": raw[:300],
        }

    if "actions" not in parsed:
        # Tolerate legacy `recommendations` key from earlier prompt versions
        parsed["actions"] = parsed.pop("recommendations", [])
    if not isinstance(parsed.get("actions"), list):
        parsed["actions"] = []
    parsed.setdefault("summary", "")
    return parsed
