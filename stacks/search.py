"""Hybrid search: vector similarity + full-text search."""
import sqlite3
from dataclasses import dataclass

from stacks.db import search_similar, search_fts
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
    """Hybrid search: combine vector similarity and full-text search."""
    # Vector search
    embedding = embed_text(query)
    vec_rows = search_similar(conn, embedding, limit=limit * 3)

    # Full-text search (may fail if query has FTS syntax issues)
    fts_rows = []
    try:
        fts_rows = search_fts(conn, query, limit=limit * 3)
    except Exception:
        pass

    # Build score maps keyed by page_id
    # Vector: normalize distance to 0-1 (lower = better)
    vec_scores = {}
    if vec_rows:
        max_dist = max(r["distance"] for r in vec_rows) or 1.0
        for r in vec_rows:
            vec_scores[r["page_id"]] = 1.0 - (r["distance"] / max_dist)

    # FTS: normalize rank (FTS5 rank is negative, more negative = better)
    fts_scores = {}
    if fts_rows:
        min_rank = min(r["fts_rank"] for r in fts_rows) or -1.0
        for r in fts_rows:
            fts_scores[r["page_id"]] = r["fts_rank"] / min_rank if min_rank != 0 else 0

    # Merge: collect all page_ids
    all_pages = {}
    for r in vec_rows:
        all_pages[r["page_id"]] = r
    for r in fts_rows:
        if r["page_id"] not in all_pages:
            all_pages[r["page_id"]] = r

    # Combined score: vec * 0.5 + fts * 0.5
    VEC_WEIGHT = 0.5
    FTS_WEIGHT = 0.5
    scored = []
    for page_id, r in all_pages.items():
        vs = vec_scores.get(page_id, 0.0)
        fs = fts_scores.get(page_id, 0.0)
        combined = vs * VEC_WEIGHT + fs * FTS_WEIGHT
        scored.append((combined, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    return [
        SearchResult(
            doc_id=r["doc_id"],
            filename=r["filename"],
            filepath=r["filepath"],
            page_num=r["page_num"],
            content=r["content"],
            summary=r["summary"],
            distance=1.0 - score,  # convert back to distance-like (lower = better)
        )
        for score, r in scored[:limit]
    ]


def _extract_snippet(content: str, query: str, length: int = 120) -> str:
    """Extract a snippet from content near the best matching query term."""
    content_lower = content.lower()
    query_lower = query.lower()

    # Try to find query terms in content
    terms = query_lower.split()
    best_pos = -1
    best_len = 0
    for term in terms:
        pos = content_lower.find(term)
        if pos >= 0 and len(term) > best_len:
            best_pos = pos
            best_len = len(term)

    if best_pos >= 0:
        # Center snippet around the match
        start = max(0, best_pos - length // 3)
        end = min(len(content), start + length)
        snippet = content[start:end].replace("\n", " ").strip()
        if start > 0:
            snippet = "…" + snippet
        if end < len(content):
            snippet = snippet + "…"
        return snippet

    # Fallback: first N chars
    snippet = content[:length].replace("\n", " ").strip()
    if len(content) > length:
        snippet += "…"
    return snippet


def format_results(results: list[SearchResult], query: str = "") -> str:
    """Format search results for CLI display."""
    if not results:
        return "No results found."

    lines = []
    for r in results:
        snippet = r.summary if r.summary else _extract_snippet(r.content, query)
        relevance = 1.0 - r.distance
        lines.append(f"\U0001f4c4 {r.filename} (p.{r.page_num}) [score: {relevance:.3f}]")
        lines.append(f"  {snippet}")
        lines.append("")
    return "\n".join(lines)
