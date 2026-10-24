import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image

spec = importlib.util.spec_from_file_location('compute_app', Path(__file__).with_name('app.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class AdapterTest(unittest.TestCase):
    def test_internal_token_idempotency_conflict_and_no_path_input(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'COMPUTE_TOKEN': 'local-compute-fixture-token'}):
            module.ROOT = Path(directory)
            client = TestClient(module.app)
            raw = io.BytesIO(); Image.new('RGB', (200, 100), 'white').save(raw, format='PNG')
            def call(params, token='local-compute-fixture-token'):
                return client.post('/internal/compute/fixture-job-123', headers={'X-Internal-Token': token}, data={'params': json.dumps(params)}, files={'file': ('test.png', raw.getvalue(), 'image/png')})
            self.assertEqual(403, call({'operation': 'RESIZE', 'size': 64}, 'wrong').status_code)
            self.assertEqual(422, call({'operation': 'RESIZE', 'size': 64, 'path': 'C:/private'}).status_code)
            first = call({'operation': 'RESIZE', 'size': 64})
            self.assertEqual(200, first.status_code)
            self.assertEqual(first.content, call({'operation': 'RESIZE', 'size': 64}).content)
            self.assertEqual(409, call({'operation': 'RESIZE', 'size': 65}).status_code)
            with zipfile.ZipFile(io.BytesIO(first.content)) as result:
                manifest = json.loads(result.read('manifest.json'))
                self.assertEqual(64, manifest['width'])
                self.assertEqual('Pillow', manifest['engine'])

    def test_missing_model_returns_unavailable_without_output(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'COMPUTE_TOKEN': 'fixture', 'OCR_DET_MODEL': '', 'OCR_REC_MODEL': '', 'OCR_CLS_MODEL': ''}):
            module.ROOT = Path(directory)
            raw = io.BytesIO(); Image.new('RGB', (10, 10)).save(raw, format='PNG')
            response = TestClient(module.app).post('/internal/compute/no-model-job', headers={'X-Internal-Token': 'fixture'}, data={'params': '{"operation":"OCR"}'}, files={'file': ('a.png', raw.getvalue(), 'image/png')})
            self.assertEqual(503, response.status_code)
            self.assertFalse((Path(directory) / 'no-model-job/result.zip').exists())

if __name__ == '__main__': unittest.main()
