"""Management commands: list, remove, info."""
import sqlite3

from stacks.db import list_documents, delete_document, get_document_info


def cmd_list(conn: sqlite3.Connection) -> str:
    """List all documents as a formatted table."""
    docs = list_documents(conn)
    if not docs:
        return "No documents found."

    header = f"{'ID':>4}  {'Filename':<30}  {'Format':<6}  {'Pages':>5}  {'Created'}"
    sep = "-" * len(header)
    lines = [header, sep]
    for d in docs:
        pages = d["page_count"] if d["page_count"] is not None else "?"
        created = d["created_at"][:10] if d["created_at"] else ""
        lines.append(
            f"{d['id']:>4}  {d['filename']:<30}  {d['format']:<6}  {pages:>5}  {created}"
        )
    return "\n".join(lines)


def cmd_remove(conn: sqlite3.Connection, doc_id: int) -> str:
    """Remove a document by id. Returns confirmation or error."""
    info = get_document_info(conn, doc_id)
    if info is None:
        return f"Error: document {doc_id} not found."
    filename = info["document"]["filename"]
    delete_document(conn, doc_id)
    return f"Removed document {doc_id} ({filename})."


def cmd_info(conn: sqlite3.Connection, doc_id: int) -> str:
    """Show detailed info for a document."""
    info = get_document_info(conn, doc_id)
    if info is None:
        return f"Error: document {doc_id} not found."

    doc = info["document"]
    pages = info["pages"]
    size = format_file_size(doc["file_size_bytes"] or 0)

    lines = [
        f"Document: {doc['filename']}",
        f"  Path:    {doc['filepath']}",
        f"  Format:  {doc['format']}",
        f"  Size:    {size}",
        f"  Pages:   {doc['page_count'] or len(pages)}",
        f"  Hash:    {doc['file_hash']}",
        f"  Created: {doc['created_at']}",
        "",
        "Pages:",
    ]
    for p in pages:
        ct = p["content_type"] or "?"
        tokens = p["token_count"] or "?"
        lines.append(f"  p.{p['page_num']:>3}  [{ct}]  ~{tokens} tokens")

    return "\n".join(lines)


def format_file_size(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes == 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            if unit == "B":
                return f"{size_bytes} B"
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"
