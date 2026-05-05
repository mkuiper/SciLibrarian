"""
Email ingestion for Alexandria.

Users can email PDFs or URLs to a dedicated inbox and Alexandria will
automatically process and file them into the library.

Setup:
  1. Create a dedicated email address (e.g. ingest@yourdomain.com)
     Gmail, Outlook, or any IMAP-compatible provider works.
  2. Set INGEST_EMAIL_ENABLED=true and IMAP credentials in .env
  3. The scheduler calls check_inbox() every INGEST_CHECK_INTERVAL_MINUTES

What Alexandria processes from each email:
  - PDF attachments → full ingestion pipeline (extract text, generate metadata)
  - URLs in subject line or body → URL ingestion pipeline
  - Subject line used as a hint for collection routing
  - Sender name recorded in reference metadata

Alexandria replies to the sender with a confirmation listing what was filed.

Security note: Any sender can submit to this inbox. Consider using a
secret/obscure email address rather than a publicly advertised one.
For a known-team-only tool, this is fine; for public deployment,
add sender allowlist via INGEST_ALLOWED_SENDERS in .env.
"""
import logging
import re
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.project import Project
from app.models.collection import Collection
from app.models.reference import Reference, ReferenceTag

logger = logging.getLogger(__name__)

URL_RE = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)


async def check_inbox(db: AsyncSession):
    """
    Poll the IMAP inbox for new messages. Process PDFs and URLs.
    Called by the scheduler every INGEST_CHECK_INTERVAL_MINUTES.
    """
    if not settings.ingest_email_enabled:
        return

    if not settings.ingest_imap_host or not settings.ingest_imap_username:
        logger.warning("Email ingestion enabled but IMAP credentials not configured")
        return

    try:
        from imap_tools import MailBox, AND, MailMessageFlags
    except ImportError:
        logger.error("imap-tools not installed — email ingestion unavailable")
        return

    project_result = await db.execute(
        select(Project).where(Project.id == settings.ingest_default_project_id)
    )
    project = project_result.scalar_one_or_none()
    if not project:
        logger.warning(f"Default project {settings.ingest_default_project_id} not found")
        return

    model = (project.settings or {}).get("ingestion_model", settings.default_ingestion_model)

    try:
        with MailBox(settings.ingest_imap_host, port=settings.ingest_imap_port).login(
            settings.ingest_imap_username,
            settings.ingest_imap_password,
            initial_folder=settings.ingest_imap_folder,
        ) as mailbox:
            unseen = list(mailbox.fetch(AND(seen=False), mark_seen=False, bulk=True))
            logger.info(f"Email ingestion: {len(unseen)} unread message(s)")

            for msg in unseen:
                filed = await _process_message(db, msg, project, model)
                if filed:
                    mailbox.flag([msg.uid], [MailMessageFlags.SEEN], True)
                    if settings.smtp_host and msg.from_:
                        await _send_confirmation(msg.from_, msg.subject or "", filed)

    except Exception as e:
        logger.error(f"IMAP connection failed: {e}")


async def _process_message(db: AsyncSession, msg, project: Project, model: str) -> list[str]:
    """Process a single email message. Returns list of filed reference titles."""
    from app.services.ingestion import ingest_pdf, ingest_url
    from app.models.reference import Reference, ReferenceTag

    filed = []
    subject = (msg.subject or "").strip()
    body = msg.text or msg.html or ""
    sender_name = msg.from_values.name if msg.from_values else msg.from_

    collection_id = await _guess_collection(db, project.id, subject)

    # Process PDF attachments
    for att in msg.attachments:
        if not att.filename.lower().endswith(".pdf"):
            continue
        try:
            logger.info(f"Processing PDF attachment: {att.filename}")
            meta = await ingest_pdf(att.payload, att.filename, model)
            ref = _build_reference(meta, project.id, collection_id, sender_name)
            db.add(ref)
            await db.flush()
            for tag in meta.get("tags", []):
                db.add(ReferenceTag(reference_id=ref.id, tag=tag.strip().lower()))
            await db.commit()
            filed.append(meta.get("title", att.filename))
            logger.info(f"Filed PDF: {meta.get('title')}")
        except Exception as e:
            logger.error(f"Failed to process attachment {att.filename}: {e}")

    # Process URLs from body and subject
    urls = URL_RE.findall(subject + " " + body)
    seen_urls = set()
    for url in urls[:5]:
        url = url.rstrip(".,;)")
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Skip tracking pixels and common noise
        if any(skip in url for skip in ["unsubscribe", "pixel", "track", "beacon", "click.em"]):
            continue

        try:
            logger.info(f"Processing URL: {url}")
            meta = await ingest_url(url, model)
            ref = _build_reference(meta, project.id, collection_id, sender_name)
            ref.url = url
            db.add(ref)
            await db.flush()
            for tag in meta.get("tags", []):
                db.add(ReferenceTag(reference_id=ref.id, tag=tag.strip().lower()))
            await db.commit()
            filed.append(meta.get("title", url))
            logger.info(f"Filed URL: {meta.get('title')}")
        except Exception as e:
            logger.error(f"Failed to process URL {url}: {e}")

    return filed


def _build_reference(meta: dict, project_id: int, collection_id: int | None, sender: str) -> Reference:
    extra = dict(meta.get("extra_metadata") or {})
    extra["submitted_by_email"] = sender
    return Reference(
        title=meta.get("title", "Untitled"),
        authors=meta.get("authors"),
        year=meta.get("year"),
        source_type=meta.get("source_type", "other"),
        abstract=meta.get("abstract"),
        summary=meta.get("summary"),
        url=meta.get("url"),
        file_path=meta.get("file_path"),
        file_name=meta.get("file_name"),
        full_text=meta.get("full_text"),
        project_id=project_id,
        collection_id=collection_id,
        created_by=1,  # system user; email submissions attributed to admin
        extra_metadata=extra,
    )


async def _guess_collection(db: AsyncSession, project_id: int, subject: str) -> int | None:
    """Try to match the email subject to an existing collection name."""
    if not subject:
        return None
    result = await db.execute(
        select(Collection).where(Collection.project_id == project_id)
    )
    collections = result.scalars().all()
    subject_lower = subject.lower()
    for col in collections:
        if col.name.lower() in subject_lower or subject_lower in col.name.lower():
            return col.id
    return None


async def _send_confirmation(recipient: str, original_subject: str, filed: list[str]):
    """Send a reply confirming what was filed."""
    from app.services.email_service import send_digest
    body = f"## Alexandria has filed {len(filed)} reference(s)\n\n"
    for title in filed:
        body += f"- {title}\n"
    body += "\nYou can view and manage these in your SciLibrarian library."
    await send_digest(
        [recipient],
        f"Re: {original_subject or 'Your submission to Alexandria'}",
        body,
    )
