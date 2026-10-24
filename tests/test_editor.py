"""Protocol fixtures only: these tests do not call the Gemini service."""
import base64
import httpx
import pytest
from app.ai_editor import EditorUnavailable, edit_clothing
from conftest import image_bytes


def test_gemini_request_contract_and_image_response(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-only-secret')
    monkeypatch.setenv('GEMINI_IMAGE_MODEL', 'configured-image-model')
    real_client = httpx.Client
    calls = []
    def service(request):
        import json
        payload = json.loads(request.content)
        calls.append(payload)
        assert request.url.host == 'generativelanguage.googleapis.com'
        assert request.headers['x-goog-api-key'] == 'test-only-secret'
        assert payload['generationConfig']['responseModalities'] == ['TEXT', 'IMAGE']
        assert len(payload['contents'][0]['parts']) == 3
        return httpx.Response(200, json={'candidates': [{'content': {'parts': [
            {'inlineData': {'mimeType': 'image/png', 'data': base64.b64encode(image_bytes()).decode()}}
        ]}}]})
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(service), **kwargs))
    result = edit_clothing(image_bytes(), image_bytes('blue'), 'preservar gola')
    assert result.startswith(b'\x89PNG') and len(calls) == 1


@pytest.mark.parametrize('response', [{'candidates': []}, {'candidates': [{'content': {'parts': [{'text': 'refused'}]}}]}])
def test_editor_no_image_does_not_fabricate_result(monkeypatch, response):
    monkeypatch.setenv('GEMINI_API_KEY', 'test')
    monkeypatch.setenv('GEMINI_IMAGE_MODEL', 'test-model')
    real_client = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response)), **kwargs))
    with pytest.raises(EditorUnavailable):
        edit_clothing(image_bytes(), image_bytes(), '')
