"""CLI entry point for stacks."""
import argparse
import json
import sys

from stacks.db import get_connection, init_db
from stacks.config import get_db_path


def cmd_init(args):
    import shutil
    db_path = get_db_path()
    if args.reset and db_path.exists():
        db_path.unlink()
        # Clean up WAL/SHM files
        for suffix in ("-wal", "-shm"):
            p = db_path.parent / (db_path.name + suffix)
            if p.exists():
                p.unlink()
        # Clean up generated images
        from stacks.config import get_images_dir, get_stacks_root
        images_dir = get_stacks_root() / ".stacks" / "images"
        if images_dir.exists():
            shutil.rmtree(images_dir)
        print(f"Removed existing database and images.")
    conn = get_connection()
    init_db(conn)
    conn.close()
    print(f"Initialized stacks database at {db_path}")


def cmd_prepare(args):
    from stacks.prepare import prepare_files
    conn = get_connection()
    init_db(conn)
    result = prepare_files(conn, args.path)
    conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_ingest(args):
    from stacks.prepare import ingest_all
    from stacks.db import init_db
    conn = get_connection()
    init_db(conn)

    def progress(phase, current, total, extra=None):
        if phase == "file":
            # current=filename, total=total_files, extra=file_idx
            print(f"\n[{extra}/{total}] {current}", flush=True)
        elif phase == "extract":
            print(f"\r  extracting text...", end="", flush=True)
        elif phase == "images":
            print(f"\r  generating images...", end="", flush=True)
        elif phase == "images_done":
            print(f"\r  images: {current} pages    ", end="", flush=True)
        elif phase == "embed":
            print(f"\r  embed: {current}/{total}", end="", flush=True)

    result = ingest_all(conn, args.path, on_progress=progress, generate_images=not args.no_images)
    conn.close()

    print()
    for item in result["ingested"]:
        print(f"  {item['original']}: {item['pages_ingested']}/{item['total_pages']} pages")
    if result["skipped"]:
        print(f"\nSkipped: {len(result['skipped'])} files")
        for s in result["skipped"]:
            print(f"  {s['file']}: {s['reason']}")
    total_pages = sum(item["pages_ingested"] for item in result["ingested"])
    print(f"\nDone. {total_pages} pages ingested from {len(result['ingested'])} documents.")


def cmd_store(args):
    from stacks.prepare import store_page
    conn = get_connection()
    # Read JSON from stdin or file
    if args.file:
        with open(args.file) as f:
            data = json.load(f)
    else:
        data = json.load(sys.stdin)
    page_id = store_page(
        conn,
        doc_id=args.doc_id,
        page_num=args.page_num,
        content=data["content"],
        summary=data.get("summary"),
        content_type=data.get("content_type"),
        sheet_name=data.get("sheet_name"),
    )
    conn.close()
    print(f"Stored page {args.page_num} (page_id={page_id})")


def cmd_search(args):
    from stacks.search import search, format_results, format_results_html, generate_highlighted_pdfs
    conn = get_connection()
    results = search(conn, args.query, limit=args.limit)
    conn.close()

    # Always print text results
    print(format_results(results, query=args.query))

    if not results:
        return

    # Generate highlighted PDFs before HTML
    highlighted_pdfs = generate_highlighted_pdfs(results, args.query)

    # Always generate HTML
    import re
    from stacks.config import get_stacks_root
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', args.query)[:80].strip()
    out = get_stacks_root() / ".stacks" / f"search_{safe_name}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(format_results_html(results, query=args.query, highlighted_pdfs=highlighted_pdfs), encoding="utf-8")

    has_images = any(r.image_path for r in results)
    if has_images and not args.no_browser:
        import webbrowser
        webbrowser.open(str(out))
    else:
        print(f"HTML: {out}")


def cmd_list(args):
    from stacks.manage import cmd_list as do_list
    conn = get_connection()
    print(do_list(conn))
    conn.close()


def cmd_remove(args):
    from stacks.manage import cmd_remove as do_remove
    conn = get_connection()
    print(do_remove(conn, args.file_id))
    conn.close()


def cmd_quality(args):
    conn = get_connection()
    threshold = args.threshold
    rows = conn.execute(
        """SELECT p.id, p.doc_id, d.filename, p.page_num, p.quality_score,
                  substr(p.content, 1, 80)
           FROM pages p
           JOIN documents d ON d.id = p.doc_id
           WHERE p.quality_score IS NOT NULL AND p.quality_score < ?
           ORDER BY p.quality_score ASC""",
        (threshold,),
    ).fetchall()
    conn.close()

    if not rows:
        print(f"No pages with quality < {threshold}")
        return

    print(f"Pages with quality < {threshold}:")
    print(f"{'ID':>5}  {'Doc':>4}  {'Page':>4}  {'Score':>5}  Filename / Preview")
    print("-" * 80)
    for r in rows:
        score = r[4] if r[4] is not None else 0
        preview = r[5].replace("\n", " ")[:60]
        print(f"{r[0]:>5}  {r[1]:>4}  {r[2]:>4}  {score:>5.3f}  {r[2]}")
        print(f"{'':>23} {preview}")


def cmd_serve(args):
    from stacks.server import start_server
    start_server(port=args.port)


def cmd_info(args):
    from stacks.manage import cmd_info as do_info
    conn = get_connection()
    print(do_info(conn, args.file_id))
    conn.close()


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stacks", description="Document ingestion and semantic search")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize the database")
    p_init.add_argument("--reset", action="store_true", help="Delete existing database and start fresh")

    p_prepare = sub.add_parser("prepare", help="Discover and prepare files for ingestion")
    p_prepare.add_argument("path", help="File or directory path (relative to STACKS_ROOT)")

    p_ingest = sub.add_parser("ingest", help="Prepare and ingest all files (bulk)")
    p_ingest.add_argument("path", help="File or directory path")
    p_ingest.add_argument("--no-images", action="store_true", help="Skip page image generation")

    p_store = sub.add_parser("store", help="Store a page with content and embedding")
    p_store.add_argument("doc_id", type=int, help="Document ID")
    p_store.add_argument("page_num", type=int, help="Page number")
    p_store.add_argument("--file", help="JSON file with content and summary (default: stdin)")

    p_search = sub.add_parser("search", help="Search documents by natural language query")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=5, help="Max results (default: 5)")
    p_search.add_argument("--no-browser", action="store_true", help="Don't auto-open browser for HTML report")

    sub.add_parser("list", help="List ingested documents")

    p_remove = sub.add_parser("remove", help="Remove a document and all its pages")
    p_remove.add_argument("file_id", type=int, help="Document ID to remove")

    p_serve = sub.add_parser("serve", help="Start embedding server for fast repeated queries")
    p_serve.add_argument("--port", type=int, default=7823, help="Port (default: 7823)")

    p_quality = sub.add_parser("quality", help="List low-quality pages")
    p_quality.add_argument("--threshold", type=float, default=0.5, help="Quality threshold (default: 0.5)")

    p_info = sub.add_parser("info", help="Show document details")
    p_info.add_argument("file_id", type=int, help="Document ID")

    return parser


def main():
    import sys
    import io

    parser = create_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # Suppress noisy torch/safetensors stderr during model loading
    original_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        handlers = {
            "init": cmd_init,
            "prepare": cmd_prepare,
            "ingest": cmd_ingest,
            "store": cmd_store,
            "search": cmd_search,
            "list": cmd_list,
            "remove": cmd_remove,
            "serve": cmd_serve,
            "quality": cmd_quality,
            "info": cmd_info,
        }
        handlers[args.command](args)
    except Exception as e:
        sys.stderr = original_stderr
        raise
    finally:
        sys.stderr = original_stderr
