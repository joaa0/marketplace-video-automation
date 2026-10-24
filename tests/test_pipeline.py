import hashlib
import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from app.db import connect
from app.media import normalize_image, probe
from app.worker import claim, run_once
from conftest import CHECKS, audio_bytes, create_job, finish, image_bytes, queue_render, upload


def test_real_image_audio_render_approve_export_revoke(operator):
    job = create_job(operator)
    visual = upload(operator, job)
    audio = upload(operator, job, 'audio', audio_bytes())
    task = queue_render(operator, job, visual['id'], audio['id'])
    render_id = finish(operator, task)
    response = operator.get(f'/renders/{render_id}/file')
    assert response.status_code == 200 and response.content[4:8] == b'ftyp'
    with connect() as db:
        record = db.execute('SELECT * FROM renders WHERE id=?', (render_id,)).fetchone()
    metadata = probe(Path(record['uri']), final=True)
    assert metadata['width'] == 720 and metadata['height'] == 1280
    assert 1.9 <= metadata['duration'] <= 2.2 and metadata['has_audio']
    assert operator.get(f'/renders/{render_id}/export').status_code == 409
    assert operator.post(f'/renders/{render_id}/approve', json=CHECKS).status_code == 200
    response = operator.get(f'/renders/{render_id}/export')
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        approval = json.loads(archive.read('aprovacao.json'))
        assert hashlib.sha256(archive.read('video.mp4')).hexdigest() == approval['sha256']
        assert approval['destination'] == 'SHOPEE' and approval['account_id'] == 'loja-1'
        assert len(json.loads(archive.read('origens.json'))) == 2
        assert 'Camisa' in archive.read('legenda.txt').decode()
    events = operator.get(f'/jobs/{job}/audit').json()
    assert {'ASSET_REGISTERED', 'RENDER_QUEUED', 'RENDER_REGISTERED', 'APPROVED', 'EXPORT_CREATED'} <= {r['action'] for r in events}
    operator.post(f'/renders/{render_id}/revoke')
    assert operator.get(f'/renders/{render_id}/export').status_code == 409


def test_new_version_revokes_previous_and_source_tamper_blocks_export(operator):
    job = create_job(operator)
    asset = upload(operator, job)
    first = finish(operator, queue_render(operator, job, asset['id']))
    operator.post(f'/renders/{first}/approve', json=CHECKS)
    second = finish(operator, queue_render(operator, job, asset['id']))
    assert operator.post(f'/renders/{first}/approve', json=CHECKS).status_code == 409
    assert operator.get(f'/renders/{first}/export').status_code == 409
    assert operator.post(f'/renders/{second}/approve', json=CHECKS).status_code == 200
    Path(asset['uri']).write_bytes(image_bytes('blue'))
    assert operator.get(f'/renders/{second}/export').status_code == 409


def test_duplicate_queue_and_cross_job_asset(operator):
    job = create_job(operator)
    asset = upload(operator, job)
    queue_render(operator, job, asset['id'])
    payload = {'visual_asset_id': asset['id'], 'caption': 'x', 'destination': 'x', 'account_id': 'x'}
    assert operator.post(f'/jobs/{job}/render-tasks', json=payload).status_code == 409
    other = create_job(operator)
    assert operator.post(f'/jobs/{other}/render-tasks', json=payload).status_code == 422
    assert operator.get('/tasks/missing').status_code == 404
    assert operator.get('/assets/missing/file').status_code == 404


def test_lease_recovery_and_bounded_retries(operator, monkeypatch):
    job = create_job(operator)
    asset = upload(operator, job)
    task = queue_render(operator, job, asset['id'])
    first = claim()
    assert first and claim() is None
    with connect() as db:
        db.execute('UPDATE tasks SET lease_until=0 WHERE id=?', (task,))
    resumed = claim()
    assert resumed['attempts'] == 2 and resumed['lease_token'] != first['lease_token']
    with connect() as db:
        db.execute('UPDATE tasks SET lease_until=0 WHERE id=?', (task,))
    import app.worker
    def fail(*args, **kwargs):
        raise ValueError('Falha local deliberada')
    monkeypatch.setattr(app.worker, 'render', fail)
    assert run_once()
    assert operator.get(f'/tasks/{task}').json()['status'] == 'FAILED'
    assert claim() is None


def test_worker_retries_tampered_source(operator):
    job = create_job(operator)
    asset = upload(operator, job)
    task = queue_render(operator, job, asset['id'])
    Path(asset['uri']).write_bytes(b'changed')
    for attempt in range(3):
        with connect() as db:
            db.execute('UPDATE tasks SET available_at=0 WHERE id=?', (task,))
        assert run_once()
    record = operator.get(f'/tasks/{task}').json()
    assert record['status'] == 'FAILED' and record['attempts'] == 3


def test_flow_assisted_roundtrip_with_real_local_clip(operator):
    job = create_job(operator)
    asset = upload(operator, job)
    response = operator.post(f'/jobs/{job}/flow-requests', json={'asset_id': asset['id'], 'prompt': 'Movimento suave, preserve a roupa e a identidade.'})
    assert response.status_code == 201, response.text
    flow = response.json()
    assert flow['live_integration_verified'] is False
    package = operator.get(flow['package_url'])
    with zipfile.ZipFile(io.BytesIO(package.content)) as archive:
        assert archive.read('reference.png') == Path(asset['uri']).read_bytes()
    # This is a local FFmpeg fixture, not a claim to have contacted Google Flow.
    local_render = finish(operator, queue_render(operator, job, asset['id']))
    clip_data = operator.get(f'/renders/{local_render}/file').content
    clip = upload(operator, job, 'clip', clip_data)
    returned = operator.post(f'/flow-requests/{flow["id"]}/complete', json={'clip_asset_id': clip['id']})
    assert returned.status_code == 200 and returned.json()['google_session_tested'] is False
    assert operator.post(f'/flow-requests/{flow["id"]}/complete', json={'clip_asset_id': clip['id']}).status_code == 409
    rendered = finish(operator, queue_render(operator, job, clip['id']))
    assert operator.post(f'/renders/{rendered}/approve', json=CHECKS).status_code == 200
    exported = operator.get(f'/renders/{rendered}/export')
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert len(json.loads(archive.read('origens.json'))) == 2


def test_clothing_editor_missing_config_fails_closed(operator):
    job = create_job(operator)
    model = upload(operator, job, 'model')
    garment = upload(operator, job, 'garment')
    response = operator.post(f'/jobs/{job}/edit-clothing', json={'model_asset_id': model['id'], 'garment_asset_id': garment['id']})
    assert response.status_code == 503
    assert len(operator.get(f'/jobs/{job}/assets').json()) == 2


@pytest.mark.parametrize('kind,data', [('model', b'fake'), ('clip', b'#EXTM3U\nhttps://example.org'), ('audio', b'https://example.org')])
def test_bad_media_rejected(operator, kind, data):
    job = create_job(operator)
    response = operator.post(f'/jobs/{job}/assets', data={'kind': kind, 'source': 'x', 'rights_evidence': 'sim'}, files={'file': ('x', data)})
    assert response.status_code == 422


def test_images_strip_metadata_and_enforce_minimum():
    from PIL import Image
    from PIL.PngImagePlugin import PngInfo
    output = io.BytesIO()
    info = PngInfo()
    info.add_text('location', 'private GPS')
    Image.new('RGB', (360, 640)).save(output, 'PNG', pnginfo=info)
    normalized, metadata = normalize_image(output.getvalue())
    with Image.open(io.BytesIO(normalized)) as image:
        assert 'location' not in image.info
    tiny = io.BytesIO()
    Image.new('RGB', (10, 10)).save(tiny, 'PNG')
    with pytest.raises(ValueError):
        normalize_image(tiny.getvalue())


def test_auth_is_required_on_new_routes(operator):
    operator.headers.clear()
    for url in ('/jobs', '/assets/x/file', '/tasks/x', '/renders/x/export', '/flow-requests/x/package'):
        assert operator.get(url).status_code == 401
