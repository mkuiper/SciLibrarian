"""
File content extractors for non-PDF types.
Each returns (title: str, text: str) suitable for the metadata generation pipeline.

Supported:
  PDF    — handled separately in ingestion.py via PyMuPDF
  DOCX   — Microsoft Word documents
  TXT/MD/RST — plain text and markdown
  CSV/TSV — tabular data; extracts shape, columns, sample rows, statistics
  XLSX/XLS — Excel spreadsheets; same tabular summary
  PDB    — Protein Data Bank structure files; extracts molecule/experiment metadata
  JSON   — structured data files
"""
import io
import re
from pathlib import Path


# ── Plain text ────────────────────────────────────────────────────────────────

def extract_text(content: bytes, filename: str) -> tuple[str, str]:
    text = content.decode("utf-8", errors="replace").replace("\x00", "")
    title = Path(filename).stem.replace("_", " ").replace("-", " ")
    return title, text[:50000]


# ── DOCX ──────────────────────────────────────────────────────────────────────

def extract_docx(content: bytes, filename: str) -> tuple[str, str]:
    try:
        from docx import Document
        doc = Document(io.BytesIO(content))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        title = paragraphs[0] if paragraphs else Path(filename).stem
        text = "\n\n".join(paragraphs)
        return title, text[:50000]
    except Exception as e:
        return Path(filename).stem, f"[Could not extract DOCX: {e}]"


# ── CSV / TSV ─────────────────────────────────────────────────────────────────

def extract_csv(content: bytes, filename: str, sep: str = ",") -> tuple[str, str]:
    try:
        import pandas as pd
        df = pd.read_csv(io.BytesIO(content), sep=sep, low_memory=False, nrows=10000)
        df = df.fillna("")

        lines = [
            f"File: {filename}",
            f"Shape: {df.shape[0]} rows × {df.shape[1]} columns",
            f"Columns: {', '.join(str(c) for c in df.columns.tolist())}",
            "",
            "Data types:",
            *[f"  {col}: {dtype}" for col, dtype in df.dtypes.items()],
            "",
            "Sample rows (first 5):",
            df.head(5).to_string(index=False),
        ]

        # Numeric summary if applicable
        numeric = df.select_dtypes(include="number")
        if not numeric.empty:
            lines += ["", "Numeric summary:", numeric.describe().to_string()]

        title = Path(filename).stem.replace("_", " ").replace("-", " ")
        return title, "\n".join(lines)[:50000]
    except Exception as e:
        return Path(filename).stem, f"[Could not parse CSV: {e}]"


def extract_excel(content: bytes, filename: str) -> tuple[str, str]:
    try:
        import pandas as pd
        xl = pd.ExcelFile(io.BytesIO(content))
        parts = [f"File: {filename}", f"Sheets: {', '.join(xl.sheet_names)}", ""]
        for sheet in xl.sheet_names[:5]:  # first 5 sheets
            df = xl.parse(sheet, nrows=10000).fillna("")
            parts += [
                f"=== Sheet: {sheet} ===",
                f"Shape: {df.shape[0]} rows × {df.shape[1]} columns",
                f"Columns: {', '.join(str(c) for c in df.columns.tolist())}",
                df.head(5).to_string(index=False),
                "",
            ]
        title = Path(filename).stem.replace("_", " ").replace("-", " ")
        return title, "\n".join(parts)[:50000]
    except Exception as e:
        return Path(filename).stem, f"[Could not parse Excel: {e}]"


# ── PDB (Protein Data Bank) ───────────────────────────────────────────────────

def extract_pdb(content: bytes, filename: str) -> tuple[str, str]:
    """
    Parse PDB format structure file. Extracts:
    - Molecule name, compound, source organism
    - Experimental method and resolution
    - Chains and residue count
    - Authors and citation
    No external library needed — PDB is a fixed-width text format.
    """
    text = content.decode("utf-8", errors="replace").replace("\x00", "")
    lines = text.splitlines()

    def get_records(tag: str) -> list[str]:
        return [l[10:].strip() for l in lines if l.startswith(tag)]

    def get_continuation(tag: str) -> str:
        return " ".join(get_records(tag))

    title_lines = get_records("TITLE     ") or get_records("TITLE")
    compound_lines = get_records("COMPND")
    source_lines = get_records("SOURCE")
    remark_lines = [l for l in lines if l.startswith("REMARK")]
    author_lines = get_records("AUTHOR")
    seqres_chains = set(l[11] for l in lines if l.startswith("SEQRES") and len(l) > 11)

    # Resolution from REMARK 2
    resolution = None
    for r in remark_lines:
        if "RESOLUTION" in r and "ANGSTROMS" in r:
            m = re.search(r"([\d.]+)\s+ANGSTROMS", r)
            if m:
                resolution = m.group(1)
                break

    # Experimental method from EXPDTA
    method = get_continuation("EXPDTA") or "Unknown"

    # Organism
    source_text = " ".join(source_lines)
    organism_m = re.search(r"ORGANISM_SCIENTIFIC:\s*([^;]+)", source_text, re.I)
    organism = organism_m.group(1).strip() if organism_m else ""

    # Molecule name
    compound_text = " ".join(compound_lines)
    mol_m = re.search(r"MOLECULE:\s*([^;]+)", compound_text, re.I)
    molecule = mol_m.group(1).strip() if mol_m else ""

    pdb_id = Path(filename).stem.upper()
    title_str = " ".join(title_lines) or molecule or pdb_id

    summary_parts = [
        f"PDB ID: {pdb_id}",
        f"Molecule: {molecule}" if molecule else "",
        f"Organism: {organism}" if organism else "",
        f"Method: {method}",
        f"Resolution: {resolution} Å" if resolution else "",
        f"Chains: {', '.join(sorted(seqres_chains))}" if seqres_chains else "",
        f"Authors: {' '.join(author_lines)}" if author_lines else "",
        "",
        "Full header:",
        "\n".join(l for l in lines if l.startswith(("HEADER", "TITLE", "COMPND", "SOURCE",
                                                      "EXPDTA", "AUTHOR", "REMARK", "SEQRES"))
                  )[:20000],
    ]

    return title_str or pdb_id, "\n".join(p for p in summary_parts if p)[:50000]


# ── JSON ──────────────────────────────────────────────────────────────────────

def extract_json(content: bytes, filename: str) -> tuple[str, str]:
    import json
    try:
        data = json.loads(content.decode("utf-8", errors="replace"))
        text = json.dumps(data, indent=2)[:50000]
        title = Path(filename).stem.replace("_", " ").replace("-", " ")
        return title, text
    except Exception as e:
        return Path(filename).stem, f"[Could not parse JSON: {e}]"


# ── Dispatcher ────────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {
    # Documents
    ".pdf":  None,  # handled by PyMuPDF in ingestion.py
    ".docx": extract_docx,
    ".doc":  extract_docx,  # may not work for old .doc binary format
    ".txt":  extract_text,
    ".md":   extract_text,
    ".rst":  extract_text,
    ".tex":  extract_text,
    # Data
    ".csv":  extract_csv,
    ".tsv":  lambda c, f: extract_csv(c, f, sep="\t"),
    ".xlsx": extract_excel,
    ".xls":  extract_excel,
    ".json": extract_json,
    # Biology / Chemistry
    ".pdb":  extract_pdb,
    ".ent":  extract_pdb,  # alternative PDB extension
    ".cif":  extract_text, # mmCIF — treat as text for now
    ".sdf":  extract_text, # chemical structure data file
    ".mol":  extract_text,
    ".mol2": extract_text,
    ".fasta": extract_text,
    ".fa":   extract_text,
}

ACCEPTED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain", "text/markdown", "text/csv", "text/tab-separated-values",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/json",
    "chemical/x-pdb", "application/octet-stream",
}


def get_extractor(filename: str):
    ext = Path(filename).suffix.lower()
    return SUPPORTED_EXTENSIONS.get(ext)


def is_supported(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS
