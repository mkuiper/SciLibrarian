"""
Alexandria's project onboarding intelligence.
When a new project is created, Alexandria analyses the description and goals
to suggest an initial collection taxonomy and watch keywords. As the project
grows, she can recommend restructuring based on what's actually been collected.
"""
import json
import anthropic
from app.config import settings


async def generate_initial_structure(
    name: str,
    description: str,
    domain: str,
    goals: str,
    model: str = "claude-sonnet-4-6",
) -> dict:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    prompt = f"""You are Alexandria, an expert research librarian. A research team is setting up a new knowledge management project and needs your help planning its structure.

Project name: {name}
Domain: {domain}
Description: {description}
Research goals: {goals}

Based on this, design an optimal collection taxonomy for organising their references. Think about:
- The main thematic areas they will need to cover
- Relevant sub-topics and specialisations
- The types of documents they will collect (papers, policies, model cards, evaluations, etc.)
- Logical groupings that will scale as the library grows

Return valid JSON only (no markdown fences) with this structure:
{{
  "welcome_message": "A personalised welcome from Alexandria explaining how you will help this project (2-3 sentences, warm and scholarly)",
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

    message = await client.messages.create(
        model=model,
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
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
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    prompt = f"""You are Alexandria, the research librarian for {project_name}.

Current collection structure:
{json.dumps(current_collections, indent=2)}

Recent references added (last 30):
{json.dumps(recent_references, indent=2)}

Based on what has actually been collected, identify:
1. Collections that are overcrowded and should be split
2. Collections that could be merged
3. New collections that would better serve the emerging themes
4. Any references that seem miscategorised

Return JSON only:
{{
  "recommendations": [
    {{
      "type": "split|merge|create|move",
      "description": "What to do and why",
      "priority": "high|medium|low"
    }}
  ],
  "summary": "Brief overall assessment of the library structure"
}}"""

    message = await client.messages.create(
        model=model,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())
