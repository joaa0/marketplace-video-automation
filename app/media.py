"""Immutable local assets and real FFmpeg validation; no remote URL fetching."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 50 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def media_root():
    root = Path(os.getenv('MEDIA_ROOT', 'data/media')).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_path(uri, root=None):
    path = Path(uri).resolve()
    root = (root or media_root()).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Arquivo fora da pasta autorizada ou indisponível')
    return path


def intact(asset):
    path = safe_path(asset['uri'])
    if digest(path) != asset['sha256']:
        raise ValueError('Mídia alterada; registre uma nova versão')
    return path


def command(args, timeout=120):
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('FFmpeg/ffprobe indisponível ou tempo limite excedido') from exc
    if result.returncode:
        raise ValueError('Mídia inválida ou falha no processamento audiovisual')
    return result.stdout


def probe(path, video=True, final=False):
    data = json.loads(command(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-show_streams', '-show_format', '-of', 'json', str(path)], 30))
    streams = data.get('streams', [])
    kind = 'video' if video else 'audio'
    stream = next((s for s in streams if s.get('codec_type') == kind), None)
    duration = float(data.get('format', {}).get('duration', 0))
    if not stream or not 0 < duration <= 300:
        raise ValueError('Arquivo deve conter mídia válida de até 300 segundos')
    if video and (stream.get('width', 0) > 4096 or stream.get('height', 0) > 4096):
        raise ValueError('Resolução máxima de entrada: 4096 pixels')
    if final:
        if stream.get('codec_name') != 'h264' or stream.get('pix_fmt') != 'yuv420p':
            raise ValueError('Vídeo final deve usar H.264 e yuv420p')
        if (stream.get('width'), stream.get('height')) != (720, 1280):
            raise ValueError('Vídeo final deve ser vertical, 720 × 1280')
        if not any(s.get('codec_type') == 'audio' and s.get('codec_name') == 'aac' for s in streams):
            raise ValueError('Vídeo final deve ter áudio AAC')
        # Decode the complete deliverable, not only its container metadata.
        command(['ffmpeg', '-v', 'error', '-xerror', '-protocol_whitelist', 'file,pipe', '-i', str(path), '-f', 'null', '-'], 120)
    return {'duration': duration, 'width': stream.get('width'), 'height': stream.get('height'),
            'codec': stream.get('codec_name'), 'has_audio': any(s.get('codec_type') == 'audio' for s in streams)}


def normalize_image(data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Envie uma imagem de até 50 MiB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ('JPEG', 'PNG', 'WEBP') or getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('Use JPEG, PNG ou WebP estático')
                if min(source.size) < 256:
                    raise ValueError('Imagem precisa ter pelo menos 256 pixels em cada dimensão')
                picture = ImageOps.exif_transpose(source).convert('RGBA')
                picture.thumbnail((2160, 2160))
                # Fresh pixels discard EXIF/GPS and arbitrary embedded metadata.
                clean = Image.new('RGB', picture.size)
                clean.paste('white', (0, 0, clean.width, clean.height))
                clean.paste(picture, mask=picture.getchannel('A'))
                output = io.BytesIO()
                clean.save(output, 'PNG')
                return output.getvalue(), {'width': clean.width, 'height': clean.height}
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError('Imagem inválida ou excessivamente grande') from exc


def store(data, kind):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Arquivo vazio ou maior que 50 MiB')
    metadata = {}
    suffix = '.png' if kind in ('model', 'garment', 'edited') else ('.mp4' if kind == 'clip' else '.audio')
    if suffix == '.png':
        data, metadata = normalize_image(data)
    elif kind == 'clip' and data[4:8] != b'ftyp':
        raise ValueError('Envie um clipe MP4, sem playlists ou URLs')
    elif kind == 'audio' and not (data.startswith((b'ID3', b'OggS', b'fLaC')) or (data[:4] == b'RIFF' and data[8:12] == b'WAVE') or (len(data) > 2 and data[0] == 255 and data[1] & 224 == 224)):
        raise ValueError('Use áudio WAV, MP3, Ogg ou FLAC')
    path = media_root() / (str(uuid4()) + suffix)
    path.write_bytes(data)
    try:
        if suffix != '.png':
            metadata = probe(path, video=kind == 'clip')
        return path, digest(path), metadata
    except Exception:
        path.unlink(missing_ok=True)
        raise


def render(source, output, duration=8, audio=None):
    """Pad without cropping the SKU. Explicit audio or silent AAC, always re-encode."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.stem + '.partial.mp4')
    is_image = source.suffix.lower() == '.png'
    args = ['ffmpeg', '-nostdin', '-y', '-v', 'error', '-threads', '1']
    args += ['-loop', '1'] if is_image else ['-stream_loop', '-1']
    args += ['-protocol_whitelist', 'file,pipe', '-i', str(source)]
    if audio:
        args += ['-stream_loop', '-1', '-protocol_whitelist', 'file,pipe', '-i', str(audio)]
    else:
        args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    args += ['-map', '0:v:0', '-map', '1:a:0', '-vf',
             'scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2,setsar=1',
             '-r', '30', '-t', str(duration), '-c:v', 'libx264', '-threads', '1', '-preset', 'veryfast',
             '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(temporary)]
    try:
        command(args, 240)
        metadata = probe(temporary, final=True)
        temporary.replace(output)
        return metadata
    finally:
        temporary.unlink(missing_ok=True)
