import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
from library.runtime.skill_router import route_skills


class SkillRoutingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='sage-router-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.catalog = self.root / 'skills-catalog'
        self.catalog.mkdir()
        for name in ('nextflow', 'fair-data', 'pdf-edit'):
            skill = self.catalog / name
            skill.mkdir()
            (skill / 'SKILL.md').write_text(f'# {name}\n')
        self.routing = {
            'version': 1,
            'core': ['agentic-coding'],
            'rules': [
                {
                    'skill': 'nextflow',
                    'category': 'bio',
                    'summary': 'Nextflow workflows',
                    'files': ['*.nf'],
                    'deps': ['nextflow'],
                    'patterns': ['\\bnextflow\\b'],
                    'companions': ['fair-data'],
                },
                {
                    'skill': 'fair-data',
                    'category': 'science',
                    'summary': 'FAIR metadata',
                    'patterns': ['\\bfair data\\b'],
                },
                {
                    'skill': 'pdf-edit',
                    'category': 'docs',
                    'summary': 'PDF editing',
                    'patterns': ['\\bpdf\\b'],
                },
            ],
        }
        (self.catalog / 'routing.json').write_text(json.dumps(self.routing))

    def test_routes_workspace_companions_and_dedups_per_conversation(self):
        workspace = self.root / 'proj'
        workspace.mkdir()
        (workspace / 'main.nf').write_text('nextflow.enable.dsl=2\n')
        fake_script = self.root / 'plugins/sage-skill-router/route_skills.py'
        fake_script.parent.mkdir(parents=True)
        fake_script.write_text('#!/usr/bin/env python3\n')

        first = route_skills.route_hook(
            {'common': {'workspacePaths': [str(workspace)], 'conversationId': 'conv-1', 'lastUserInput': ''}},
            'antigravity',
            False,
            fake_script,
        )
        msg1 = first['injectSteps'][0]['systemMessage']['systemMessage']
        self.assertIn('nextflow', msg1)
        self.assertIn('fair-data', msg1)
        self.assertIn('[SAGE On-Demand Catalog]', msg1)

        repeat = route_skills.route_hook(
            {'common': {'workspacePaths': [str(workspace)], 'conversationId': 'conv-1', 'lastUserInput': 'check log'}},
            'antigravity',
            True,
            fake_script,
        )
        self.assertEqual(repeat, {})

        second = route_skills.route_hook(
            {'common': {'workspacePaths': [str(workspace)], 'conversationId': 'conv-1', 'lastUserInput': 'redact this pdf'}},
            'antigravity',
            True,
            fake_script,
        )
        msg2 = second['injectSteps'][0]['systemMessage']['systemMessage']
        self.assertIn('pdf-edit', msg2)
        self.assertNotIn('nextflow', msg2)
        self.assertNotIn('[SAGE On-Demand Catalog]', msg2)

    def test_symlinked_antigravity_plugin_resolves_target_catalog(self):
        repo_plugin = self.root / 'repo/plugins/sage-skill-router'
        repo_plugin.mkdir(parents=True)
        real_script = repo_plugin / 'route_skills.py'
        real_script.write_text('#!/usr/bin/env python3\n')
        target_plugins = self.root / 'plugins'
        target_plugins.mkdir(exist_ok=True)
        (target_plugins / 'sage-skill-router').symlink_to(repo_plugin)
        symlinked_script = target_plugins / 'sage-skill-router/route_skills.py'
        out = route_skills.route_hook(
            {'common': {'workspacePaths': [], 'conversationId': 'sym-1', 'lastUserInput': 'redact pdf'}},
            'antigravity',
            False,
            symlinked_script,
        )
        msg = out['injectSteps'][0]['systemMessage']['systemMessage']
        self.assertIn('pdf-edit', msg)

    def test_codex_hook_output_format(self):
        fake_script = self.root / 'sage/route_skills.py'
        fake_script.parent.mkdir(parents=True)
        fake_script.write_text('#!/usr/bin/env python3\n')
        out = route_skills.route_hook(
            {'cwd': str(self.root), 'session_id': 'codex-1', 'hook_event_name': 'SessionStart', 'prompt': 'redact pdf'},
            'codex',
            False,
            fake_script,
        )
        hook_out = out['hookSpecificOutput']
        self.assertEqual(hook_out['hookEventName'], 'SessionStart')
        self.assertIn('pdf-edit', hook_out['additionalContext'])

    def test_codex_prompt_hook_respects_disabled_skill_and_companion(self):
        fake = self.root / 'sage/route_skills.py'
        (self.root / 'config.toml').write_text(
            '[[skills.config]]\nname="pdf-edit"\nenabled=false\n'
            f'[[skills.config]]\npath="{self.catalog}/fair-data/SKILL.md"\nenabled=false\n')
        payload = {'session_id': 'codex-2', 'hook_event_name': 'UserPromptSubmit', 'prompt': 'Nextflow and PDF'}
        result = route_skills.route_hook(payload, 'codex', True, fake)['hookSpecificOutput']
        self.assertEqual(result['hookEventName'], 'UserPromptSubmit')
        self.assertIn('nextflow', result['additionalContext'])
        self.assertNotIn('pdf-edit', result['additionalContext'])
        self.assertNotIn('fair-data', result['additionalContext'])

    def test_compaction_restores_last_prompt_skill_and_clear_starts_fresh(self):
        payload = {'session_id': 'continues', 'hook_event_name': 'UserPromptSubmit',
                   'cwd': str(self.root), 'turn_id': 't1', 'prompt': 'redact this PDF'}
        script = self.root / 'sage/route_skills.py'
        self.assertIn('pdf-edit', route_skills.route_hook(payload, 'codex', True, script)['hookSpecificOutput']['additionalContext'])
        self.assertEqual(route_skills.route_hook(payload, 'codex', True, script), {})
        before_compact = {'session_id': 'continues', 'hook_event_name': 'SessionStart', 'cwd': str(self.root)}
        resumed = route_skills.route_hook({**before_compact, 'source': 'compact'}, 'codex', False, script)
        self.assertIn('pdf-edit', resumed['hookSpecificOutput']['additionalContext'])
        cleared = route_skills.route_hook({**before_compact, 'source': 'clear'}, 'codex', False, script)
        self.assertNotIn('pdf-edit', cleared['hookSpecificOutput']['additionalContext'])

    def test_explicit_skill_can_be_requested_again_on_a_new_turn(self):
        self.routing['rules'][-1]['requests'] = [r'^\$pdf-edit$']
        (self.catalog / 'routing.json').write_text(json.dumps(self.routing))
        payload = {'session_id': 'reissue', 'hook_event_name': 'UserPromptSubmit',
                   'prompt': '$pdf-edit', 'turn_id': 'a'}
        script = self.root / 'sage/route_skills.py'
        first = route_skills.route_hook(payload, 'codex', True, script)
        self.assertIn('pdf-edit', first['hookSpecificOutput']['additionalContext'])
        self.assertEqual(route_skills.route_hook(payload, 'codex', True, script), {})
        second = route_skills.route_hook({**payload, 'turn_id': 'b'}, 'codex', True, script)
        self.assertIn('pdf-edit', second['hookSpecificOutput']['additionalContext'])

    def test_prompt_detects_workspace_changes_in_the_same_conversation(self):
        first, second = self.root / 'first', self.root / 'second'
        first.mkdir()
        second.mkdir()
        (second / 'main.nf').touch()
        hook = self.root / 'plugins/sage-skill-router/route_skills.py'
        payload = {'common': {'conversationId': 'moves', 'workspacePaths': [str(first)]}}
        route_skills.route_hook(payload, 'antigravity', True, hook)
        payload['common']['workspacePaths'] = [str(second)]
        output = route_skills.route_hook(payload, 'antigravity', True, hook)
        self.assertIn('nextflow', output['injectSteps'][0]['systemMessage']['systemMessage'])

    def test_workspace_scan_bounds_and_ignores_symlink_targets(self):
        workspace, unrelated = self.root / 'work', self.root / 'unrelated'
        workspace.mkdir()
        unrelated.mkdir()
        (unrelated / 'external.nf').touch()
        (workspace / 'linked').symlink_to(unrelated)
        manifest = unrelated / 'pyproject.toml'
        manifest.write_text('nextflow\n')
        link = workspace / 'pyproject.toml'
        link.symlink_to(manifest)
        self.assertEqual(route_skills.match_workspace([workspace], self.routing['rules']), [])
        link.unlink()
        link.write_text(' ' * 16384 + 'nextflow')
        self.assertEqual(route_skills.match_workspace([workspace], self.routing['rules']), [])
        link.write_text('nextflow')
        self.assertEqual(route_skills.match_workspace([workspace], self.routing['rules']), ['nextflow', 'fair-data'])


if __name__ == '__main__':
    unittest.main()
