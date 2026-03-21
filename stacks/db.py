"""Database operations for stacks using SQLite + sqlite-vec."""
import sqlite3
import struct
from pathlib import Path

import sqlite_vec

from stacks.config import get_db_path
from stacks.tokenizer import tokenize

EMBEDDING_DIM = 384


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a SQLite connection with sqlite-vec loaded and foreign keys enabled."""
    if db_path is None:
        db_path = get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes."""
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            filepath TEXT NOT NULL,
            format TEXT NOT NULL,
            file_hash TEXT NOT NULL UNIQUE,
            page_count INTEGER,
            file_size_bytes INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            page_num INTEGER NOT NULL,
            sheet_name TEXT,
            content TEXT NOT NULL,
            summary TEXT,
            content_type TEXT,
            token_count INTEGER,
            quality_score REAL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(doc_id, page_num)
        );

        CREATE INDEX IF NOT EXISTS idx_pages_doc_id ON pages(doc_id);
        CREATE INDEX IF NOT EXISTS idx_documents_file_hash ON documents(file_hash);
        CREATE INDEX IF NOT EXISTS idx_documents_format ON documents(format);

        CREATE VIRTUAL TABLE IF NOT EXISTS pages_vec USING vec0(
            page_id INTEGER PRIMARY KEY,
            embedding FLOAT[{EMBEDDING_DIM}]
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
            content,
            content='pages',
            content_rowid='id',
            tokenize='unicode61'
        );
    """)
    # Migrate: add image_path column if missing
    cols = [row[1] for row in conn.execute("PRAGMA table_info(pages)").fetchall()]
    if "image_path" not in cols:
        conn.execute("ALTER TABLE pages ADD COLUMN image_path TEXT")
        conn.commit()

    conn.commit()


def insert_document(
    conn: sqlite3.Connection,
    filename: str,
    filepath: str,
    format: str,
    file_hash: str,
    page_count: int | None,
    file_size_bytes: int | None,
) -> int:
    """Insert a document record and return its id."""
    cur = conn.execute(
        """INSERT INTO documents (filename, filepath, format, file_hash, page_count, file_size_bytes)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (filename, filepath, format, file_hash, page_count, file_size_bytes),
    )
    conn.commit()
    return cur.lastrowid


def find_document_by_hash(conn: sqlite3.Connection, file_hash: str) -> dict | None:
    """Find a document by its file hash. Returns None if not found."""
    row = conn.execute(
        "SELECT * FROM documents WHERE file_hash = ?", (file_hash,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def insert_page(
    conn: sqlite3.Connection,
    doc_id: int,
    page_num: int,
    content: str,
    summary: str | None,
    content_type: str | None,
    token_count: int | None,
    sheet_name: str | None = None,
    quality_score: float | None = None,
    image_path: str | None = None,
) -> int:
    """Insert a page record and return its id."""
    cur = conn.execute(
        """INSERT INTO pages (doc_id, page_num, sheet_name, content, summary, content_type, token_count, quality_score, image_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (doc_id, page_num, sheet_name, content, summary, content_type, token_count, quality_score, image_path),
    )
    page_id = cur.lastrowid
    # Sync FTS index (形態素解析済みテキストを投入)
    conn.execute(
        "INSERT INTO pages_fts (rowid, content) VALUES (?, ?)",
        (page_id, tokenize(content)),
    )
    conn.commit()
    return page_id


def _serialize_embedding(embedding: list[float]) -> bytes:
    """Serialize a float list to bytes for sqlite-vec."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def insert_embedding(conn: sqlite3.Connection, page_id: int, embedding: list[float]) -> None:
    """Insert an embedding vector for a page."""
    conn.execute(
        "INSERT INTO pages_vec (page_id, embedding) VALUES (?, ?)",
        (page_id, _serialize_embedding(embedding)),
    )
    conn.commit()


def delete_document(conn: sqlite3.Connection, doc_id: int) -> None:
    """Delete a document and all related pages and embeddings."""
    # Get page ids for pages_vec cleanup
    page_ids = [
        row[0]
        for row in conn.execute(
            "SELECT id FROM pages WHERE doc_id = ?", (doc_id,)
        ).fetchall()
    ]
    # Delete from virtual tables (no CASCADE)
    for pid in page_ids:
        conn.execute("DELETE FROM pages_vec WHERE page_id = ?", (pid,))
        conn.execute("DELETE FROM pages_fts WHERE rowid = ?", (pid,))
    # Delete document (CASCADE deletes pages)
    conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()


def list_documents(conn: sqlite3.Connection) -> list[dict]:
    """Return all documents as a list of dicts."""
    rows = conn.execute(
        "SELECT * FROM documents ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_document_info(conn: sqlite3.Connection, doc_id: int) -> dict | None:
    """Return document details with its pages. Returns None if not found."""
    doc = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if doc is None:
        return None
    pages = conn.execute(
        "SELECT * FROM pages WHERE doc_id = ? ORDER BY page_num", (doc_id,)
    ).fetchall()
    return {"document": dict(doc), "pages": [dict(p) for p in pages]}


def search_fts(
    conn: sqlite3.Connection, query: str, limit: int = 20
) -> list[dict]:
    """Full-text search using FTS5. Returns pages with BM25 rank."""
    tokenized_query = tokenize(query)
    if not tokenized_query.strip():
        return []
    rows = conn.execute(
        """
        SELECT
            p.id AS page_id,
            rank AS fts_rank,
            p.doc_id,
            p.page_num,
            p.content,
            p.summary,
            p.image_path,
            d.filename,
            d.filepath
        FROM pages_fts
        JOIN pages p ON p.id = pages_fts.rowid
        JOIN documents d ON d.id = p.doc_id
        WHERE pages_fts MATCH ?
        ORDER BY rank
        LIMIT ?
        """,
        (tokenized_query, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def search_similar(
    conn: sqlite3.Connection, embedding: list[float], limit: int = 5
) -> list[dict]:
    """Search for similar pages using cosine distance via sqlite-vec."""
    rows = conn.execute(
        """
        SELECT
            pv.page_id,
            pv.distance,
            p.doc_id,
            p.page_num,
            p.content,
            p.summary,
            p.image_path,
            d.filename,
            d.filepath
        FROM pages_vec pv
        JOIN pages p ON p.id = pv.page_id
        JOIN documents d ON d.id = p.doc_id
        WHERE pv.embedding MATCH ?
            AND k = ?
        ORDER BY pv.distance
        """,
        (_serialize_embedding(embedding), limit),
    ).fetchall()
    return [dict(r) for r in rows]


def rebuild_fts(conn: sqlite3.Connection) -> int:
    """既存ページのFTSインデックスを形態素解析で再構築する。戻り値は処理件数。"""
    conn.execute("DELETE FROM pages_fts")
    rows = conn.execute("SELECT id, content FROM pages ORDER BY id").fetchall()
    for row in rows:
        conn.execute(
            "INSERT INTO pages_fts (rowid, content) VALUES (?, ?)",
            (row[0], tokenize(row[1])),
        )
    conn.commit()
    return len(rows)
