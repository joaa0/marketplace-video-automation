from app import config  # load local .env before reading configuration
import hashlib
from contextlib import asynccontextmanager
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field
from app.db import connect, init_db
from app.pexels import search_models, PexelsError

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title='Marketplace Video Automation', version='0.3.0', lifespan=lifespan)


def now():
    return datetime.now(timezone.utc).isoformat()


def require_operator(x_operator_key: str | None = Header(default=None)):
    import hmac
    key = os.getenv('OPERATOR_API_KEY', '')
    if not key or not x_operator_key or not hmac.compare_digest(key.encode(), x_operator_key.encode()):
        raise HTTPException(status_code=401, detail='Chave de operador inválida ou não configurada')


class ProductInput(BaseModel):
    sku: str = Field(min_length=1)
    title: str = Field(min_length=1)
    product_url: str = Field(min_length=1)


class JobInput(BaseModel):
    product_id: str


class RenderInput(BaseModel):
    job_id: str
    file_path: str
    caption: str
    destination: str
    account_id: str


class ApprovalInput(BaseModel):
    reviewer: str = Field(min_length=1, max_length=200)
    sku_verified: bool = False
    rights_verified: bool = False
    caption_verified: bool = False
    price_availability_verified: bool = False


@app.get('/health')
def health():
    return {'status': 'ok', 'phase': 'media-render-export', 'production_ready': False, 'publication_enabled': False}


@app.post('/products', status_code=201, dependencies=[Depends(require_operator)])
def create_product(payload: ProductInput):
    product_id = str(uuid4())
    with connect() as db:
        db.execute('INSERT INTO products VALUES (?, ?, ?, ?)', (product_id, payload.sku, payload.title, payload.product_url))
    return {'id': product_id, **payload.model_dump()}


@app.post('/jobs', status_code=201, dependencies=[Depends(require_operator)])
def create_job(payload: JobInput):
    with connect() as db:
        if not db.execute('SELECT id FROM products WHERE id=?', (payload.product_id,)).fetchone():
            raise HTTPException(404, 'Produto não encontrado')
        job_id = str(uuid4())
        created_at = now()
        db.execute('INSERT INTO jobs VALUES (?, ?, ?, ?)', (job_id, payload.product_id, 'NEW', created_at))
    return {'id': job_id, 'product_id': payload.product_id, 'status': 'NEW', 'created_at': created_at}


@app.get('/jobs/{job_id}', dependencies=[Depends(require_operator)])
def get_job(job_id: str):
    with connect() as db:
        row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'Tarefa não encontrada')
    return dict(row)


@app.post('/renders', status_code=201, dependencies=[Depends(require_operator)])
def register_render(payload: RenderInput):
    # Files must be produced in a configured local workspace, never an arbitrary path.
    root = Path(os.getenv('RENDER_ROOT', 'data/renders')).resolve()
    path = Path(payload.file_path).resolve()
    if not path.is_relative_to(root) or not path.is_file() or path.suffix.lower() != '.mp4':
        raise HTTPException(400, 'MP4 não encontrado no diretório autorizado')
    from app.media import digest, probe
    try:
        probe(path, final=True)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    sha = digest(path)
    render_id = str(uuid4())
    with connect() as db:
        job = db.execute('SELECT id FROM jobs WHERE id=?', (payload.job_id,)).fetchone()
        if not job:
            raise HTTPException(404, 'Tarefa não encontrada')
        db.execute('UPDATE approvals SET revoked_at=? WHERE render_id IN (SELECT id FROM renders WHERE job_id=?) AND revoked_at IS NULL', (now(), payload.job_id))
        db.execute('INSERT INTO renders VALUES (?,?,?,?,?,?,?,?)', (render_id, payload.job_id, sha, str(path), payload.caption, payload.destination, payload.account_id, now()))
        db.execute("UPDATE jobs SET status='AWAITING_APPROVAL' WHERE id=?", (payload.job_id,))
        db.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?)', (str(uuid4()), payload.job_id, 'RENDER_REGISTERED', 'operator', now(), render_id))
    return {'id': render_id, 'sha256': sha, 'status': 'AWAITING_APPROVAL'}


@app.post('/renders/{render_id}/approve', dependencies=[Depends(require_operator)])
def approve_render(render_id: str, payload: ApprovalInput):
    if not all((payload.sku_verified, payload.rights_verified, payload.caption_verified, payload.price_availability_verified)):
        raise HTTPException(422, 'Confirme SKU, direitos de uso, legenda, preço e disponibilidade após revisar o vídeo')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        render = db.execute('SELECT * FROM renders WHERE id=?', (render_id,)).fetchone()
        if not render:
            raise HTTPException(404, 'Vídeo não encontrado')
        latest = db.execute('SELECT id FROM renders WHERE job_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1', (render['job_id'],)).fetchone()
        if latest['id'] != render_id:
            raise HTTPException(409, 'Existe uma versão mais recente')
        from app.media import safe_path, probe
        try:
            path = safe_path(render['uri'], Path(os.getenv('RENDER_ROOT', 'data/renders')))
            probe(path, final=True)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not path.is_file():
            raise HTTPException(409, 'Arquivo indisponível')
        with path.open('rb') as f:
            current_sha = hashlib.file_digest(f, 'sha256').hexdigest()
        if current_sha != render['sha256']:
            raise HTTPException(409, 'Arquivo alterado; gere uma nova versão')
        existing = db.execute('SELECT id FROM approvals WHERE render_id=? AND revoked_at IS NULL', (render_id,)).fetchone()
        if existing:
            raise HTTPException(409, 'Este vídeo já foi aprovado')
        approval_id = str(uuid4())
        db.execute('INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,NULL)', (approval_id, render_id, payload.reviewer, now(), render['sha256'], render['destination'], render['account_id'], render['caption']))
        db.execute("UPDATE jobs SET status='APPROVED' WHERE id=?", (render['job_id'],))
        db.execute('INSERT INTO audit_events VALUES (?,?,?,?,?,?)', (str(uuid4()), render['job_id'], 'APPROVED', payload.reviewer, now(), __import__('json').dumps({'approval_id': approval_id, 'checks': payload.model_dump()})))
    return {'approval_id': approval_id, 'status': 'APPROVED', 'publication_enabled': False}


@app.get('/media/models', dependencies=[Depends(require_operator)])
def find_model_photos(query: str = 'fashion model full body', per_page: int = 10):
    try:
        return {'photos': search_models(query, per_page), 'rights_review_required': True}
    except (PexelsError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


from app.pipeline_api import router
app.include_router(router, dependencies=[Depends(require_operator)])


@app.get('/', include_in_schema=False)
def studio():
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).parent / 'static' / 'index.html', headers={'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; media-src 'self' blob:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'", 'Cache-Control': 'no-store'})
