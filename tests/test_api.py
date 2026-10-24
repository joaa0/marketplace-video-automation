from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db

def test_create_product_and_job(tmp_path, monkeypatch):
    monkeypatch.setenv('DB_PATH', str(tmp_path / 'test.sqlite3'))
    monkeypatch.setenv('OPERATOR_API_KEY', 'test-secret')
    headers = {'X-Operator-Key': 'test-secret'}
    init_db()
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        product = client.post('/products', headers=headers, json={'sku':'SKU-1','title':'Camisa','product_url':'https://example.org/product'}).json()
        response = client.post('/jobs', headers=headers, json={'product_id':product['id']})
        assert response.status_code == 201
        assert client.get('/jobs/' + response.json()['id'], headers=headers).json()['status'] == 'NEW'
        assert client.post('/jobs', headers=headers, json={'product_id':'missing'}).status_code == 404


def test_studio_is_available_without_disclosing_credentials():
    with TestClient(app) as client:
        response = client.get('/')
    assert response.status_code == 200
    assert '<html lang="pt-BR">' in response.text
    assert 'localStorage' not in response.text
    assert 'frame-ancestors' in response.headers['Content-Security-Policy']
