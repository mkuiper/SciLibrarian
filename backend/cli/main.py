"""
SciLibrarian CLI — interact with Alexandria from your terminal.

Usage:
  python -m cli.main --help
  python -m cli.main ingest path/to/paper.pdf --project 1
  python -m cli.main search "AI alignment" --project 1
  python -m cli.main digest --project 1
"""
import asyncio
import json
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

import typer
import httpx

app = typer.Typer(
    name="scilibrarian",
    help="Alexandria — SciLibrarian CLI. Manage your research library from the terminal.",
    rich_markup_mode="rich",
)

API_URL = "http://localhost:8000"
_token: Optional[str] = None


def _headers() -> dict:
    if not _token:
        typer.echo("Not logged in. Run: scilibrarian login", err=True)
        raise typer.Exit(1)
    return {"Authorization": f"Bearer {_token}"}


def _load_token() -> Optional[str]:
    token_file = Path.home() / ".scilibrarian_token"
    if token_file.exists():
        return token_file.read_text().strip()
    return None


def _save_token(token: str):
    token_file = Path.home() / ".scilibrarian_token"
    token_file.write_text(token)
    token_file.chmod(0o600)


@app.command()
def login(
    email: str = typer.Option(..., prompt=True),
    password: str = typer.Option(..., prompt=True, hide_input=True),
    api_url: str = typer.Option(API_URL, envvar="SCILIBRARIAN_API_URL"),
):
    """Authenticate with the SciLibrarian server."""
    with httpx.Client(base_url=api_url) as client:
        resp = client.post("/auth/login", json={"email": email, "password": password})
        if resp.status_code != 200:
            typer.echo(f"Login failed: {resp.json().get('detail', 'unknown error')}", err=True)
            raise typer.Exit(1)
        data = resp.json()
        _save_token(data["access_token"])
        typer.echo(f"Logged in as {data['user']['name']} ({data['user']['email']})")


@app.command()
def projects(api_url: str = typer.Option(API_URL, envvar="SCILIBRARIAN_API_URL")):
    """List all projects."""
    token = _load_token()
    with httpx.Client(base_url=api_url, headers={"Authorization": f"Bearer {token}"}) as client:
        resp = client.get("/projects")
        resp.raise_for_status()
        for p in resp.json():
            typer.echo(f"[{p['id']}] {p['name']} — {p['description'][:60]}...")


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="PDF file or URL to ingest"),
    project_id: int = typer.Option(..., "--project", "-p", help="Project ID"),
    collection_id: Optional[int] = typer.Option(None, "--collection", "-c"),
    model: str = typer.Option("claude-sonnet-4-6", "--model"),
    api_url: str = typer.Option(API_URL, envvar="SCILIBRARIAN_API_URL"),
):
    """Ingest a PDF file or URL into the library."""
    token = _load_token()
    headers = {"Authorization": f"Bearer {token}"}

    url_str = str(path)
    is_url = url_str.startswith("http://") or url_str.startswith("https://")

    with httpx.Client(base_url=api_url, headers=headers, timeout=120) as client:
        if is_url:
            typer.echo(f"Ingesting URL: {url_str}")
            params = {"url": url_str, "model": model}
            if collection_id:
                params["collection_id"] = collection_id
            resp = client.post("/references/from-url", params=params)
        else:
            if not path.exists():
                typer.echo(f"File not found: {path}", err=True)
                raise typer.Exit(1)
            typer.echo(f"Ingesting PDF: {path.name}")
            with open(path, "rb") as f:
                data = {"model": model}
                if collection_id:
                    data["collection_id"] = str(collection_id)
                resp = client.post("/references/upload", files={"file": (path.name, f, "application/pdf")}, data=data)

        if resp.status_code not in (200, 201):
            typer.echo(f"Ingestion failed: {resp.text}", err=True)
            raise typer.Exit(1)

        ref = resp.json()
        typer.echo(f"\nAdded: {ref['title']}")
        if ref.get("authors"):
            typer.echo(f"Authors: {ref['authors']}")
        if ref.get("year"):
            typer.echo(f"Year: {ref['year']}")
        typer.echo(f"Type: {ref['source_type']}")
        if ref.get("summary"):
            typer.echo(f"\nSummary: {ref['summary'][:300]}...")


@app.command()
def ingest_dir(
    directory: Path = typer.Argument(..., help="Directory of PDFs (searched recursively)"),
    project_id: int = typer.Option(..., "--project", "-p"),
    collection_id: Optional[int] = typer.Option(None, "--collection", "-c"),
    model: str = typer.Option("claude-sonnet-4-6", "--model"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", help="Search subdirectories"),
    api_url: str = typer.Option(API_URL, envvar="SCILIBRARIAN_API_URL"),
):
    """Batch ingest all PDFs in a directory (recursive by default)."""
    pattern = "**/*.pdf" if recursive else "*.pdf"
    pdfs = sorted(directory.glob(pattern))
    if not pdfs:
        typer.echo(f"No PDFs found in {directory}{' (recursive)' if recursive else ''}")
        raise typer.Exit(0)

    typer.echo(f"Found {len(pdfs)} PDFs to ingest\n")
    ok, failed = 0, 0
    for i, pdf in enumerate(pdfs, 1):
        typer.echo(f"[{i}/{len(pdfs)}] {pdf.relative_to(directory)}")
        try:
            ingest(pdf, project_id=project_id, collection_id=collection_id, model=model, api_url=api_url)
            ok += 1
        except Exception as e:
            typer.echo(f"  ✗ Failed: {e}", err=True)
            failed += 1

    typer.echo(f"\n{'─'*40}")
    typer.echo(f"Done: {ok} succeeded, {failed} failed")


@app.command()
def ingest_urls(
    urls_file: Path = typer.Argument(..., help="Text file with one URL per line"),
    project_id: int = typer.Option(..., "--project", "-p"),
    collection_id: Optional[int] = typer.Option(None, "--collection", "-c"),
    model: str = typer.Option("claude-sonnet-4-6", "--model"),
    api_url: str = typer.Option(API_URL, envvar="SCILIBRARIAN_API_URL"),
):
    """Batch ingest URLs from a text file (one URL per line)."""
    if not urls_file.exists():
        typer.echo(f"File not found: {urls_file}", err=True)
        raise typer.Exit(1)

    urls = [u.strip() for u in urls_file.read_text().splitlines() if u.strip() and not u.startswith("#")]
    if not urls:
        typer.echo("No URLs found in file")
        raise typer.Exit(0)

    typer.echo(f"Found {len(urls)} URLs to ingest\n")
    token = _load_token()

    with httpx.Client(base_url=api_url, headers={"Authorization": f"Bearer {token}"}, timeout=600) as client:
        resp = client.post(
            "/references/from-urls-bulk",
            json={"urls": urls, "model": model, "collection_id": collection_id},
        )
        resp.raise_for_status()
        data = resp.json()

    typer.echo(f"\n{'─'*40}")
    typer.echo(f"Done: {data['succeeded']}/{data['total']} succeeded")
    for r in data.get("results", []):
        typer.echo(f"  ✓ {r['title']}")
    for e in data.get("errors", []):
        typer.echo(f"  ✗ {e['url']}: {e['error']}", err=True)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    project_id: Optional[int] = typer.Option(None, "--project", "-p"),
    source_type: Optional[str] = typer.Option(None, "--type", "-t"),
    limit: int = typer.Option(10, "--limit", "-n"),
    api_url: str = typer.Option(API_URL, envvar="SCILIBRARIAN_API_URL"),
):
    """Search the reference library."""
    token = _load_token()
    params = {"q": query, "limit": limit}
    if source_type:
        params["source_type"] = source_type

    with httpx.Client(base_url=api_url, headers={"Authorization": f"Bearer {token}"}) as client:
        resp = client.get("/search", params=params)
        resp.raise_for_status()
        data = resp.json()

    typer.echo(f"\nFound {data['total']} results for '{query}'\n")
    for ref in data["results"]:
        typer.echo(f"[{ref['id']}] {ref['title']}")
        if ref.get("authors"):
            typer.echo(f"     {ref['authors'][:60]} ({ref.get('year', 'n.d.')})")
        typer.echo(f"     Type: {ref['source_type']}")
        typer.echo()


@app.command()
def digest(
    project_id: int = typer.Option(..., "--project", "-p"),
    month: Optional[int] = typer.Option(None, "--month", "-m", help="Month (1-12), defaults to last month"),
    year: Optional[int] = typer.Option(None, "--year", "-y", help="Year, defaults to current"),
    api_url: str = typer.Option(API_URL, envvar="SCILIBRARIAN_API_URL"),
):
    """Generate or display a monthly digest."""
    from datetime import date
    import calendar

    now = date.today()
    y = year or now.year
    m = month or (now.month - 1 or 12)
    if month is None and now.month == 1:
        y -= 1

    _, last_day = calendar.monthrange(y, m)
    period_start = datetime(y, m, 1, tzinfo=timezone.utc)
    period_end = datetime(y, m, last_day, 23, 59, 59, tzinfo=timezone.utc)

    token = _load_token()
    typer.echo(f"Generating digest for {period_start.strftime('%B %Y')}...")

    with httpx.Client(base_url=api_url, headers={"Authorization": f"Bearer {token}"}, timeout=120) as client:
        resp = client.post(
            f"/projects/{project_id}/digests",
            json={
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            },
        )
        resp.raise_for_status()
        d = resp.json()

    typer.echo("\n" + "=" * 60)
    typer.echo(d["content"])
    typer.echo("=" * 60)


if __name__ == "__main__":
    app()
