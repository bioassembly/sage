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


if __name__ == '__main__':
    unittest.main()
