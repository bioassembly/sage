"""Offline discovery checks for installed OpenCode and Antigravity CLIs."""
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import urlencode
from urllib.request import Request, urlopen

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

    @unittest.skipUnless(shutil.which('opencode'), 'OpenCode CLI is optional')
    def test_opencode_discovers_core_sources_and_workspace_skills(self):
        target = self.activate('opencode', '.config/opencode')
        self.env['OPENCODE_CONFIG_DIR'] = str(target)
        self.invoke('git', 'init', '-q', str(self.home))
        (self.home / 'main.nf').write_text('nextflow.enable.dsl=2\n')
        personal = self.home / '.opencode/skills/ponytail/SKILL.md'
        personal.parent.mkdir(parents=True)
        personal.write_text('---\nname: ponytail\ndescription: Personal fixture.\n---\nProject instructions.\n')
        self.env['OPENCODE_SERVER_PASSWORD'] = 'temporary-local-fixture'
        with socket.socket() as port_socket:
            port_socket.bind(('127.0.0.1', 0))
            port = port_socket.getsockname()[1]
        query = urlencode({'location[directory]': str(self.home)})
        auth = base64.b64encode(b'opencode:temporary-local-fixture').decode()
        request = Request(f'http://127.0.0.1:{port}/api/skill?{query}', headers={'Authorization': f'Basic {auth}'})
        expected = set(profiles.profile('opencode')['core']) | {'nextflow'}
        skills = {}
        with subprocess.Popen(['opencode', 'serve', '--hostname', '127.0.0.1', '--port', str(port)],
                              cwd=self.home, env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) as process:
            try:
                deadline = time.monotonic() + 35
                while process.poll() is None and time.monotonic() < deadline:
                    try:
                        with urlopen(request, timeout=2) as response:
                            skills = {skill['id']: skill for skill in json.load(response)['data']}
                        if expected <= skills.keys() and skills['ponytail']['description'] == 'Personal fixture.':
                            break
                    except OSError:
                        pass
                    time.sleep(.4)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
        self.assertLessEqual(expected, skills.keys())
        self.assertEqual(skills['ponytail']['description'], 'Personal fixture.')
        self.assertNotIn('sage-review', skills)

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
