"""
Alexandria's project onboarding intelligence.
When a project is created, Alexandria analyses the description and goals
to suggest an initial collection taxonomy and watch queries.
"""
import json
from app.services.llm import complete_text


async def generate_initial_structure(
    name: str,
    description: str,
    domain: str,
    goals: str,
    model: str = "claude-sonnet-4-6",
) -> dict:
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
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


async def suggest_restructure(
    project_name: str,
    current_collections: list[dict],
    recent_references: list[dict],
    model: str = "claude-sonnet-4-6",
) -> dict:
    prompt = f"""You are Alexandria, the research librarian for {project_name}.

Current collection structure:
{json.dumps(current_collections, indent=2)}

Recent references added (last 30):
{json.dumps(recent_references, indent=2)}

Based on what has actually been collected, identify reorganisation opportunities.
Return JSON only:
{{
  "recommendations": [
    {{
      "type": "split|merge|create|move",
      "description": "What to do and why",
      "priority": "high|medium|low"
    }}
  ],
  "summary": "Brief overall assessment"
}}"""

    raw = await complete_text(model, prompt, max_tokens=1500)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
