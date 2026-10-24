import pytest
from app.pexels import PexelsError, search_models


def test_pexels_requires_key(monkeypatch):
    monkeypatch.delenv('PEXELS_API_KEY', raising=False)
    with pytest.raises(PexelsError):
        search_models()


def test_pexels_rejects_bad_limit(monkeypatch):
    monkeypatch.setenv('PEXELS_API_KEY', 'test')
    with pytest.raises(ValueError):
        search_models(per_page=100)
