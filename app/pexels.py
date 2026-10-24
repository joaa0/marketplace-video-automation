"""Pexels photo discovery. Results require individual rights review before ad use."""
import json
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class PexelsError(RuntimeError):
    pass


def search_models(query: str = 'fashion model full body', per_page: int = 10) -> list[dict]:
    key = os.getenv('PEXELS_API_KEY', '').strip()
    if not key:
        raise PexelsError('PEXELS_API_KEY não configurada')
    if not 1 <= per_page <= 30:
        raise ValueError('per_page deve estar entre 1 e 30')
    params = urlencode({'query': query, 'per_page': per_page, 'orientation': 'portrait'})
    request = Request('https://api.pexels.com/v1/search?' + params,
                      headers={'Authorization': key, 'User-Agent': 'MarketplaceVideoAutomation/0.3'})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except Exception as exc:
        raise PexelsError('Falha ao consultar Pexels') from exc
    return [{'id': photo['id'], 'url': photo['url'], 'photographer': photo.get('photographer'),
             'image_url': photo.get('src', {}).get('large2x'),
             'commercial_model_release_verified': False} for photo in payload.get('photos', [])]
