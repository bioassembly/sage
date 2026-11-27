import json
from pathlib import Path
import shutil
import tempfile
import unittest

from library import index, profiles


class FunctionalIndexTests(unittest.TestCase):
    def test_index_is_complete_current_and_searchable_by_function(self):
        self.assertFalse(index.sync())
        entries = index.rows(profiles.ROOT)
        self.assertEqual(len(entries), sum(len(items) for items in index.inventory(profiles.ROOT).values()))
        output = index.render(query='token saving', client='codex')
        self.assertIn('[token-efficiency]', output)
        self.assertIn('[rtk]', output)
        self.assertNotIn('[pyright]', output)
        self.assertEqual(output.count('[token-efficiency]'), 1)
        explicit = index.render(query='explicit', client='codex')
        self.assertIn('[grill-with-docs]', explicit)
        self.assertNotIn('[grilling]', explicit)
        self.assertIn('[pyright]', index.render(query='lsp', client='codex'))
        self.assertIn('[scientific-workflows]', index.render(query='brief'))
        self.assertIn('No capabilities match', index.render(query='zzmissing'))

    def test_missing_and_duplicate_group_entries_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ('clients', 'library'):
                shutil.copytree(profiles.ROOT / name, root / name, ignore=shutil.ignore_patterns('__pycache__', 'skills.local'))
            path = root / 'library/functions.json'
            groups = json.loads(path.read_text())
            groups['Token savings and context']['skill'].pop('ponytail')
            path.write_text(json.dumps(groups))
            with self.assertRaisesRegex(ValueError, 'ponytail'):
                index.sync(root, write=True)
            groups['Token savings and context']['skill']['sage-debug'] = 'Another purpose'
            path.write_text(json.dumps(groups))
            with self.assertRaisesRegex(ValueError, 'duplicate.*sage-debug'):
                index.sync(root, write=True)
