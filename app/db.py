import os
from contextlib import contextmanager
import sqlite3
from pathlib import Path


@contextmanager
def connect():
    path = Path(os.getenv('DB_PATH', 'data/app.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        with db:
            yield db
    finally:
        db.close()


def init_db():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS products (
          id TEXT PRIMARY KEY, sku TEXT NOT NULL, title TEXT NOT NULL, product_url TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, product_id TEXT NOT NULL REFERENCES products(id),
          status TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS renders (
          id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
          sha256 TEXT NOT NULL, uri TEXT NOT NULL, caption TEXT NOT NULL,
          destination TEXT NOT NULL, account_id TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS approvals (
          id TEXT PRIMARY KEY, render_id TEXT NOT NULL REFERENCES renders(id),
          reviewer TEXT NOT NULL, approved_at TEXT NOT NULL,
          sha256 TEXT NOT NULL, destination TEXT NOT NULL,
          account_id TEXT NOT NULL, caption TEXT NOT NULL, revoked_at TEXT
        );
        CREATE TABLE IF NOT EXISTS audit_events (
          id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
          action TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL,
          detail TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS assets (
          id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), kind TEXT NOT NULL,
          uri TEXT NOT NULL, sha256 TEXT NOT NULL, source TEXT NOT NULL,
          rights_evidence TEXT NOT NULL, metadata TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS render_assets (
          render_id TEXT NOT NULL REFERENCES renders(id), asset_id TEXT NOT NULL REFERENCES assets(id),
          PRIMARY KEY(render_id, asset_id)
        );
        CREATE TABLE IF NOT EXISTS flow_requests (
          id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
          asset_id TEXT NOT NULL REFERENCES assets(id), prompt TEXT NOT NULL,
          status TEXT NOT NULL, clip_id TEXT REFERENCES assets(id), created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
          id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), payload TEXT NOT NULL,
          status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, available_at REAL NOT NULL,
          lease_until REAL, lease_token TEXT, result TEXT, error TEXT, created_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_render_task ON tasks(job_id)
          WHERE status IN ('QUEUED','RUNNING');
        CREATE TABLE IF NOT EXISTS bot_state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_approval ON approvals(render_id)
          WHERE revoked_at IS NULL;
        ''')
