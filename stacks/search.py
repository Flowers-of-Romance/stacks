"""Search for similar pages using vector embeddings."""
import sqlite3
from dataclasses import dataclass

from stacks.db import search_similar
from stacks.embedder import embed_text


@dataclass
class SearchResult:
    doc_id: int
    filename: str
    filepath: str
    page_num: int
    content: str
    summary: str | None
    distance: float


def search(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[SearchResult]:
    """Embed query and search for similar pages."""
    embedding = embed_text(query)
    rows = search_similar(conn, embedding, limit=limit)
    return [
        SearchResult(
            doc_id=r["doc_id"],
            filename=r["filename"],
            filepath=r["filepath"],
            page_num=r["page_num"],
            content=r["content"],
            summary=r["summary"],
            distance=r["distance"],
        )
        for r in rows
    ]


def format_results(results: list[SearchResult]) -> str:
    """Format search results for CLI display."""
    if not results:
        return "No results found."

    lines = []
    for r in results:
        snippet = r.summary if r.summary else r.content[:80]
        lines.append(f"\U0001f4c4 {r.filename} (p.{r.page_num}) [score: {r.distance:.3f}]")
        lines.append(f"  {snippet}")
        lines.append("")
    return "\n".join(lines)
