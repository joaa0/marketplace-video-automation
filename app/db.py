import os
import sqlite3
from pathlib import Path


def connect():
    path = Path(os.getenv('DB_PATH', 'data/app.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


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
        ''')
