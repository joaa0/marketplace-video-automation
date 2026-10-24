"""Operator-only media pipeline. Approval and export remain separate actions."""
import io
import json
import os
import sqlite3
import time
import zipfile
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from app.db import connect
from app.media import MAX_BYTES, digest, intact, safe_path, store, probe
from app.ai_editor import edit_clothing, EditorUnavailable

router = APIRouter()


def stamp():
    from app.main import now
    return now()


def audit(db, job_id, action, detail, actor='operator'):
    db.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?)',
               (str(uuid4()), job_id, action, actor, stamp(), json.dumps(detail, ensure_ascii=False)))


def job_exists(job_id):
    with connect() as db:
        if not db.execute('SELECT id FROM jobs WHERE id=?', (job_id,)).fetchone():
            raise HTTPException(404, 'Tarefa não encontrada')


def asset_for(job_id, asset_id, kinds):
    with connect() as db:
        row = db.execute('SELECT * FROM assets WHERE id=? AND job_id=?', (asset_id, job_id)).fetchone()
    if not row or row['kind'] not in kinds:
        raise HTTPException(422, 'Mídia de tipo incorreto ou de outra tarefa')
    try:
        intact(row)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return dict(row)


def save_asset(job_id, kind, data, source, rights_evidence, metadata=None):
    try:
        path, sha, info = store(data, kind)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    info.update(metadata or {})
    record = dict(id=str(uuid4()), job_id=job_id, kind=kind, uri=str(path), sha256=sha,
                  source=source, rights_evidence=rights_evidence, metadata=json.dumps(info), created_at=stamp())
    try:
        with connect() as db:
            db.execute('INSERT INTO assets VALUES (:id,:job_id,:kind,:uri,:sha256,:source,:rights_evidence,:metadata,:created_at)', record)
            audit(db, job_id, 'ASSET_REGISTERED', {'id': record['id'], 'sha256': sha, 'source': source})
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return record


@router.get('/jobs')
def list_jobs():
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100')]


@router.get('/jobs/{job_id}/audit')
def job_audit(job_id: str):
    job_exists(job_id)
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM audit_events WHERE job_id=? ORDER BY rowid', (job_id,))]


@router.post('/jobs/{job_id}/assets', status_code=201)
async def upload_asset(job_id: str, kind: Literal['model', 'garment', 'edited', 'clip', 'audio'] = Form(...),
                       source: str = Form(..., min_length=1, max_length=2000),
                       rights_evidence: str = Form(..., min_length=3, max_length=4000), file: UploadFile = File(...)):
    job_exists(job_id)
    if not rights_evidence.strip() or not source.strip():
        raise HTTPException(422, 'Informe origem e evidência de direitos')
    try:
        data = await file.read(MAX_BYTES + 1)
    finally:
        await file.close()
    return save_asset(job_id, kind, data, source, rights_evidence)


@router.get('/jobs/{job_id}/assets')
def list_assets(job_id: str):
    job_exists(job_id)
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM assets WHERE job_id=? ORDER BY rowid', (job_id,))]


@router.get('/assets/{asset_id}/file')
def asset_file(asset_id: str):
    with connect() as db:
        row = db.execute('SELECT * FROM assets WHERE id=?', (asset_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Mídia não encontrada')
    try:
        return FileResponse(intact(row))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


class EditInput(BaseModel):
    model_asset_id: str
    garment_asset_id: str
    instructions: str = Field(default='', max_length=2000)


@router.post('/jobs/{job_id}/edit-clothing', status_code=201)
def clothing_edit(job_id: str, payload: EditInput):
    model = asset_for(job_id, payload.model_asset_id, ('model',))
    garment = asset_for(job_id, payload.garment_asset_id, ('garment',))
    with connect() as db:
        audit(db, job_id, 'AI_EDIT_REQUESTED', payload.model_dump())
    try:
        data = edit_clothing(intact(model).read_bytes(), intact(garment).read_bytes(), payload.instructions)
    except EditorUnavailable as exc:
        with connect() as db:
            audit(db, job_id, 'AI_EDIT_FAILED_OR_UNKNOWN', {'reason': str(exc)})
        raise HTTPException(503, str(exc)) from exc
    return save_asset(job_id, 'edited', data, 'Gemini: ' + os.getenv('GEMINI_IMAGE_MODEL', ''),
                      model['rights_evidence'] + '\n' + garment['rights_evidence'],
                      {'parents': [model['id'], garment['id']], 'sku_review_required': True, 'instructions': payload.instructions})


class FlowInput(BaseModel):
    asset_id: str
    prompt: str = Field(min_length=10, max_length=4000)


@router.post('/jobs/{job_id}/flow-requests', status_code=201)
def request_flow(job_id: str, payload: FlowInput):
    asset_for(job_id, payload.asset_id, ('edited', 'model', 'garment'))
    request_id = str(uuid4())
    with connect() as db:
        db.execute('INSERT INTO flow_requests VALUES (?,?,?,?,?,?,?)',
                   (request_id, job_id, payload.asset_id, payload.prompt, 'WAITING_OPERATOR', None, stamp()))
        audit(db, job_id, 'FLOW_HANDOFF_CREATED', {'request_id': request_id})
    return {'id': request_id, 'status': 'WAITING_OPERATOR', 'mode': 'assisted',
            'package_url': f'/flow-requests/{request_id}/package', 'live_integration_verified': False}


@router.get('/flow-requests/{request_id}/package')
def flow_package(request_id: str):
    with connect() as db:
        row = db.execute('SELECT * FROM flow_requests WHERE id=?', (request_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Solicitação Flow não encontrada')
    asset = asset_for(row['job_id'], row['asset_id'], ('edited', 'model', 'garment'))
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(intact(asset), 'reference.png')
        archive.writestr('prompt.txt', row['prompt'])
        archive.writestr('manifest.json', json.dumps(dict(row), ensure_ascii=False, indent=2))
        archive.writestr('INSTRUCOES.txt', 'Abra https://labs.google/fx/tools/flow na sua conta.\n'
                         'Crie um vídeo vertical usando reference.png como quadro ou ingrediente e prompt.txt.\n'
                         'Revise o SKU, baixe o clipe e envie como asset clip nesta tarefa.\n'
                         'Registre o ID do clipe em POST /flow-requests/ID/complete.\n'
                         'Nenhuma chamada ao Flow foi realizada pelo sistema.\n')
    return zip_response(output.getvalue(), f'flow-{request_id}.zip')


class FlowComplete(BaseModel):
    clip_asset_id: str


@router.post('/flow-requests/{request_id}/complete')
def flow_complete(request_id: str, payload: FlowComplete):
    with connect() as db:
        row = db.execute('SELECT * FROM flow_requests WHERE id=?', (request_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Solicitação Flow não encontrada')
    clip = asset_for(row['job_id'], payload.clip_asset_id, ('clip',))
    with connect() as db:
        changed = db.execute("UPDATE flow_requests SET status='IMPORTED',clip_id=? WHERE id=? AND status='WAITING_OPERATOR'",
                             (clip['id'], request_id)).rowcount
        if not changed:
            raise HTTPException(409, 'Solicitação já concluída')
        audit(db, row['job_id'], 'FLOW_CLIP_IMPORTED', {'request_id': request_id, 'clip_asset_id': clip['id']})
    return {'status': 'IMPORTED', 'external_origin': 'operator_declared', 'google_session_tested': False}


class RenderTaskInput(BaseModel):
    visual_asset_id: str
    audio_asset_id: str | None = None
    duration: int = Field(default=8, ge=2, le=60)
    caption: str = Field(min_length=1, max_length=4000)
    destination: str = Field(min_length=1, max_length=100)
    account_id: str = Field(min_length=1, max_length=200)


@router.post('/jobs/{job_id}/render-tasks', status_code=202)
def enqueue_render(job_id: str, payload: RenderTaskInput):
    asset_for(job_id, payload.visual_asset_id, ('edited', 'model', 'garment', 'clip'))
    if payload.audio_asset_id:
        asset_for(job_id, payload.audio_asset_id, ('audio',))
    task_id = str(uuid4())
    try:
        with connect() as db:
            db.execute('INSERT INTO tasks(id,job_id,payload,status,available_at,created_at) VALUES (?,?,?,?,?,?)',
                       (task_id, job_id, payload.model_dump_json(), 'QUEUED', time.time(), stamp()))
            audit(db, job_id, 'RENDER_QUEUED', {'task_id': task_id})
    except sqlite3.IntegrityError as exc:
        raise HTTPException(409, 'Já existe renderização pendente nesta tarefa') from exc
    return {'id': task_id, 'status': 'QUEUED'}


@router.get('/tasks/{task_id}')
def task_status(task_id: str):
    with connect() as db:
        row = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Processamento não encontrado')
    return dict(row)


def zip_response(data, filename):
    return StreamingResponse(io.BytesIO(data), media_type='application/zip',
                             headers={'Content-Disposition': f'attachment; filename="{filename}"'})


@router.get('/renders/{render_id}/file')
def render_file(render_id: str):
    with connect() as db:
        row = db.execute('SELECT * FROM renders WHERE id=?', (render_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Vídeo não encontrado')
    try:
        path = safe_path(row['uri'], Path(os.getenv('RENDER_ROOT', 'data/renders')))
        if digest(path) != row['sha256']:
            raise ValueError('Vídeo alterado')
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return FileResponse(path, media_type='video/mp4')


@router.post('/renders/{render_id}/revoke')
def revoke(render_id: str):
    with connect() as db:
        row = db.execute('SELECT * FROM renders WHERE id=?', (render_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Vídeo não encontrado')
        db.execute('UPDATE approvals SET revoked_at=? WHERE render_id=? AND revoked_at IS NULL', (stamp(), render_id))
        latest = db.execute('SELECT id FROM renders WHERE job_id=? ORDER BY rowid DESC LIMIT 1', (row['job_id'],)).fetchone()
        if latest['id'] == render_id:
            db.execute("UPDATE jobs SET status='AWAITING_APPROVAL' WHERE id=?", (row['job_id'],))
        audit(db, row['job_id'], 'APPROVAL_REVOKED', {'render_id': render_id})
    return {'status': 'REVOKED'}


@router.get('/renders/{render_id}/export')
def export_render(render_id: str):
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT * FROM renders WHERE id=?', (render_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Vídeo não encontrado')
        latest = db.execute('SELECT id FROM renders WHERE job_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (row['job_id'],)).fetchone()
        approval = db.execute('SELECT * FROM approvals WHERE render_id=? AND revoked_at IS NULL', (render_id,)).fetchone()
        if not approval or latest['id'] != render_id:
            raise HTTPException(409, 'A versão atual precisa de aprovação humana ativa')
        for key in ('sha256', 'caption', 'destination', 'account_id'):
            if row[key] != approval[key]:
                raise HTTPException(409, 'Aprovação não corresponde ao conteúdo e destino')
        assets = db.execute('SELECT a.* FROM assets a JOIN render_assets ra ON a.id=ra.asset_id WHERE ra.render_id=?', (render_id,)).fetchall()
        if not assets:
            raise HTTPException(409, 'Registre mídias com origem e direitos pelo pipeline antes de exportar')
        try:
            for asset in assets:
                intact(asset)
            path = safe_path(row['uri'], Path(os.getenv('RENDER_ROOT', 'data/renders')))
            probe(path, final=True)
            # Package the same bytes we hash; never reopen a possibly modified file.
            data = path.read_bytes()
            import hashlib
            if hashlib.sha256(data).hexdigest() != approval['sha256']:
                raise ValueError('Arquivo alterado após aprovação')
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('video.mp4', data)
            archive.writestr('legenda.txt', row['caption'])
            archive.writestr('aprovacao.json', json.dumps(dict(approval), ensure_ascii=False, indent=2))
            archive.writestr('origens.json', json.dumps([dict(a) for a in assets], ensure_ascii=False, indent=2))
            archive.writestr('LEIA-ME.txt', f'Publicação manual: {row["destination"]}, conta {row["account_id"]}.\nConfira preço e estoque no momento de publicar.\n')
        audit(db, row['job_id'], 'EXPORT_CREATED', {'render_id': render_id, 'approval_id': approval['id']})
    return zip_response(output.getvalue(), f'publicacao-{render_id}.zip')


@router.get('/jobs/{job_id}/renders')
def list_renders(job_id: str):
    job_exists(job_id)
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT id,sha256,caption,destination,account_id,created_at FROM renders WHERE job_id=? ORDER BY rowid DESC', (job_id,))]


@router.get('/jobs/{job_id}/tasks')
def list_tasks(job_id: str):
    job_exists(job_id)
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM tasks WHERE job_id=? ORDER BY rowid DESC LIMIT 100', (job_id,))]


@router.get('/jobs/{job_id}/flow-requests')
def list_flow_requests(job_id: str):
    job_exists(job_id)
    with connect() as db:
        return [dict(r) for r in db.execute('SELECT * FROM flow_requests WHERE job_id=? ORDER BY rowid DESC', (job_id,))]


@router.get('/renders/{render_id}')
def render_detail(render_id: str):
    with connect() as db:
        row = db.execute('SELECT id,job_id,sha256,caption,destination,account_id,created_at FROM renders WHERE id=?', (render_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Vídeo não encontrado')
        approval = db.execute('SELECT id,reviewer,approved_at FROM approvals WHERE render_id=? AND revoked_at IS NULL', (render_id,)).fetchone()
    return {**dict(row), 'approval': dict(approval) if approval else None, 'publication_enabled': False}


class ModelSelectionInput(BaseModel):
    garment_asset_id: str


@router.post('/jobs/{job_id}/select-model')
def auto_select_model(job_id: str, payload: ModelSelectionInput):
    from app.model_selector import select_model, SelectionUnavailable
    from app.pexels import PexelsError
    garment = asset_for(job_id, payload.garment_asset_id, ('garment',))
    with connect() as db:
        audit(db, job_id, 'MODEL_SELECTION_REQUESTED', payload.model_dump())
    try:
        report, chosen = select_model(intact(garment).read_bytes())
    except (SelectionUnavailable, PexelsError) as exc:
        with connect() as db:
            audit(db, job_id, 'MODEL_SELECTION_UNAVAILABLE', {'reason': str(exc)})
        raise HTTPException(503, str(exc)) from exc
    if chosen:
        score, photo, image, assessment = chosen
        asset = save_asset(job_id, 'model', image, photo['url'],
                           'PENDENTE: referência Pexels; autorização publicitária e edição não verificadas',
                           {'pexels': photo, 'selection': assessment, 'selection_score': score,
                            'matched_garment_id': garment['id'], 'rights_review_required': True})
        report['selected_asset_id'] = asset['id']
        report['selected_photo'] = photo
    with connect() as db:
        audit(db, job_id, 'MODEL_SELECTION_COMPLETED', report)
    return report
