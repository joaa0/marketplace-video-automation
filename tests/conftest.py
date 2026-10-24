import io
import wave
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from app.main import app

CHECKS = {'reviewer': 'owner', 'sku_verified': True, 'rights_verified': True,
          'caption_verified': True, 'price_availability_verified': True}


def image_bytes(color='red'):
    output = io.BytesIO()
    Image.new('RGB', (360, 640), color).save(output, 'PNG')
    return output.getvalue()


def audio_bytes():
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48000)
        handle.writeframes(b'\x00\x00' * 48000)
    return output.getvalue()


@pytest.fixture
def operator(tmp_path, monkeypatch):
    for key, value in {'DB_PATH': str(tmp_path / 'db.sqlite3'), 'MEDIA_ROOT': str(tmp_path / 'media'),
                       'RENDER_ROOT': str(tmp_path / 'renders'), 'OPERATOR_API_KEY': 'test-secret'}.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GEMINI_IMAGE_MODEL', raising=False)
    with TestClient(app) as client:
        client.headers.update({'X-Operator-Key': 'test-secret'})
        yield client


def create_job(client):
    product = client.post('/products', json={'sku': 'CAM-001', 'title': 'Camisa', 'product_url': 'https://example.org/item'})
    assert product.status_code == 201
    response = client.post('/jobs', json={'product_id': product.json()['id']})
    assert response.status_code == 201
    return response.json()['id']


def upload(client, job, kind='garment', data=None):
    response = client.post(f'/jobs/{job}/assets', data={'kind': kind, 'source': 'Foto própria',
                           'rights_evidence': 'Autorização de uso e edição arquivada, referência T-1'},
                           files={'file': ('reference.png', data if data is not None else image_bytes(), 'application/octet-stream')})
    assert response.status_code == 201, response.text
    return response.json()


def queue_render(client, job, visual, audio=None):
    response = client.post(f'/jobs/{job}/render-tasks', json={'visual_asset_id': visual,
                           'audio_asset_id': audio, 'duration': 2, 'caption': 'Camisa — confira os detalhes',
                           'destination': 'SHOPEE', 'account_id': 'loja-1'})
    assert response.status_code == 202, response.text
    return response.json()['id']


def finish(client, task):
    from app.worker import run_once
    assert run_once()
    response = client.get(f'/tasks/{task}').json()
    assert response['status'] == 'DONE', response
    import json
    return json.loads(response['result'])['render_id']
