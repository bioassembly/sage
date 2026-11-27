"""Offline discovery checks for installed OpenCode and Antigravity CLIs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from library import profiles


class NativeClientTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='sage native client ')
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.env = {
            'HOME': tmp.name, 'PATH': os.environ['PATH'], 'LANG': 'C.UTF-8',
            'XDG_CONFIG_HOME': str(self.home / '.config'), 'XDG_CACHE_HOME': str(self.home / 'cache'),
            'XDG_DATA_HOME': str(self.home / 'data'), 'XDG_STATE_HOME': str(self.home / 'state'),
            'HTTPS_PROXY': 'http://127.0.0.1:9', 'HTTP_PROXY': 'http://127.0.0.1:9',
            'NO_PROXY': 'localhost,127.0.0.1,::1', 'CI': '1', 'NO_COLOR': '1',
        }

    def invoke(self, *argv):
        result = subprocess.run(argv, cwd=self.home, env=self.env, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def activate(self, client, directory):
        self.invoke(sys.executable, profiles.ROOT / 'sage.py', 'install', client, '--home', self.home)
        target = self.home / directory
        journal, = (target / 'sage/backups').glob('*.json')
        restore = profiles.ROOT / 'sage.py'
        self.addCleanup(self.invoke, sys.executable, restore, 'restore', journal)
        return target

    @unittest.skipUnless(shutil.which('opencode'), 'OpenCode CLI is optional')
    def test_opencode_loads_native_tool_commands(self):
        target = self.home / '.config/opencode'
        target.mkdir(parents=True)
        personal = {'build': {'temperature': 0.61}, 'plan': {'top_p': 0.75}}
        (target / 'opencode.json').write_text(json.dumps({'agent': personal}))
        target = self.activate('opencode', '.config/opencode')
        self.env['OPENCODE_CONFIG_DIR'] = str(target)
        records = json.loads(self.invoke('opencode', 'debug', 'config', '--standalone'))
        path = target / 'opencode.json'
        info = next(doc['info'] for doc in records if doc.get('path') == str(path))
        source = profiles.read(path)
        self.assertEqual(source['agent'], personal)
        self.assertFalse((target / 'agent').exists())
        self.assertEqual(set(info['mcp']['servers']), set(source['mcp']))
        for name in profiles.profile('opencode')['lsp']:
            self.assertEqual(info['lsp'][name]['command'], source['lsp'][name]['command'])

    @unittest.skipUnless(shutil.which('agy'), 'Antigravity CLI is optional')
    def test_antigravity_discovers_servers_and_hook_with_native_agents_intact(self):
        personal = self.home / '.gemini/config/agents/personal-reader/agent.md'
        personal.parent.mkdir(parents=True)
        personal.write_text('---\nname: personal-reader\ndescription: Read a fixture\n---\nInspect the fixture.\n')
        before = self.invoke('agy', 'agents').splitlines()
        target = self.activate('antigravity', '.gemini/config')
        servers = self.invoke('agy', 'mcp', 'list')
        for name in profiles.profile('antigravity')['mcp']:
            self.assertRegex(servers, rf'(?m)^{name}\s')
        self.assertIn('sage-skill-router (enabled', self.invoke('agy', 'plugin', 'list'))
        self.assertEqual(self.invoke('agy', 'agents').splitlines(), before)
        self.assertEqual(list((target / 'agents').iterdir()), [personal.parent])


if __name__ == '__main__':
    unittest.main()
