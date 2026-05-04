import json
import uuid
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.llm import complete_text

SOURCE_TYPES = ["paper", "policy", "model_card", "evaluation", "government", "news", "other"]


async def extract_pdf_text(file_bytes: bytes) -> str:
    import fitz
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = "\n\n".join(page.get_text() for page in doc)
    doc.close()
    return text[:50000]


async def extract_url_text(url: str) -> tuple[str, str]:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
        resp = await client.get(url, headers={"User-Agent": "SciLibrarian/1.0 (research tool)"})
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    title = soup.title.string.strip() if soup.title else ""
    text = soup.get_text(separator="\n", strip=True)
    return title, text[:50000]


async def generate_metadata(text: str, title: str, model: str = "claude-sonnet-4-6") -> dict:
    prompt = f"""Analyse this document and extract structured metadata. Return valid JSON only, no markdown fences.

Title hint: {title}

Document excerpt:
{text[:8000]}

Return JSON with these fields:
- title: string (best title for this document)
- authors: string (comma-separated author names, or null)
- year: integer (publication year, or null)
- source_type: one of {SOURCE_TYPES}
- abstract: string (2-3 sentence abstract or description)
- summary: string (concise 5-7 sentence summary of key points and relevance to AI safety)
- tags: array of strings (5-10 relevant topic tags, lowercase, no spaces)
- extra_metadata: object with any other relevant fields (journal, doi, institution, etc.)"""

    raw = await complete_text(model, prompt, max_tokens=1500)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


async def save_upload(file_bytes: bytes, original_filename: str) -> str:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(original_filename).suffix
    filename = f"{uuid.uuid4().hex}{ext}"
    path = upload_dir / filename
    path.write_bytes(file_bytes)
    return str(path)


async def ingest_pdf(file_bytes: bytes, filename: str, model: str = "claude-sonnet-4-6") -> dict:
    text = await extract_pdf_text(file_bytes)
    file_path = await save_upload(file_bytes, filename)
    meta = await generate_metadata(text, Path(filename).stem, model)
    meta["file_path"] = file_path
    meta["file_name"] = filename
    meta["full_text"] = text
    return meta


async def ingest_url(url: str, model: str = "claude-sonnet-4-6") -> dict:
    title, text = await extract_url_text(url)
    meta = await generate_metadata(text, title, model)
    meta["url"] = url
    meta["full_text"] = text
    return meta
