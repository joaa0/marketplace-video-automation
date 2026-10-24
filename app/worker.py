"""Durable local rendering queue, leased ownership and bounded retries."""
from app import config
import json
import os
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from app.db import connect, init_db
from app.media import digest, intact, render

MAX_ATTEMPTS = 3
LEASE_SECONDS = 600


def claim():
    current = time.time()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute("UPDATE tasks SET status='FAILED',error='Worker interrompido; limite de tentativas atingido' "
                   "WHERE status='RUNNING' AND lease_until<? AND attempts>=?", (current, MAX_ATTEMPTS))
        row = db.execute("SELECT * FROM tasks WHERE attempts<? AND "
                         "((status='QUEUED' AND available_at<=?) OR (status='RUNNING' AND lease_until<?)) "
                         'ORDER BY created_at,rowid LIMIT 1', (MAX_ATTEMPTS, current, current)).fetchone()
        if not row:
            return None
        token = str(uuid4())
        db.execute("UPDATE tasks SET status='RUNNING',attempts=attempts+1,lease_until=?,lease_token=? WHERE id=?",
                   (current + LEASE_SECONDS, token, row['id']))
        return {**dict(row), 'attempts': row['attempts'] + 1, 'lease_token': token}


def lineage(db, job_id, asset_ids):
    """Include originals behind AI/Flow assets so export rechecks their hashes too."""
    found = {}
    pending = list(asset_ids)
    while pending:
        asset_id = pending.pop()
        if asset_id in found:
            continue
        row = db.execute('SELECT * FROM assets WHERE id=? AND job_id=?', (asset_id, job_id)).fetchone()
        if not row:
            raise ValueError('Mídia de outra tarefa ou indisponível')
        intact(row)
        found[asset_id] = dict(row)
        pending.extend(json.loads(row['metadata']).get('parents', []))
        pending.extend(r['asset_id'] for r in db.execute('SELECT asset_id FROM flow_requests WHERE clip_id=?', (asset_id,)))
    return found


def run_once():
    task = claim()
    if task is None:
        return False
    output = None
    try:
        payload = json.loads(task['payload'])
        ids = [payload['visual_asset_id']] + ([payload['audio_asset_id']] if payload.get('audio_asset_id') else [])
        with connect() as db:
            assets = lineage(db, task['job_id'], ids)
        source = intact(assets[payload['visual_asset_id']])
        audio = intact(assets[payload['audio_asset_id']]) if payload.get('audio_asset_id') else None
        root = Path(os.getenv('RENDER_ROOT', 'data/renders')).resolve()
        output = root / (task['id'] + '-' + task['lease_token'] + '.mp4')
        render(source, output, payload['duration'], audio)
        sha = digest(output)
        from app.pipeline_api import audit, stamp
        render_id = str(uuid4())
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            owned = db.execute("SELECT id FROM tasks WHERE id=? AND status='RUNNING' AND lease_token=? AND lease_until>?",
                               (task['id'], task['lease_token'], time.time())).fetchone()
            if not owned:
                raise ValueError('Lease perdida; resultado descartado')
            # Recheck sources after processing, before committing the deliverable.
            assets = lineage(db, task['job_id'], ids)
            db.execute('UPDATE approvals SET revoked_at=? WHERE render_id IN (SELECT id FROM renders WHERE job_id=?) AND revoked_at IS NULL', (stamp(), task['job_id']))
            db.execute('INSERT INTO renders VALUES (?,?,?,?,?,?,?,?)',
                       (render_id, task['job_id'], sha, str(output), payload['caption'], payload['destination'], payload['account_id'], stamp()))
            db.executemany('INSERT INTO render_assets VALUES (?,?)', [(render_id, asset_id) for asset_id in assets])
            db.execute("UPDATE jobs SET status='AWAITING_APPROVAL' WHERE id=?", (task['job_id'],))
            db.execute("UPDATE tasks SET status='DONE',result=?,lease_until=NULL,error=NULL WHERE id=?",
                       (json.dumps({'render_id': render_id, 'sha256': sha}), task['id']))
            audit(db, task['job_id'], 'RENDER_REGISTERED', {'render_id': render_id, 'task_id': task['id'], 'sha256': sha}, 'worker')
    except Exception as exc:
        if output:
            output.unlink(missing_ok=True)
        # Never persist provider credentials, raw commands or arbitrary error payloads.
        error = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
        with connect() as db:
            db.execute("UPDATE tasks SET status=?,error=?,available_at=?,lease_until=NULL WHERE id=? AND lease_token=? AND status='RUNNING'",
                       ('FAILED' if task['attempts'] >= MAX_ATTEMPTS else 'QUEUED', error[:500],
                        time.time() + 5 * task['attempts'], task['id'], task['lease_token']))
    return True


def run():
    init_db()
    while True:
        try:
            if not run_once():
                time.sleep(1)
        except KeyboardInterrupt:
            break
        except sqlite3.Error:
            time.sleep(2)


if __name__ == '__main__':
    run()
