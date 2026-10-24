from pathlib import Path
from app.media import render
from conftest import CHECKS, create_job, image_bytes


def test_approval_checks_file_and_version(operator, tmp_path):
    client = operator
    job = create_job(client)
    source = tmp_path / 'image.png'
    source.write_bytes(image_bytes())
    path = tmp_path / 'renders' / 'video.mp4'
    path.parent.mkdir()
    path.write_bytes(b'test-mp4-placeholder')
    payload = {'job_id': job, 'file_path': str(path), 'caption': 'legenda', 'destination': 'SHOPEE', 'account_id': 'acc'}
    assert client.post('/renders', json=payload).status_code == 422
    render(source, path, 2)
    data = path.read_bytes()
    response = client.post('/renders', json=payload)
    assert response.status_code == 201, response.text
    render_id = response.json()['id']
    path.write_bytes(b'altered')
    assert client.post(f'/renders/{render_id}/approve', json=CHECKS).status_code == 409
    path.write_bytes(data)
    assert client.post(f'/renders/{render_id}/approve', json={'reviewer': 'owner'}).status_code == 422
    approved = client.post(f'/renders/{render_id}/approve', json=CHECKS)
    assert approved.status_code == 200
    assert approved.json()['publication_enabled'] is False
    assert client.post(f'/renders/{render_id}/approve', json=CHECKS).status_code == 409
    assert client.get(f'/renders/{render_id}/export').status_code == 409  # missing source provenance
