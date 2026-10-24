import os
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app


def test_approval_checks_file_and_version(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'db.sqlite'))
    monkeypatch.setenv('RENDER_ROOT', str(tmp_path / 'renders'))
    monkeypatch.setenv('OPERATOR_API_KEY', 'test-secret')
    from app.db import init_db
    init_db()
    client = TestClient(app)
    headers = {'X-Operator-Key': 'test-secret'}
    assert client.post('/products', json={'sku':'x','title':'t','product_url':'https://example.org'}).status_code == 401
    product = client.post('/products', headers=headers, json={'sku':'x','title':'t','product_url':'https://example.org'}).json()
    job = client.post('/jobs', headers=headers, json={'product_id':product['id']}).json()
    path = tmp_path / 'renders' / 'video.mp4'
    path.parent.mkdir()
    path.write_bytes(b'test-mp4-placeholder')
    render = client.post('/renders', headers=headers, json={'job_id':job['id'],'file_path':str(path),'caption':'legenda','destination':'SHOPEE','account_id':'acc'}).json()
    path.write_bytes(b'altered')
    assert client.post(f"/renders/{render['id']}/approve", headers=headers, json={'reviewer':'owner'}).status_code == 409
    path.write_bytes(b'test-mp4-placeholder')
    approved = client.post(f"/renders/{render['id']}/approve", headers=headers, json={'reviewer':'owner'})
    assert approved.status_code == 200
    assert approved.json()['publication_enabled'] is False
