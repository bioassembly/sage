import io
import json
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from contextlib import redirect_stdout

from clients.codex import installer as codex
from library import profiles
from library.scripts import client_state as state, install_client


class NativeAgentOwnershipTests(unittest.TestCase):
    def record(self, target, changes):
        """Create the same before/after journal and manifest as an older install."""
        latest = target / 'sage/latest.json'
        managed = json.loads(latest.read_text()) if latest.exists() else {}
        entries = []
        for path, after in changes.items():
            entries.append(dict(path=str(path), before=state.snapshot(path), after=after))
            if path.name not in ('opencode.json', 'config.toml', 'mcp_config.json'):
                managed[str(path)] = state.fingerprint(after)
            state.apply_state(path, after)
        manifest = state.file_state(json.dumps(managed, indent=2) + '\n')
        entries.append(dict(path=str(latest), before=state.snapshot(latest), after=manifest))
        backup = latest.parent / 'backups'
        backup.mkdir(parents=True, exist_ok=True)
        (backup / f'install-{len(list(backup.iterdir()))}.json').write_text(json.dumps(dict(entries=entries)))
        state.apply_state(latest, manifest)

    def test_fresh_opencode_uses_native_agents_models_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            home = Path(tmp)
            target = home / '.config/opencode'
            first = install_client.install(profiles.ROOT, home, 'opencode')
            current = json.loads((target / 'opencode.json').read_text())
            self.assertFalse({'agent', 'default_agent', 'model', 'small_model', 'provider', 'permission'} & current.keys())
            self.assertFalse((target / 'agent').exists())
            self.assertFalse((target / 'agents').exists())
            for command in (target / 'command').glob('*.md'):
                self.assertTrue(command.name.startswith('sage-'))
                self.assertNotIn('\nagent:', command.read_text())
            state.restore(first)
            install_client.install(profiles.ROOT, home, 'opencode', base_url='http://127.0.0.1:9800/v1')
            selected = json.loads((target / 'opencode.json').read_text())
            self.assertEqual(selected['provider']['strata']['options']['baseURL'], 'http://127.0.0.1:9800/v1')
            self.assertNotIn('agent', selected)

    def test_opencode_releases_its_defaults_restores_personal_files_and_preserves_edits(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            home = Path(tmp)
            target = home / '.config/opencode'
            target.mkdir(parents=True)
            config = target / 'opencode.json'
            agent = target / 'agent/reviewer.md'
            edited = target / 'agent/skeptic.md'
            shortcut = target / 'command/review.md'
            personal = {'agent': {'plan': {'top_p': 0.9}, 'mine': {'temperature': 0.7}}, 'default_agent': 'mine'}
            config.write_text(json.dumps(personal))
            state.apply_state(agent, state.file_state('my original reviewer', 0o644))
            state.apply_state(shortcut, state.file_state('my original shortcut', 0o644))
            installed = json.loads(json.dumps(personal))
            installed['agent'].update({'skeptic': {'mode': 'subagent'}, 'build': {'temperature': 0.3, 'top_p': 0.85},
                                       'plan': {'temperature': 0.4, 'top_p': 0.9}, 'reviewer': {'mode': 'subagent'}})
            changes = {config: state.file_state(json.dumps(installed)),
                       agent: state.file_state('old reviewer'), edited: state.file_state('old skeptic'),
                       shortcut: state.file_state('old shortcut')}
            self.record(target, changes)
            self.record(target, changes)
            installed['agent']['build']['temperature'] = 0.71
            installed['agent']['skeptic'] = {}
            installed['new_setting'] = 'personal'
            config.write_text(json.dumps(installed))
            edited.write_text('my current skeptic')
            first = install_client.install(profiles.ROOT, home, 'opencode')
            result = json.loads(config.read_text())
            self.assertEqual(result['agent'], {**personal['agent'], 'build': {'temperature': 0.71}, 'skeptic': {}})
            self.assertEqual(result['default_agent'], 'mine')
            self.assertEqual(result['new_setting'], 'personal')
            self.assertEqual(agent.read_text(), 'my original reviewer')
            self.assertEqual(shortcut.read_text(), 'my original shortcut')
            self.assertEqual(edited.read_text(), 'my current skeptic')
            self.assertNotIn(str(agent), json.loads((target / 'sage/latest.json').read_text()))
            result['agent']['build'] = {'temperature': 0.3, 'top_p': 0.85}
            config.write_text(json.dumps(result))
            second = install_client.install(profiles.ROOT, home, 'opencode')
            self.assertEqual(json.loads(config.read_text())['agent'], result['agent'])
            state.restore(second)
            self.assertEqual(agent.read_text(), 'my original reviewer')
            # Restore the post-upgrade config before requesting the earlier journal.
            entry = next(e for e in json.loads(first.read_text())['entries'] if e['path'] == str(config))
            state.apply_state(config, entry['after'])
            state.restore(first)
            self.assertEqual(json.loads(config.read_text()), installed)
            self.assertEqual(agent.read_text(), 'old reviewer')

    @unittest.skipUnless(shutil.which('codex'), 'uses the native Codex TOML writer')
    def test_codex_relinquishes_agent_settings_with_the_native_writer(self):
        import argparse
        for initial in ('', '[agents]\nenabled = false\n'):
            with self.subTest(initial=initial), tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
                home = Path(tmp)
                target = home / '.codex'
                target.mkdir()
                config = target / 'config.toml'
                if initial:
                    config.write_text(initial)
                saved = '# retain comment\n[agents]\nenabled = ' + ('false' if initial else 'true') + '\nmax_concurrent_threads_per_session = 3\n'
                role = target / 'agents/sage-reviewer.toml'
                managed = target / 'sage/managed-config.json'
                self.record(target, {config: state.file_state(saved), role: state.file_state('old role'),
                                    managed: state.file_state(json.dumps({'agents': tomllib.loads(saved)['agents']}))})
                if initial:
                    config.write_text(saved + 'default_subagent_model = "chosen"\n')
                args = argparse.Namespace(codex_home=target, skills_dir=home / '.agents/skills', bin_dir=home/'bin',
                                          mcp=[], disable_mcp=[], dry_run=False, with_hybrid=None)
                before = config.read_bytes()
                journal = codex.install(args)
                result = tomllib.loads(config.read_text())
                if initial:
                    self.assertEqual(result['agents'], {'enabled': False, 'default_subagent_model': 'chosen'})
                else:
                    self.assertNotIn('agents', result)
                self.assertNotIn('agents', json.loads(managed.read_text()))
                self.assertFalse(role.exists())
                self.assertIn('# retain comment', config.read_text())
                state.restore(journal)
                self.assertEqual(config.read_bytes(), before)
                self.assertEqual(role.read_text(), 'old role')

    def test_antigravity_preserves_personal_roles_and_unproven_ownership(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            home = Path(tmp)
            target = home / '.gemini/config'
            role = target / 'agents/reviewer'
            role.parent.mkdir(parents=True)
            old = home / 'missing-old-role'
            role.symlink_to(old)
            personal = target / 'agents/personal/agent.md'
            state.apply_state(personal, state.file_state('my personal role'))
            latest = target / 'sage/latest.json'
            state.apply_state(latest, state.file_state(json.dumps({str(role): state.fingerprint(state.snapshot(role))})))
            install_client.install(profiles.ROOT, home, 'antigravity')
            self.assertEqual(role.readlink(), old)
            self.assertEqual(personal.read_text(), 'my personal role')
            owned = target / 'agents/orchestrator'
            self.record(target, {owned: {'kind':'symlink', 'target':str(old)}})
            journal = install_client.install(profiles.ROOT, home, 'antigravity')
            self.assertFalse(owned.is_symlink())
            self.assertTrue(role.is_symlink())
            state.restore(journal)
            self.assertTrue(owned.is_symlink())
