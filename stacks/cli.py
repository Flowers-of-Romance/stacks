"""CLI entry point for stacks."""
import argparse
import json
import sys

from stacks.db import get_connection, init_db
from stacks.config import get_db_path


def cmd_init(args):
    conn = get_connection()
    init_db(conn)
    conn.close()
    print(f"Initialized stacks database at {get_db_path()}")


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

    def progress(page, total):
        print(f"\r  {page}/{total}", end="", flush=True)

    result = ingest_all(conn, args.path, on_progress=progress)
    conn.close()

    for item in result["ingested"]:
        print(f"\n  {item['original']}: {item['pages_ingested']}/{item['total_pages']} pages")
    if result["skipped"]:
        print(f"\nSkipped: {len(result['skipped'])} files")
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
    from stacks.search import search, format_results
    conn = get_connection()
    results = search(conn, args.query, limit=args.limit)
    conn.close()
    print(format_results(results))


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


def cmd_info(args):
    from stacks.manage import cmd_info as do_info
    conn = get_connection()
    print(do_info(conn, args.file_id))
    conn.close()


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stacks", description="Document ingestion and semantic search")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize the database")

    p_prepare = sub.add_parser("prepare", help="Discover and prepare files for ingestion")
    p_prepare.add_argument("path", help="File or directory path (relative to STACKS_ROOT)")

    p_ingest = sub.add_parser("ingest", help="Prepare and ingest all files (bulk)")
    p_ingest.add_argument("path", help="File or directory path")

    p_store = sub.add_parser("store", help="Store a page with content and embedding")
    p_store.add_argument("doc_id", type=int, help="Document ID")
    p_store.add_argument("page_num", type=int, help="Page number")
    p_store.add_argument("--file", help="JSON file with content and summary (default: stdin)")

    p_search = sub.add_parser("search", help="Search documents by natural language query")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=5, help="Max results (default: 5)")

    sub.add_parser("list", help="List ingested documents")

    p_remove = sub.add_parser("remove", help="Remove a document and all its pages")
    p_remove.add_argument("file_id", type=int, help="Document ID to remove")

    p_quality = sub.add_parser("quality", help="List low-quality pages")
    p_quality.add_argument("--threshold", type=float, default=0.5, help="Quality threshold (default: 0.5)")

    p_info = sub.add_parser("info", help="Show document details")
    p_info.add_argument("file_id", type=int, help="Document ID")

    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    handlers = {
        "init": cmd_init,
        "prepare": cmd_prepare,
        "ingest": cmd_ingest,
        "store": cmd_store,
        "search": cmd_search,
        "list": cmd_list,
        "remove": cmd_remove,
        "quality": cmd_quality,
        "info": cmd_info,
    }
    handlers[args.command](args)
