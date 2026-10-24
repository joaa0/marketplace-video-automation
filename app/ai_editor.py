"""Gemini REST adapter. Live service needs separate credentialed acceptance testing."""
import base64
import os
import re
import httpx
from app.media import normalize_image


class EditorUnavailable(RuntimeError):
    pass


def edit_clothing(model_image: bytes, garment_image: bytes, instructions: str):
    key = os.getenv('GEMINI_API_KEY', '').strip()
    model = os.getenv('GEMINI_IMAGE_MODEL', '').strip()
    if not key or not re.fullmatch(r'[a-zA-Z0-9._-]+', model):
        raise EditorUnavailable('Configure GEMINI_API_KEY e GEMINI_IMAGE_MODEL; serviço externo ainda não validado')
    prompt = ('Edit the FIRST image: replace only the clothing with the exact garment in the SECOND image. '
              'Preserve the person identity, face, body proportions, pose, background and lighting. '
              'Preserve garment SKU details, color, pattern, logos and seams. No added text. '
              'The operator must review product fidelity before commercial use. Details: ' + instructions)
    parts = [{'text': prompt}]
    for data in (model_image, garment_image):
        parts.append({'inline_data': {'mime_type': 'image/png', 'data': base64.b64encode(data).decode()}})
    payload = {'contents': [{'parts': parts}], 'generationConfig': {'responseModalities': ['TEXT', 'IMAGE']}}
    # No automatic retries: a timeout may already have consumed paid credits.
    try:
        with httpx.Client(timeout=120, follow_redirects=False) as client:
            response = client.post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                                   headers={'x-goog-api-key': key}, json=payload)
            response.raise_for_status()
            result = response.json()
        for candidate in result.get('candidates', []):
            for part in candidate.get('content', {}).get('parts', []):
                inline = part.get('inlineData') or part.get('inline_data')
                if inline and inline.get('mimeType', inline.get('mime_type', '')).startswith('image/'):
                    return normalize_image(base64.b64decode(inline['data'], validate=True))[0]
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise EditorUnavailable('Falha ou resposta inválida do editor; verifique o provedor antes de repetir') from exc
    raise EditorUnavailable('Editor não retornou imagem; a solicitação pode ter sido filtrada')
