"""Hybrid search: vector similarity + full-text search."""
import hashlib
import html
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

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
    image_path: str | None = None


def search(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[SearchResult]:
    """Hybrid search: RRF scoring with document-level aggregation."""
    from collections import defaultdict

    # Retrieve candidates (wider net than final limit)
    embedding = embed_text(query)
    candidate_limit = max(limit * 5, 30)
    vec_rows = search_similar(conn, embedding, limit=candidate_limit)

    fts_rows = []
    try:
        fts_rows = search_fts(conn, query, limit=candidate_limit)
    except Exception:
        pass

    # Step 1: Page-level RRF (Reciprocal Rank Fusion)
    K = 60
    page_scores = defaultdict(float)
    page_data = {}

    for rank, r in enumerate(vec_rows, 1):
        page_scores[r["page_id"]] += 1.0 / (K + rank)
        page_data[r["page_id"]] = r

    for rank, r in enumerate(fts_rows, 1):
        page_scores[r["page_id"]] += 1.0 / (K + rank)
        if r["page_id"] not in page_data:
            page_data[r["page_id"]] = r

    # Boost: pages in both sources get priority over single-source hits
    fts_pids = {r["page_id"] for r in fts_rows}
    vec_pids = {r["page_id"] for r in vec_rows}
    for pid in fts_pids & vec_pids:
        page_scores[pid] *= 1.5

    # Step 2: Document-level aggregation (top pages per doc, max 3)
    MAX_PER_DOC = 3
    doc_pages = defaultdict(list)
    for pid, score in page_scores.items():
        r = page_data[pid]
        doc_pages[r["doc_id"]].append((score, r))
    for doc_id in doc_pages:
        doc_pages[doc_id].sort(key=lambda x: x[0], reverse=True)
        doc_pages[doc_id] = doc_pages[doc_id][:MAX_PER_DOC]

    # Step 3: Rank documents by best page, then expand
    doc_scores = {did: pages[0][0] for did, pages in doc_pages.items()}
    ranked_doc_ids = sorted(doc_scores, key=doc_scores.get, reverse=True)

    results = []
    for doc_id in ranked_doc_ids:
        results.extend(doc_pages[doc_id])

    # Filter: drop results below 30% of top score
    if results:
        threshold = results[0][0] * 0.3
        results = [(s, r) for s, r in results if s >= threshold]

    top = results[:limit]

    return [
        SearchResult(
            doc_id=r["doc_id"],
            filename=r["filename"],
            filepath=r["filepath"],
            page_num=r["page_num"],
            content=r["content"],
            summary=r["summary"],
            distance=1.0 - score,
            image_path=r.get("image_path"),
        )
        for score, r in top
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


def generate_highlighted_pdfs(
    results: list[SearchResult], query: str
) -> dict[int, str]:
    """Generate highlighted PDFs for search results.

    Returns a mapping of doc_id -> highlighted PDF file URI.
    """
    from stacks.config import get_stacks_root, get_converted_dir, get_highlighted_dir

    import unicodedata
    normalized = unicodedata.normalize("NFKC", query)
    terms = [t for t in normalized.split() if t]
    if not terms:
        return {}

    root = get_stacks_root()
    highlighted_dir = get_highlighted_dir()
    query_hash = hashlib.md5(query.encode()).hexdigest()[:8]

    # Group results by doc_id, collecting hit pages (resolved to PDF pages)
    doc_pages: dict[int, list[int]] = defaultdict(list)
    doc_info: dict[int, SearchResult] = {}
    for r in results:
        if r.filepath.lower().endswith(".pdf"):
            doc_pages[r.doc_id].append(r.page_num)
        else:
            pdf_page = _find_pdf_page(r.content, r.filepath)
            if pdf_page:
                doc_pages[r.doc_id].append(pdf_page)
            # If not found, hit_pages will be empty → fallback to all pages in create_highlighted_pdf
        if r.doc_id not in doc_info:
            doc_info[r.doc_id] = r

    result_map: dict[int, str] = {}
    for doc_id, pages in doc_pages.items():
        r = doc_info[doc_id]
        output_path = highlighted_dir / f"{doc_id}_{query_hash}.pdf"

        # Cache: skip if already exists
        if output_path.exists():
            result_map[doc_id] = output_path.as_uri()
            continue

        # Resolve source PDF
        if r.filepath.lower().endswith(".pdf"):
            pdf_path = root / r.filepath
        else:
            pdf_path = get_converted_dir() / f"{Path(r.filepath).stem}.pdf"

        if not pdf_path.exists():
            continue

        try:
            from stacks.converter import create_highlighted_pdf
            create_highlighted_pdf(pdf_path, terms, pages, output_path)
            result_map[doc_id] = output_path.as_uri()
        except Exception:
            continue

    return result_map


def format_results(results: list[SearchResult], query: str = "") -> str:
    """Format search results for CLI display."""
    if not results:
        return "No results found."

    from stacks.config import get_stacks_root
    root = get_stacks_root()
    lines = []
    for r in results:
        snippet = r.summary if r.summary else _extract_snippet(r.content, query)
        relevance = 1.0 - r.distance
        lines.append(f"\U0001f4c4 {r.filename} (p.{r.page_num}) [score: {relevance:.3f}]")
        lines.append(f"  {snippet}")
        lines.append(f"  -> {root / r.filepath}")
        lines.append("")
    return "\n".join(lines)


def _find_pdf_page(content: str, filepath: str) -> int | None:
    """Find which page of the converted PDF contains the chunk's text.

    Returns 1-indexed page number, or None if not found.
    """
    from stacks.config import get_converted_dir
    import unicodedata
    import re as _re

    converted_pdf = get_converted_dir() / f"{Path(filepath).stem}.pdf"
    if not converted_pdf.exists():
        return None

    def _normalize(s):
        """Normalize and strip whitespace for fuzzy matching."""
        s = unicodedata.normalize("NFKC", s)
        return _re.sub(r'\s+', '', s)

    try:
        import fitz
        doc = fitz.open(str(converted_pdf))
        text = content.strip()
        # Skip [Sheet: ...] header
        if text.startswith("[Sheet:"):
            text = text[text.find("]") + 1:].strip()
        # Extract multiple search fragments for robustness
        normalized = _normalize(text)
        if len(normalized) < 10:
            doc.close()
            return None

        # Try fragments from multiple positions (start may differ between formats)
        for start in range(0, min(len(normalized), 100), 10):
            fragment = normalized[start:start + 30]
            if len(fragment) < 10:
                continue
            for i in range(len(doc)):
                page_normalized = _normalize(doc[i].get_text())
                if fragment in page_normalized:
                    doc.close()
                    return i + 1
        doc.close()
    except Exception:
        pass
    return None


def _resolve_image_path(image_path: str | None) -> str | None:
    """Resolve a relative image path to an absolute file URI."""
    if not image_path:
        return None
    from stacks.config import get_stacks_root
    abs_path = get_stacks_root() / image_path
    if abs_path.exists():
        return abs_path.as_uri()
    return None


def _nav_image_uri(doc_id: int, page_num: int) -> str | None:
    """Return file URI for a neighboring page image, if it exists."""
    from stacks.config import get_images_dir
    img = get_images_dir() / str(doc_id) / f"{page_num}.png"
    if img.exists():
        return img.as_uri()
    return None


def format_results_html(
    results: list[SearchResult],
    query: str = "",
    highlighted_pdfs: dict[int, str] | None = None,
) -> str:
    """Generate an HTML report with page images and navigation."""
    q = html.escape(query)
    highlighted_pdfs = highlighted_pdfs or {}

    from stacks.config import get_stacks_root
    root = get_stacks_root()

    import re as _re

    def _highlight(text: str, query: str) -> str:
        """Wrap query terms in <mark> tags. text must already be HTML-escaped."""
        import unicodedata as _ud
        query = _ud.normalize("NFKC", query)
        text = _ud.normalize("NFKC", text)
        terms = [html.escape(t) for t in query.split() if t]
        if not terms:
            return text
        pattern = "|".join(_re.escape(t) for t in terms)
        return _re.sub(f"({pattern})", r"<mark>\1</mark>", text, flags=_re.IGNORECASE)

    cards = []
    for r in results:
        snippet = html.escape(r.summary if r.summary else _extract_snippet(r.content, query, length=300))
        snippet = _highlight(snippet, query)
        relevance = 1.0 - r.distance
        filename = html.escape(r.filename)
        original_uri = (root / r.filepath).as_uri()
        # Resolve the actual PDF page for this result
        _is_native_pdf = r.filepath.lower().endswith(".pdf")
        if _is_native_pdf:
            _pdf_page = r.page_num
        else:
            _pdf_page = _find_pdf_page(r.content, r.filepath) or 1

        # PDF page link — prefer highlighted version if available
        pdf_uri = None
        _page_frag = f"#page={_pdf_page}"
        if r.doc_id in highlighted_pdfs:
            pdf_uri = highlighted_pdfs[r.doc_id] + _page_frag
        elif _is_native_pdf:
            pdf_uri = original_uri + _page_frag
        else:
            from stacks.config import get_converted_dir
            converted_pdf = get_converted_dir() / f"{Path(r.filepath).stem}.pdf"
            if converted_pdf.exists():
                pdf_uri = converted_pdf.as_uri() + _page_frag

        # Current page image — use resolved PDF page for non-native PDFs
        _img_page = r.page_num if _is_native_pdf else _pdf_page
        if _is_native_pdf:
            img_uri = _resolve_image_path(r.image_path)
        else:
            img_uri = _nav_image_uri(r.doc_id, _img_page)
        img_html = f'<img src="{img_uri}" alt="Page {_img_page}" class="page-img">' if img_uri else '<div class="no-img">No image</div>'

        # Navigation: prev/next
        prev_uri = _nav_image_uri(r.doc_id, _img_page - 1)
        next_uri = _nav_image_uri(r.doc_id, _img_page + 1)

        nav_parts = []
        if prev_uri:
            nav_parts.append(f'<a class="nav-btn" href="#" onclick="showNav(this, \'{prev_uri}\'); return false;">&#9664; p.{_img_page - 1}</a>')
        nav_parts.append(f'<span class="current-page">p.{_img_page}</span>')
        if next_uri:
            nav_parts.append(f'<a class="nav-btn" href="#" onclick="showNav(this, \'{next_uri}\'); return false;">p.{_img_page + 1} &#9654;</a>')
        nav_html = " ".join(nav_parts)

        cards.append(f"""
        <div class="result-card">
          <div class="result-header">
            <span class="file-links">
              <span class="filename copy-path" title="Click to copy path" onclick="copyPath(this, '{html.escape(str(root / r.filepath))}')">{filename}</span>
              {f'<a class="pdf-link" href="{pdf_uri}">PDF p.{_pdf_page}</a>' if pdf_uri else ''}
            </span>
            <span class="score">score: {relevance:.3f}</span>
          </div>
          <div class="result-body">
            <div class="image-col">
              <div class="img-container">{img_html}</div>
              <div class="nav">{nav_html}</div>
            </div>
            <div class="text-col">
              <p class="snippet">{snippet}</p>
            </div>
          </div>
        </div>""")

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>stacks search: {q}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f5f5f5; padding: 20px; color: #333; }}
  h1 {{ font-size: 1.3rem; margin-bottom: 16px; }}
  h1 span {{ color: #0066cc; }}
  .result-card {{ background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.12); margin-bottom: 16px; overflow: hidden; }}
  .result-header {{ display: flex; justify-content: space-between; padding: 10px 16px; background: #fafafa; border-bottom: 1px solid #eee; font-size: 0.9rem; }}
  .file-links {{ display: flex; gap: 12px; align-items: center; }}
  .filename {{ font-weight: 600; color: #0066cc; text-decoration: none; cursor: pointer; }}
  .filename:hover {{ text-decoration: underline; }}
  .copy-path.copied {{ color: #888; }}
  .pdf-link {{ font-size: 0.8rem; color: #fff; background: #d44; padding: 2px 8px; border-radius: 3px; text-decoration: none; }}
  .pdf-link:hover {{ background: #b33; }}
  .score {{ color: #888; }}
  .result-body {{ display: flex; gap: 16px; padding: 16px; }}
  .image-col {{ flex: 0 0 320px; }}
  .text-col {{ flex: 1; min-width: 0; }}
  .img-container {{ border: 1px solid #ddd; border-radius: 4px; overflow: hidden; background: #fafafa; }}
  .page-img {{ width: 100%; height: auto; display: block; }}
  .no-img {{ width: 100%; height: 200px; display: flex; align-items: center; justify-content: center; color: #aaa; }}
  .nav {{ display: flex; align-items: center; justify-content: center; gap: 12px; margin-top: 8px; font-size: 0.85rem; }}
  .nav-btn {{ text-decoration: none; color: #0066cc; padding: 4px 8px; border: 1px solid #0066cc; border-radius: 4px; }}
  .nav-btn:hover {{ background: #0066cc; color: #fff; }}
  .current-page {{ font-weight: 600; }}
  .snippet {{ white-space: pre-wrap; line-height: 1.6; font-size: 0.95rem; }}
  mark {{ background: #fff176; padding: 1px 2px; border-radius: 2px; }}
  @media (max-width: 700px) {{
    .result-body {{ flex-direction: column; }}
    .image-col {{ flex: none; width: 100%; }}
  }}
</style>
</head>
<body>
<h1>stacks search: <span>{q}</span></h1>
{"".join(cards) if cards else "<p>No results found.</p>"}
<script>
function showNav(el, uri) {{
  const container = el.closest('.result-card').querySelector('.img-container');
  container.innerHTML = '<img src="' + uri + '" class="page-img">';
}}
function copyPath(el, path) {{
  navigator.clipboard.writeText(path).then(() => {{
    const orig = el.textContent;
    el.textContent = 'Copied!';
    el.classList.add('copied');
    setTimeout(() => {{ el.textContent = orig; el.classList.remove('copied'); }}, 1500);
  }});
}}
</script>
</body>
</html>"""
