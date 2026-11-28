import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from library.scripts import install_client as installer


class ClientActivationTests(unittest.TestCase):
    def setUp(self):
        capture = patch('sys.stdout', new_callable=io.StringIO)
        capture.start()
        self.addCleanup(capture.stop)
        temp = tempfile.TemporaryDirectory(prefix='sage-client-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def prepare(self, client):
        repo = self.root / client
        source = repo / 'clients' / client
        (source / 'migration').mkdir(parents=True)
        lib = repo / 'library'
        (lib / 'skills/example').mkdir(parents=True)
        (lib / 'skills/example/SKILL.md').write_text('new public skill')
        (source / 'profile.json').write_text(json.dumps(dict(core=['example'], catalog=[], mcp=['docs'], optional_mcp=[], lsp=[])))
        (lib / 'routing.json').write_text('{}')
        for folder in ('mcp', 'lsp'):
            (lib / folder).mkdir()
        (lib / 'lsp/servers.json').write_text('{}')
        (lib / 'mcp/servers.json').write_text(json.dumps({'docs': {'url':'https://docs.example/v2', 'startup_seconds':10, 'tool_seconds':20}}))
        if client == 'opencode':
            (source / 'commands').mkdir()
            (source / 'defaults.json').write_text('{}')
        (lib / 'guidance.md').write_text('New shared rules.\n')
        old_rules = 'Old shared rules.\n'
        (source / 'migration/guidance.json').write_text(json.dumps(dict(
            first_line=old_rules.strip(), characters=len(old_rules), sha256=hashlib.sha256(old_rules.encode()).hexdigest())))
        key = 'mcp' if client == 'opencode' else 'mcpServers'
        old = {key: {'docs': {'url': 'https://docs.example/v1', 'enabled': True},
                     'hybrid-sage': {'command': ['hybrid'], 'enabled': True}}}
        (source / 'migration/legacy-mcp.json').write_text(json.dumps(old))
        home = self.root / (client + '-home')
        target = home / ('.config/opencode' if client == 'opencode' else '.gemini/config')
        target.mkdir(parents=True)
        config = target / ('opencode.json' if client == 'opencode' else 'mcp_config.json')
        personal = {**old, 'model': 'chosen-model', 'provider': {'private': {'key': 'test-sentinel'}}}
        config.write_text(json.dumps(personal))
        (target / 'AGENTS.md').write_text('Personal note.\nOld shared rules.\n')
        (target / 'skills/example').mkdir(parents=True)
        (target / 'skills/example/SKILL.md').write_text('old public skill')
        (target / 'skills/example/private-note.md').write_text('personal')
        return repo, home, target, config

    def test_both_clients_preserve_user_data_disable_hybrid_and_restore(self):
        for client in ('antigravity', 'opencode'):
            with self.subTest(client=client):
                repo, home, target, config = self.prepare(client)
                original = config.read_bytes()
                journal = installer.install(repo, home, client, disable_hybrid=True)
                actual = json.loads(config.read_text())
                key = 'mcp' if client == 'opencode' else 'mcpServers'
                self.assertEqual(actual['model'], 'chosen-model')
                self.assertEqual(actual['provider']['private']['key'], 'test-sentinel')
                self.assertEqual(actual[key]['docs']['url'], 'https://docs.example/v2')
                if client == 'opencode':self.assertFalse(actual[key]['hybrid-sage']['enabled'])
                else:self.assertTrue(actual[key]['hybrid-sage']['disabled'])
                self.assertIn('Personal note.', (target / 'AGENTS.md').read_text())
                self.assertNotIn('Old shared rules.', (target / 'AGENTS.md').read_text())
                self.assertEqual((target / 'skills/example/private-note.md').read_text(), 'personal')
                installer.harness.restore(journal)
                self.assertEqual(config.read_bytes(), original)
                self.assertEqual((target / 'skills/example/SKILL.md').read_text(), 'old public skill')

    def test_reinstall_and_dry_run_preserve_personal_skill_trees(self):
        repo, home, target, config = self.prepare('opencode')
        before = config.read_bytes()
        self.assertIsNone(installer.install(repo, home, 'opencode', dry_run=True))
        self.assertEqual(config.read_bytes(), before)
        self.assertFalse((target / 'sage').exists())
        first = installer.install(repo, home, 'opencode')
        content = (target / 'AGENTS.md').read_text()
        second = installer.install(repo, home, 'opencode')
        self.assertEqual((target / 'AGENTS.md').read_text(), content)
        installer.harness.restore(second)
        installer.harness.restore(first)

    def test_native_empty_config_is_valid_and_malformed_json_is_preserved(self):
        repo, home, _, config = self.prepare('antigravity')
        config.write_bytes(b'')
        journal = installer.install(repo, home, 'antigravity')
        self.assertIn('docs', json.loads(config.read_text())['mcpServers'])
        installer.harness.restore(journal)
        self.assertEqual(config.read_bytes(), b'')
        config.write_text('{')
        with self.assertRaises(json.JSONDecodeError):
            installer.install(repo, home, 'antigravity')
        self.assertEqual(config.read_text(), '{')

    def test_machine_local_override_survives_reinstall(self):
        repo, home, target, config = self.prepare('opencode')
        # Fresh target: original installers also support local overrides by name.
        import shutil
        shutil.rmtree(target / 'skills/example')
        local = repo / 'clients/opencode/skills.local/example'
        local.mkdir(parents=True)
        (local / 'SKILL.md').write_text('private local skill')
        first = installer.install(repo, home, 'opencode')
        second = installer.install(repo, home, 'opencode')
        routes = json.loads((target / 'skills-catalog/routing.json').read_text())
        self.assertEqual(routes['core_packages']['example']['path'], str(local / 'SKILL.md'))
        installer.harness.restore(second)
        installer.harness.restore(first)

    def test_disable_retires_only_hybrid_autoload_plugins_and_restores_them(self):
        for client in ('antigravity', 'opencode'):
            repo, home, target, config = self.prepare(client)
            path = target / ('plugins/hybrid-sage.mjs' if client == 'opencode' else 'plugins/hybrid-sage/plugin.json')
            path.parent.mkdir(parents=True)
            path.write_text('managed hybrid fixture')
            personal = target / 'plugins/personal.mjs'
            personal.parent.mkdir(parents=True, exist_ok=True)
            personal.write_text('personal plugin')
            journal = installer.install(repo, home, client, disable_hybrid=True)
            self.assertFalse(path.exists())
            self.assertTrue(personal.exists())
            installer.harness.restore(journal)
            self.assertEqual(path.read_text(), 'managed hybrid fixture')

    def test_tiered_skills_install_router_and_tidy_retired_dirs_on_upgrade(self):
        for client in ('antigravity', 'opencode'):
            with self.subTest(client=client):
                repo, home, target, _ = self.prepare(client)
                source = repo / 'clients' / client
                lib = repo / 'library'
                (lib / 'skills/bio').mkdir()
                (lib / 'skills/bio/SKILL.md').write_text('---\nname: bio\ndescription: Bio workflow\n---\n')
                plan = json.loads((source / 'profile.json').read_text())
                plan['catalog'] = ['bio']
                (source / 'profile.json').write_text(json.dumps(plan))
                (lib / 'routing.json').write_text(json.dumps({'bio': {'category': 'bio', 'summary': 'Bio', 'patterns': ['bio']}}))
                if client == 'opencode':
                    (source / 'router.ts').write_text('// router')
                else:
                    plugin = lib / 'runtime/skill_router'
                    plugin.mkdir(parents=True)
                    (plugin / 'plugin.json').write_text('{}')
                # Simulate an old copied non-core skill directory tracked by previous install.
                old_bio_md = target / 'skills/bio/SKILL.md'
                old_bio_md.parent.mkdir(parents=True, exist_ok=True)
                old_bio_md.write_text('old bio')
                (target / 'sage').mkdir(parents=True, exist_ok=True)
                (target / 'sage/latest.json').write_text(
                    json.dumps({str(old_bio_md): installer.harness.fingerprint(installer.harness.snapshot(old_bio_md))})
                )

                journal = installer.install(repo, home, client)
                self.assertTrue((target / 'skills/example/SKILL.md').is_file())
                self.assertFalse((target / 'skills/bio').exists())
                self.assertTrue((target / 'skills-catalog/bio/SKILL.md').is_file())
                self.assertTrue((target / 'skills-catalog/routing.json').is_file())
                expected_plugin = target / ('plugins/sage-skill-router.ts' if client == 'opencode' else 'plugins/sage-skill-router/plugin.json')
                self.assertTrue(expected_plugin.is_file())

                installer.harness.restore(journal)
                self.assertEqual(old_bio_md.read_text(), 'old bio')


if __name__ == '__main__':
    unittest.main()
