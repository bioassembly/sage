import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from library.scripts.validate_vendor import validate


class VendoredIntegrityTests(unittest.TestCase):
    def test_modified_or_missing_original_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill = root / 'skills/original/SKILL.md'
            skill.parent.mkdir(parents=True)
            content = 'Original upstream text.\r\n'.encode()
            skill.write_bytes(content)
            digest = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
            (root / 'third_party').mkdir()
            (root / 'third_party/lock.json').write_text(json.dumps({'skills': [
                {'name': 'original', 'files': {'SKILL.md': digest}}]}))
            self.assertEqual(validate(root, root / 'skills'), [])
            skill.write_text('Shortened adaptation.\n')
            self.assertIn('unrecorded upstream modification', validate(root, root / 'skills')[0])
            skill.unlink()
            self.assertIn('file list differs', validate(root, root / 'skills')[0])


if __name__ == '__main__':
    unittest.main()
