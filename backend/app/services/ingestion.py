import json
import re
import uuid
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.services.llm import complete_text


def _parse_json_response(raw: str) -> dict:
    """
    Robustly parse a JSON response from an LLM.
    Handles: markdown fences, invalid backslash escapes, trailing commas,
    and partial responses. Falls back to extracting what it can.
    """
    raw = raw.strip()

    # Strip markdown code fences
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:]
            if part.strip().startswith("{"):
                raw = part.strip()
                break

    # Find the outermost JSON object
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start != -1 and end > start:
        raw = raw[start:end]

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fix invalid backslash escapes — the most common Ollama failure
    # Valid JSON escapes: \" \\ \/ \b \f \n \r \t \uXXXX
    fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Remove trailing commas before } or ]
    fixed2 = re.sub(r',\s*([}\]])', r'\1', fixed)
    try:
        return json.loads(fixed2)
    except json.JSONDecodeError:
        pass

    # Last resort: extract fields with regex
    def extract(pattern, default=None):
        m = re.search(pattern, raw, re.DOTALL)
        return m.group(1).strip() if m else default

    return {
        "title": extract(r'"title"\s*:\s*"([^"]+)"', "Untitled"),
        "authors": extract(r'"authors"\s*:\s*"([^"]+)"'),
        "year": None,
        "source_type": "paper",
        "abstract": extract(r'"abstract"\s*:\s*"([^"]{20,}?)"'),
        "summary": extract(r'"summary"\s*:\s*"([^"]{20,}?)"'),
        "tags": [],
        "extra_metadata": {},
    }

SOURCE_TYPES = ["paper", "policy", "model_card", "evaluation", "government", "news", "other"]


async def extract_pdf_text(file_bytes: bytes) -> str:
    import fitz
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    text = "\n\n".join(page.get_text() for page in doc)
    doc.close()
    # Strip null bytes — PostgreSQL rejects \x00 in UTF-8 text columns
    return text.replace("\x00", "")[:50000]


ARXIV_ABS  = re.compile(r'https?://arxiv\.org/abs/(\d{4}\.\d{4,5}(?:v\d+)?)')
ARXIV_PDF  = re.compile(r'https?://arxiv\.org/pdf/(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?')
DOI_URL    = re.compile(r'https?://(?:dx\.)?doi\.org/(.+)')


def _arxiv_pdf_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/pdf/{arxiv_id}"


def _is_pdf_response(resp) -> bool:
    ct = resp.headers.get("content-type", "").lower()
    return "pdf" in ct or resp.content[:4] == b"%PDF"


async def _fetch(url: str, timeout: int = 60) -> httpx.Response:
    async with httpx.AsyncClient(
        follow_redirects=True, timeout=timeout,
        headers={"User-Agent": "SciLibrarian/1.0 (research tool)"}
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp


async def extract_url_text(url: str) -> tuple[str, str]:
    resp = await _fetch(url)
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
- summary: string (concise 5-7 sentence summary of key points and relevance)
- tags: array of strings (5-10 relevant topic tags, lowercase, no spaces)
- main_finding: string (the single most important claim or result, one sentence, or null)
- method: string (primary method, model, or technique used, or null)
- limitations: string (key limitations or caveats mentioned, or null)
- extra_metadata: object with any other relevant fields (journal, doi, institution, arxiv_id, etc.)"""

    raw = await complete_text(model, prompt, max_tokens=1800)
    meta = _parse_json_response(raw)

    # Move findings into extra_metadata.findings to keep schema stable
    findings = {}
    for key in ("main_finding", "method", "limitations"):
        val = meta.pop(key, None)
        if val and isinstance(val, str) and val.strip():
            findings[key] = val.strip()
    if findings:
        extra = meta.setdefault("extra_metadata", {}) or {}
        extra["findings"] = findings
        meta["extra_metadata"] = extra

    return meta


async def save_upload(file_bytes: bytes, original_filename: str) -> str:
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(original_filename).suffix
    filename = f"{uuid.uuid4().hex}{ext}"
    path = upload_dir / filename
    path.write_bytes(file_bytes)
    return str(path)


def _clean(value):
    """Strip null bytes from any string value (PostgreSQL rejects \\x00)."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    return value


async def ingest_pdf(file_bytes: bytes, filename: str, model: str = "claude-sonnet-4-6") -> dict:
    text = await extract_pdf_text(file_bytes)
    file_path = await save_upload(file_bytes, filename)
    meta = await generate_metadata(text, Path(filename).stem, model)
    meta["file_path"] = file_path
    meta["file_name"] = filename
    meta["full_text"] = text
    return {k: _clean(v) for k, v in meta.items()}


async def ingest_file(file_bytes: bytes, filename: str, model: str = "claude-sonnet-4-6") -> dict:
    """
    Generic file ingestion — routes to the correct extractor based on file extension.
    Falls back to PDF pipeline for .pdf files.
    """
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return await ingest_pdf(file_bytes, filename, model)

    from app.services.extractors import get_extractor, is_supported
    extractor = get_extractor(filename)
    if not extractor:
        raise ValueError(f"Unsupported file type: {ext}")

    title, text = extractor(file_bytes, filename)
    file_path = await save_upload(file_bytes, filename)
    meta = await generate_metadata(text, title, model)
    meta["file_path"] = file_path
    meta["file_name"] = filename
    meta["full_text"] = text
    if not meta.get("title") or meta["title"] == "Untitled":
        meta["title"] = title
    return {k: _clean(v) for k, v in meta.items()}


async def _ingest_pdf_bytes_from_url(pdf_url: str, filename: str, original_url: str, model: str) -> dict | None:
    """Download a URL and process it as a PDF if it really is one. Returns None on failure."""
    try:
        resp = await _fetch(pdf_url, timeout=60)
        if _is_pdf_response(resp):
            meta = await ingest_pdf(resp.content, filename, model)
            meta["url"] = original_url  # keep the canonical URL
            return meta
    except Exception:
        pass
    return None


async def ingest_url(url: str, model: str = "claude-sonnet-4-6") -> dict:
    """
    Smart URL ingestion that handles:
    - arXiv abstract pages → automatically fetch the PDF
    - arXiv PDF URLs → download and process via PDF pipeline
    - Direct PDF URLs (.pdf extension or PDF content-type) → PDF pipeline
    - DOI URLs → resolve and try PDF
    - Everything else → HTML scraping
    """
    # ── arXiv abstract page ──────────────────────────────────────────────────
    m = ARXIV_ABS.match(url)
    if m:
        arxiv_id = m.group(1)
        pdf_url = _arxiv_pdf_url(arxiv_id)
        meta = await _ingest_pdf_bytes_from_url(pdf_url, f"arxiv_{arxiv_id}.pdf", url, model)
        if meta:
            return meta
        # Fall back to abstract page scraping
        title, text = await extract_url_text(url)
        meta = await generate_metadata(text, title, model)
        meta.update(url=url, full_text=text)
        return {k: _clean(v) for k, v in meta.items()}

    # ── arXiv PDF URL ────────────────────────────────────────────────────────
    m = ARXIV_PDF.match(url)
    if m:
        arxiv_id = m.group(1)
        canonical = f"https://arxiv.org/abs/{arxiv_id}"
        meta = await _ingest_pdf_bytes_from_url(url, f"arxiv_{arxiv_id}.pdf", canonical, model)
        if meta:
            return meta

    # ── Any URL that ends with .pdf or responds with PDF content-type ────────
    if url.lower().endswith(".pdf") or "/pdf/" in url.lower():
        fname = url.split("/")[-1] or "paper.pdf"
        if not fname.lower().endswith(".pdf"):
            fname += ".pdf"
        meta = await _ingest_pdf_bytes_from_url(url, fname, url, model)
        if meta:
            return meta

    # ── Try fetching: if it turns out to be a PDF, route to PDF pipeline ─────
    try:
        resp = await _fetch(url, timeout=45)
        if _is_pdf_response(resp):
            fname = url.split("/")[-1] or "document.pdf"
            if not fname.lower().endswith(".pdf"):
                fname += ".pdf"
            meta = await ingest_pdf(resp.content, fname, model)
            meta["url"] = url
            return meta
        # It's HTML — parse it
        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        title = soup.title.string.strip() if soup.title else ""
        text = soup.get_text(separator="\n", strip=True)[:50000]
    except Exception:
        title, text = "", ""

    meta = await generate_metadata(text, title, model)
    meta.update(url=url, full_text=text)
    return {k: _clean(v) for k, v in meta.items()}


