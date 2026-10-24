"""Optional Python algorithms only. No business DB, platform keys, filesystem paths or callbacks in requests."""
import hashlib
import hmac
import io
import json
import os
import re
import threading
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from PIL import Image, ImageOps

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
ROOT = Path(os.environ.get('COMPUTE_CACHE', './cache')).resolve()
CAPACITY = threading.BoundedSemaphore(2)
LOCK = threading.Lock()
ACTIVE = set()
Image.MAX_IMAGE_PIXELS = 40_000_000

def execute(job, raw, parameters):
    fingerprint = hashlib.sha256(raw + json.dumps(parameters, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    folder = ROOT / job
    marker = folder / 'input.json'
    with LOCK:
        folder.mkdir(parents=True, exist_ok=True)
        if marker.exists() and json.loads(marker.read_text())['fingerprint'] != fingerprint:
            raise HTTPException(409, 'Same jobId has different inputs')
        if (folder / 'result.zip').exists():
            return (folder / 'result.zip').read_bytes()
        if job in ACTIVE:
            raise HTTPException(409, 'Job is running')
        if not CAPACITY.acquire(blocking=False):
            raise HTTPException(503, 'Compute capacity is full')
        ACTIVE.add(job)
        marker.write_text(json.dumps({'fingerprint': fingerprint}), encoding='utf-8')
    try:
        if not raw or len(raw) > 30 * 1024 * 1024:
            raise HTTPException(422, 'Input image exceeds limit')
        try:
            image = Image.open(io.BytesIO(raw))
            if image.width > 12000 or image.height > 12000 or image.width * image.height > 40_000_000:
                raise ValueError('pixel limit')
            image.load()
        except Exception as exc:
            raise HTTPException(422, 'Cannot decode image') from exc
        operation = parameters.get('operation')
        manifest = {'jobId': job, 'input_fingerprint': fingerprint, 'operation': operation, 'language': 'Python', 'algorithm_version': 'compute-v1'}
        output = None
        if operation == 'OCR':
            model_paths = {key: os.environ.get(name, '') for key, name in [('Det.model_path', 'OCR_DET_MODEL'), ('Rec.model_path', 'OCR_REC_MODEL'), ('Cls.model_path', 'OCR_CLS_MODEL')]}
            if not all(path and Path(path).is_file() for path in model_paths.values()):
                raise HTTPException(503, 'OCR local models are not configured; no recognition performed')
            try:
                from rapidocr import RapidOCR
                result = RapidOCR(params=model_paths)(raw)
                manifest['text'] = '\n'.join(result.txts or [])[:12000]
                manifest['engine'] = 'RapidOCR'
            except ImportError as exc:
                raise HTTPException(503, 'RapidOCR runtime is not installed') from exc
        elif operation == 'REMOVE_BACKGROUND':
            model_root = os.environ.get('U2NET_HOME', '')
            if not model_root or not (Path(model_root) / 'birefnet-general.onnx').is_file():
                raise HTTPException(503, 'BiRefNet local model is not configured; no background removal performed')
            try:
                from rembg import new_session, remove
                output = Image.open(io.BytesIO(remove(raw, session=new_session('birefnet-general'))))
                manifest['engine'] = 'BiRefNet'
            except ImportError as exc:
                raise HTTPException(503, 'rembg runtime is not installed') from exc
        elif operation == 'RESIZE':
            size = parameters.get('size')
            if not isinstance(size, int) or isinstance(size, bool) or size < 64 or size > 2400:
                raise HTTPException(422, 'size must be an integer between 64 and 2400')
            output = ImageOps.contain(image, (size, size))
            manifest['engine'] = 'Pillow'
        else:
            raise HTTPException(422, 'Unsupported operation')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
            if output:
                product = io.BytesIO(); output.save(product, format='PNG'); archive.writestr('output.png', product.getvalue())
                manifest.update({'sha256': hashlib.sha256(product.getvalue()).hexdigest(), 'width': output.width, 'height': output.height})
            archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
        result = stream.getvalue()
        temporary = folder / 'result.tmp'
        temporary.write_bytes(result); temporary.replace(folder / 'result.zip')
        return result
    finally:
        with LOCK:
            ACTIVE.discard(job)
            CAPACITY.release()

@app.post('/internal/compute/{job_id}')
async def compute(job_id: str, file: UploadFile = File(...), params: str = Form(...), x_internal_token: str = Header(default='')):
    expected = os.environ.get('COMPUTE_TOKEN', '')
    if not expected or not hmac.compare_digest(expected, x_internal_token):
        raise HTTPException(403, 'Internal token required')
    if not re.fullmatch(r'[a-zA-Z0-9-]{8,80}', job_id):
        raise HTTPException(422, 'Invalid jobId')
    try:
        parameters = json.loads(params)
        if not isinstance(parameters, dict) or set(parameters) - {'operation', 'size', 'skuFacts', 'dimensions', 'inputFingerprint'}:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, 'Invalid parameters; paths, SQL and callback URLs are not accepted')
    raw = await file.read(30 * 1024 * 1024 + 1)
    result = await run_in_threadpool(execute, job_id, raw, parameters)
    return Response(result, media_type='application/zip')
