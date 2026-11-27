import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from library import index, profiles
from library.lsp import provision, wsl_bash
from library.scripts import client_state, merge_config
from library.runtime.skill_router import route_skills

ROOT = profiles.ROOT


class ProfileTests(unittest.TestCase):
    def test_explicit_policy_survives_profile_overrides_and_companion_edges(self):
        plan = profiles.profile('opencode')
        plan['rule_overrides'] = {'grill-with-docs': {'files': ['*'], 'patterns': ['.*']}}
        entries = profiles.routing(plan, ROOT / 'library')['rules']
        interview = next(rule for rule in entries if rule['skill'] == 'grill-with-docs')
        self.assertTrue(interview['explicit_only'])
        self.assertNotIn('files', interview)
        self.assertEqual(route_skills.match_prompt('Fix a typo', [interview]), [])
        self.assertEqual(route_skills.match_prompt('[$grill-with-docs](/skills/grill-with-docs/SKILL.md)', [interview]),
                         ['grill-with-docs'])
        plan['rule_overrides']['red-team'] = {'companions': ['grill-with-docs']}
        with self.assertRaisesRegex(ValueError, 'explicit-only companion'):
            profiles.routing(plan, ROOT / 'library')

    def test_each_supported_manual_policy_is_sufficient(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            skill = path / 'SKILL.md'
            skill.write_text('---\nname: sample\ndisable-model-invocation: true\n---\n')
            self.assertTrue(profiles.requires_invocation(path))
            skill.write_text('---\nname: sample\n---\ndisable-model-invocation: true\n')
            self.assertFalse(profiles.requires_invocation(path))
            (path / 'agents').mkdir()
            (path / 'agents/openai.yaml').write_text('policy:\n  allow_implicit_invocation: false\n')
            self.assertTrue(profiles.requires_invocation(path))

    def test_catalog_rejects_duplicate_native_registrations(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib = Path(tmp) / 'library'
            for kind, name in [('mcp', 'context7'), ('lsp', 'typescript')]:
                (lib / kind).mkdir(parents=True)
                shutil.copyfile(ROOT / 'library' / kind / 'servers.json', lib / kind / 'servers.json')
            for kind, name in [('mcp', 'context7'), ('lsp', 'typescript')]:
                path = lib / kind / 'servers.json'
                specs = profiles.read(path)
                path.write_text(profiles.formatted({**specs, 'copied': specs[name]}))
                with self.assertRaisesRegex(ValueError, 'duplicates the registration'):
                    profiles.validate_catalog(Path(tmp))
                path.write_text(profiles.formatted(specs))

    def test_profiles_share_real_packages_and_route_graph_requests_on_demand(self):
        skill = ROOT / 'library/skills/workflow-graph/SKILL.md'
        for client in profiles.CLIENTS:
            plan = profiles.profile(client)
            routes = profiles.routing(plan, ROOT / 'library')
            self.assertNotIn('workflow-graph', routes['core'])
            self.assertTrue(skill.is_file())
            self.assertEqual(set(plan['catalog']), {r['skill'] for r in routes['rules']})
            for prompt in ['Make a workflow graph of this repo', 'Visualize the architecture', 'Refresh the Graphviz diagrams']:
                self.assertIn('workflow-graph', route_skills.match_prompt(prompt, routes['rules']))
            self.assertNotIn('workflow-graph', route_skills.match_prompt('Fix a misspelled error message', routes['rules']))

    def test_tuning_changes_native_behavior_and_only_the_selected_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'another checkout'
            shutil.copytree(ROOT, root, symlinks=True, ignore=shutil.ignore_patterns('.git', '.state', '__pycache__'))
            file = root / 'clients/opencode/profile.json'
            plan = profiles.read(file)
            plan['catalog'].remove('workflow-graph')
            plan['core'].append('workflow-graph')
            plan['catalog'].remove('web-scraping')
            plan['mcp'].remove('deepwiki')
            plan['lsp'] = ['pyright']
            file.write_text(profiles.formatted(plan))
            with self.assertRaisesRegex(ValueError, 'Stale library'):
                index.sync(root)
            profiles.validate(root=root)
            index.sync(root, write=True)
            self.assertFalse(index.sync(root))
            self.assertIn('web-scraping', profiles.profile('antigravity', root)['catalog'])
            home = Path(tmp) / 'test user'
            subprocess.run([sys.executable, root / 'sage.py', 'install', 'opencode', '--home', home], check=True, capture_output=True)
            installed = home / '.config/opencode'
            self.assertTrue((installed / 'skills/workflow-graph/SKILL.md').samefile(root / 'library/skills/workflow-graph/SKILL.md'))
            config = profiles.read(installed / 'opencode.json')
            self.assertEqual(set(config['lsp']), {'pyright'})
            self.assertNotIn('deepwiki', config['mcp'])
            self.assertFalse((installed / 'skills-catalog/web-scraping').exists())
            plan['catalog'].append('missing-skill')
            file.write_text(profiles.formatted(plan))
            before = (root / 'library/INDEX.md').read_bytes()
            with self.assertRaisesRegex(ValueError, 'unknown'):
                profiles.validate(root=root)
            self.assertEqual(before, (root / 'library/INDEX.md').read_bytes())

    def test_lsp_upgrades_only_refresh_previously_managed_entries(self):
        old = {'pyright': {'command': ['old']}, 'bash': {'command': ['bash']}, 'yaml': {'command': ['yaml']}}
        current = {**old, 'bash': {'command': ['mine']}, 'custom': {'command': ['private']}}
        new = {'pyright': {'command': ['new']}, 'bash': {'command': ['updated']}}
        result = merge_config.merge({'lsp': new}, {'lsp': current}, {'lsp': old}, 'opencode')
        self.assertEqual(result['lsp'], {'pyright': new['pyright'], 'bash': current['bash'], 'custom': current['custom']})
        self.assertIs(merge_config.merge({'lsp': new}, {'lsp': False}, {'lsp': old}, 'opencode')['lsp'], False)

    def test_wsl_bash_environment_is_scoped_to_the_server(self):
        command = ['bash-language-server', 'start']
        with patch.object(provision.platform, 'release', return_value='linux-microsoft-WSL2'):
            adapted = provision.native_command(command)
            self.assertEqual(Path(adapted[1]).resolve(), Path(wsl_bash.__file__).resolve())
            self.assertEqual(adapted[2:], ['start'])
        with patch.object(provision.platform, 'release', return_value='linux'):
            self.assertEqual(provision.native_command(command), command)
        original = {'PATH': '/usr/bin:/mnt/c/Windows:/mnt/data/bin:/tools:/usr/bin', 'OTHER': 'keep'}
        self.assertEqual(wsl_bash.server_environment(original), {'PATH': '/usr/bin:/mnt/data/bin:/tools', 'OTHER': 'keep'})
        self.assertIn('/mnt/c/Windows', original['PATH'])
        full = {**original, 'SAGE_BASH_LSP_FULL_PATH': '1'}
        self.assertEqual(wsl_bash.server_environment(full), full)

    def test_lsp_provision_uses_selected_pins_and_rejects_bad_binary(self):
        catalog = profiles.read(ROOT / 'library/lsp/servers.json')
        with tempfile.TemporaryDirectory() as tmp, patch.object(provision.shutil, 'which', return_value=None), \
                patch.object(provision.subprocess, 'run') as run:
            prefix = Path(tmp)
            provision.provision(['bash'], catalog, prefix)
            run.assert_not_called()
            provision.provision(['bash'], catalog, prefix, True)
            self.assertEqual(run.call_args.args[0], ['npm', 'install', '--global', '--prefix', tmp, *catalog['bash']['npm']])
            with patch.object(provision.platform, 'system', return_value='Linux'), \
                    patch.object(provision.platform, 'machine', return_value='x86_64'), \
                    patch.object(provision.urllib.request, 'urlopen', return_value=io.BytesIO(b'wrong bytes')):
                with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                    provision.provision(['marksman'], catalog, prefix, True)
            self.assertFalse((prefix / 'bin/marksman').exists())

    def test_existing_installation_migrates_and_restores_to_the_former_checkout(self):
        for client in profiles.CLIENTS:
            if client == 'codex' and not shutil.which('codex'):
                continue
            with self.subTest(client=client), tempfile.TemporaryDirectory(prefix='sage upgrade ') as tmp:
                home = Path(tmp)
                target = home / {'codex': '.codex', 'opencode': '.config/opencode', 'antigravity': '.gemini/config'}[client]
                skill_dir = home / '.agents/skills' if client == 'codex' else target / 'skills'
                skill_dir.mkdir(parents=True)
                old = home / 'old standalone' / 'ponytail'
                old.mkdir(parents=True)
                (old / 'SKILL.md').write_text('Previous contents')
                link = skill_dir / 'ponytail'
                link.symlink_to(old)
                latest = target / 'sage/latest.json'
                latest.parent.mkdir(parents=True)
                latest.write_text(json.dumps({str(link): client_state.fingerprint(client_state.snapshot(link))}))
                installed_config = target / {'codex': 'config.toml', 'opencode': 'opencode.json', 'antigravity': 'mcp_config.json'}[client]
                original = 'model_reasoning_effort = "high"\n' if client == 'codex' else '{"mcpServers":{}}\n' if client == 'antigravity' else '{"model":"keep/my-model"}\n'
                installed_config.write_text(original)
                cli = [sys.executable, ROOT / 'sage.py', 'install', client, '--home', home]
                subprocess.run(cli + ['--dry-run'], check=True, capture_output=True)
                self.assertEqual(link.resolve(), old)
                self.assertFalse((target / 'sage/backups').exists())
                subprocess.run(cli, check=True, capture_output=True)
                catalog = target / 'skills-catalog'
                self.assertTrue((link / 'SKILL.md').samefile(ROOT / 'library/skills/ponytail/SKILL.md'))
                self.assertTrue((catalog / 'workflow-graph/SKILL.md').samefile(ROOT / 'library/skills/workflow-graph/SKILL.md'))
                self.assertFalse((skill_dir / 'workflow-graph').exists())
                self.assertEqual(len(list(catalog.glob('*/SKILL.md'))), len(profiles.profile(client)['catalog']))
                if client in ('antigravity', 'codex'):
                    hook = target / ('plugins/sage-skill-router/route_skills.py' if client == 'antigravity' else 'sage/route_skills.py')
                    project = home / 'project'
                    project.mkdir()
                    (project / 'example.dot').write_text('digraph { a -> b }')
                    reply = subprocess.run([sys.executable, hook, '--client', client], check=True, capture_output=True,
                                           text=True, input=json.dumps({'cwd': str(project), 'session_id': 'test'}),
                                           env={**os.environ, 'SAGE_ROUTER_CATALOG': str(catalog)})
                    self.assertIn(str(catalog / 'workflow-graph/SKILL.md'), reply.stdout)
                journal, = (target / 'sage/backups').glob('*.json')
                subprocess.run([sys.executable, ROOT / 'sage.py', 'restore', journal], check=True, capture_output=True)
                self.assertEqual(link.resolve(), old)
                self.assertEqual(installed_config.read_text(), original)
                self.assertFalse((catalog / 'workflow-graph').is_symlink())


if __name__ == '__main__':
    unittest.main()
