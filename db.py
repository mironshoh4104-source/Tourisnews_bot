"""SQLite helpers for dedup (posted) and pending drafts."""
import hashlib
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS posted (
    item_hash TEXT PRIMARY KEY,
    url TEXT,
    title TEXT,
    posted_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pending (
    draft_id TEXT PRIMARY KEY,
    item_hash TEXT,
    draft_text TEXT,
    url TEXT,
    title TEXT,
    source TEXT,
    admin_message_id INTEGER,
    created_at TIMESTAMP
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def normalize_url(url: str) -> str:
    """Strip query params/fragments and trailing slash for stable hashing."""
    if not url:
        return ""
    base = url.split("?")[0].split("#")[0]
    return base.rstrip("/").lower()


def compute_item_hash(url: str, title: str) -> str:
    """sha256 of normalized URL; falls back to title if no URL."""
    basis = normalize_url(url) or (title or "").strip().lower()
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def is_posted(item_hash: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM posted WHERE item_hash = ?", (item_hash,)
        ).fetchone()
        return row is not None


def mark_posted(item_hash: str, url: str, title: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO posted (item_hash, url, title, posted_at) VALUES (?, ?, ?, ?)",
            (item_hash, url, title, datetime.now(timezone.utc).isoformat()),
        )


def save_pending_draft(item_hash: str, draft_text: str, url: str, title: str, source: str) -> str:
    """Create a new pending draft row, return its draft_id."""
    draft_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO pending
               (draft_id, item_hash, draft_text, url, title, source, admin_message_id, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (draft_id, item_hash, draft_text, url, title, source, None,
             datetime.now(timezone.utc).isoformat()),
        )
    return draft_id


def get_pending_draft(draft_id: str):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT draft_id, item_hash, draft_text, url, title, source, admin_message_id, created_at "
            "FROM pending WHERE draft_id = ?",
            (draft_id,),
        ).fetchone()
        if not row:
            return None
        keys = ["draft_id", "item_hash", "draft_text", "url", "title", "source",
                "admin_message_id", "created_at"]
        return dict(zip(keys, row))


def update_pending_text(draft_id: str, new_text: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE pending SET draft_text = ? WHERE draft_id = ?",
            (new_text, draft_id),
        )


def set_pending_message_id(draft_id: str, message_id: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE pending SET admin_message_id = ? WHERE draft_id = ?",
            (message_id, draft_id),
        )


def delete_pending(draft_id: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM pending WHERE draft_id = ?", (draft_id,))
