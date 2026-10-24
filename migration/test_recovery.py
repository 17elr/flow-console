import importlib.util
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('recovery', Path(__file__).with_name('recover_remote_assets.py'))
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

class RecoveryTest(unittest.TestCase):
    def test_only_verified_existing_objects_are_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Mock(); client.get_object.side_effect = [{'Body':io.BytesIO(b'original')}, {'Body':io.BytesIO(b'wrong')}]
            digest = hashlib.sha256(b'original').hexdigest()
            rows = [{'storage_key':'packaging/a.png','sha256':digest},{'storage_key':'packaging/b.png','sha256':'0'*64}]
            root = Path(directory)/'new-overlay'; report = module.recover(client,'fixture',rows,set(),root)
            self.assertEqual(b'original',(root/'packaging/a.png').read_bytes()); self.assertFalse((root/'packaging/b.png').exists())
            self.assertEqual(1,len(report['unavailable'])); self.assertEqual(0,report['remote_writes']); client.put_object.assert_not_called(); client.delete_object.assert_not_called()
