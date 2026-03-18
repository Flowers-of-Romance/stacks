"""File discovery, preparation, and page storage."""
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from stacks.config import get_stacks_root, get_converted_dir
from stacks.converter import is_supported_format, check_excel_limits, convert_to_pdf, get_page_count
from stacks.db import insert_document, find_document_by_hash, insert_page, insert_embedding
from stacks.embedder import embed_text


def store_page(
    conn: sqlite3.Connection,
    doc_id: int,
    page_num: int,
    content: str,
    summary: str | None,
    content_type: str | None = None,
    sheet_name: str | None = None,
) -> int:
    """Store a page and its embedding. Returns page_id."""
    if content_type is None:
        content_type = detect_content_type(content)
    token_count = estimate_token_count(content)
    quality = compute_quality_score(content)

    page_id = insert_page(
        conn, doc_id, page_num, content, summary,
        content_type, token_count, sheet_name=sheet_name,
        quality_score=quality,
    )

    embedding = embed_text(content)
    insert_embedding(conn, page_id, embedding)

    return page_id


def detect_content_type(content: str) -> str:
    """Detect whether content is table, figure, mixed, or text."""
    has_table = bool(re.search(r"\|.+\|", content))
    has_figure = bool(re.search(r"(?i)\bfigure\s+\d", content))

    if has_table and has_figure:
        return "mixed"
    if has_table:
        return "table"
    if has_figure:
        return "figure"
    return "text"


def estimate_token_count(content: str) -> int:
    """Rough token estimate: len(content) // 3."""
    return len(content) // 3


def compute_quality_score(content: str) -> float:
    """Compute a 0.0-1.0 quality score for extracted text.

    Factors:
    - Length (very short = low quality)
    - Readable character ratio (CJK + Latin + digits + common punctuation)
    - Unique character variety (repetitive text = low quality)
    """
    text = content.strip()
    if not text:
        return 0.0

    length = len(text)

    # Length factor: ramp from 0 to 1 over 20-200 chars
    length_score = min(1.0, max(0.0, (length - 20) / 180))

    # Readable character ratio
    readable = sum(
        1 for c in text
        if c.isalnum() or c in ' \t\n。、．，・：；！？「」『』（）()[]{}+-=/<>%&#@'
        or '\u3000' <= c <= '\u9fff' or '\uff00' <= c <= '\uffef'
    )
    readable_ratio = readable / length

    # Variety: unique chars / total chars (capped)
    unique_ratio = min(1.0, len(set(text)) / min(length, 200))

    return round(length_score * 0.3 + readable_ratio * 0.5 + unique_ratio * 0.2, 3)


def is_readable_text(content: str, min_chars: int = 20) -> bool:
    """Check if extracted text is readable (not garbled/empty)."""
    return compute_quality_score(content) > 0.3


# ── File discovery and preparation (TASK-0006) ──


def scan_files(path: str | Path) -> list[Path]:
    """Recursively find supported files under path."""
    root = get_stacks_root()
    target = root / Path(path)
    if not target.exists():
        return []
    if target.is_file():
        return [target] if is_supported_format(target) else []
    files = []
    for p in sorted(target.rglob("*")):
        if p.is_file() and is_supported_format(p):
            files.append(p)
    return files


def compute_file_hash(filepath: str | Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def prepare_files(conn: sqlite3.Connection, path: str) -> dict:
    """Discover, validate, convert, and register files. Returns JSON-serializable dict."""
    root = get_stacks_root()
    files_out = []
    skipped = []

    candidates = scan_files(path)

    for fpath in candidates:
        rel = fpath.relative_to(root)

        # Duplicate check
        file_hash = compute_file_hash(fpath)
        existing = find_document_by_hash(conn, file_hash)
        if existing is not None:
            skipped.append({"file": str(rel), "reason": "Already ingested"})
            continue

        fmt = fpath.suffix.lower().lstrip(".")

        # Excel limits
        if fmt in ("xlsx", "xls"):
            ok, reason = check_excel_limits(fpath)
            if not ok:
                skipped.append({"file": str(rel), "reason": reason})
                continue

        # PDF conversion
        if fmt == "pdf":
            pdf_path = fpath
        else:
            try:
                converted_dir = get_converted_dir()
                pdf_path = convert_to_pdf(fpath, converted_dir)
            except RuntimeError as e:
                skipped.append({"file": str(rel), "reason": str(e)})
                continue

        # Page count
        try:
            total_pages = get_page_count(pdf_path)
        except Exception:
            total_pages = 0

        # Register in DB
        file_size = fpath.stat().st_size
        doc_id = insert_document(
            conn,
            filename=fpath.name,
            filepath=str(rel),
            format=fmt,
            file_hash=file_hash,
            page_count=total_pages,
            file_size_bytes=file_size,
        )

        pdf_rel = pdf_path.relative_to(root) if pdf_path != fpath else rel

        files_out.append({
            "doc_id": doc_id,
            "original": str(rel),
            "pdf_path": str(pdf_rel),
            "total_pages": total_pages,
            "format": fmt,
            "status": "ready",
        })

    return {"files": files_out, "skipped": skipped}


def _extract_page_text(pdf_path: Path, page_num: int) -> str:
    """Extract text from a single PDF page (1-indexed)."""
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    if page_num < 1 or page_num > len(reader.pages):
        return ""
    return reader.pages[page_num - 1].extract_text() or ""


MAX_INGEST_PAGES = 1000


def ingest_document(
    conn: sqlite3.Connection,
    doc_id: int,
    source_path: str | Path,
    on_progress=None,
) -> int:
    """Extract text from all pages and store with embeddings.

    Uses native extraction for pptx/docx/xlsx, falls back to PDF.
    Returns the number of pages ingested.
    """
    from stacks.converter import extract_pages_native

    source_path = Path(source_path)
    pages = extract_pages_native(source_path)
    total = len(pages)
    count = 0

    for i, text in enumerate(pages, 1):
        if not text.strip():
            continue
        if not is_readable_text(text):
            continue
        store_page(conn, doc_id=doc_id, page_num=i, content=text, summary=None)
        count += 1
        if on_progress:
            on_progress(i, total)

    return count


def ingest_all(conn: sqlite3.Connection, path: str, on_progress=None) -> dict:
    """Prepare and ingest all files under path in one shot.

    Returns a summary dict with ingested/skipped lists.
    """
    root = get_stacks_root()
    result = prepare_files(conn, path)

    ingested = []
    for f in result["files"]:
        if f["total_pages"] > MAX_INGEST_PAGES:
            result["skipped"].append({
                "file": f["original"],
                "reason": f"Too many pages: {f['total_pages']} (max {MAX_INGEST_PAGES})",
            })
            continue
        doc_id = f["doc_id"]
        source = root / f["original"]
        count = ingest_document(conn, doc_id, source, on_progress=on_progress)
        ingested.append({
            "doc_id": doc_id,
            "original": f["original"],
            "pages_ingested": count,
            "total_pages": f["total_pages"],
        })

    # Also ingest any previously prepared but not yet stored documents
    rows = conn.execute(
        """SELECT d.id, d.filepath, d.format, d.page_count
           FROM documents d
           WHERE NOT EXISTS (SELECT 1 FROM pages p WHERE p.doc_id = d.id)"""
    ).fetchall()

    for row in rows:
        doc_id = row[0]
        filepath = row[1]
        fmt = row[2]
        page_count = row[3] or 0
        # Already handled in this batch?
        if any(item["doc_id"] == doc_id for item in ingested):
            continue
        if page_count > MAX_INGEST_PAGES:
            result["skipped"].append({
                "file": filepath,
                "reason": f"Too many pages: {page_count} (max {MAX_INGEST_PAGES})",
            })
            continue

        source = root / filepath
        if not source.exists():
            continue

        count = ingest_document(conn, doc_id, source, on_progress=on_progress)
        ingested.append({
            "doc_id": doc_id,
            "original": filepath,
            "pages_ingested": count,
            "total_pages": row[3] or 0,
        })

    return {"ingested": ingested, "skipped": result["skipped"]}
