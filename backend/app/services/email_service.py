"""
Email delivery for digests and notifications.
Configure SMTP credentials in .env:
  SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM
"""
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def _markdown_to_html(md: str) -> str:
    """Minimal markdown→HTML for email bodies."""
    import re
    lines = md.split('\n')
    html_lines = []
    for line in lines:
        line = re.sub(r'^### (.+)', r'<h3>\1</h3>', line)
        line = re.sub(r'^## (.+)', r'<h2>\1</h2>', line)
        line = re.sub(r'^# (.+)', r'<h1>\1</h1>', line)
        line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
        line = re.sub(r'\*(.+?)\*', r'<em>\1</em>', line)
        if line.startswith('- '):
            line = f'<li>{line[2:]}</li>'
        elif line.strip() == '---':
            line = '<hr>'
        elif line and not line.startswith('<'):
            line = f'<p>{line}</p>'
        html_lines.append(line)
    return '\n'.join(html_lines)


async def send_digest(recipients: list[str], subject: str, markdown_content: str):
    if not settings.smtp_host:
        logger.warning("SMTP not configured — digest email not sent")
        return

    if not recipients:
        return

    html = f"""
    <html><body style="font-family: Georgia, serif; max-width: 700px; margin: auto; padding: 20px; color: #1a1a2e;">
    <div style="background: #1a2236; padding: 20px; border-radius: 8px; margin-bottom: 24px;">
      <h2 style="color: white; margin: 0;">📚 Alexandria</h2>
      <p style="color: #8892b0; margin: 4px 0 0;">SciLibrarian Monthly Digest</p>
    </div>
    {_markdown_to_html(markdown_content)}
    <hr style="margin-top: 40px;">
    <p style="color: #888; font-size: 12px;">You received this because you're on the digest mailing list.
    Contact your administrator to unsubscribe.</p>
    </body></html>
    """

    try:
        import aiosmtplib
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = settings.smtp_from
        msg['To'] = ', '.join(recipients)
        msg.attach(MIMEText(markdown_content, 'plain'))
        msg.attach(MIMEText(html, 'html'))

        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_tls,
        )
        logger.info(f"Digest sent to {len(recipients)} recipients")
    except Exception as e:
        logger.error(f"Failed to send digest email: {e}")
