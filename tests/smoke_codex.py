#!/usr/bin/env python3
"""Exercise installation, native parsing/discovery, and restore without a model call."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clients.codex import installer as harness


async def skill_catalog(binary, env, cwd):
    proc = await asyncio.create_subprocess_exec(binary, 'app-server', '--stdio', cwd=cwd, env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    async def request(identifier, method, params):
        proc.stdin.write((json.dumps({'id': identifier, 'method': method, 'params': params}) + '\n').encode())
        await proc.stdin.drain()
        while True:
            line = await proc.stdout.readline()
            if not line:
                raise RuntimeError('Native skill catalog exited before responding')
            reply = json.loads(line)
            if reply.get('id') == identifier:
                if 'error' in reply:
                    raise RuntimeError(str(reply['error']))
                return reply['result']
    try:
        await asyncio.wait_for(request(1, 'initialize', {'clientInfo': {'name': 'sage-smoke', 'version': '1'}}), 30)
        result = await asyncio.wait_for(request(2, 'skills/list', {'cwds': [str(cwd)], 'forceReload': True}), 30)
        return {s['name']: s for entry in result['data'] for s in entry['skills']}
    finally:
        proc.stdin.close()
        try:
            await asyncio.wait_for(proc.wait(), 3)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()


def main():
    binary = shutil.which("codex")
    if not binary:
        raise SystemExit("Codex CLI is required for the native smoke test")
    with tempfile.TemporaryDirectory(prefix="sage-codex-smoke-") as temp, patch.dict(os.environ, {
        'HOME': temp, 'XDG_CONFIG_HOME': str(Path(temp) / '.config'), 'XDG_CACHE_HOME': str(Path(temp) / 'cache'),
        'XDG_DATA_HOME': str(Path(temp) / 'data'), 'XDG_STATE_HOME': str(Path(temp) / 'state'),
    }):
        root = Path(temp)
        args = argparse.Namespace(codex_home=root / "codex", skills_dir=root / ".agents/skills",
                                  bin_dir=root / "bin", mcp=list(harness.mcp_templates()),
                                  with_hybrid=None, disable_mcp=['hybrid-sage'], dry_run=False, native=True)
        personal = args.codex_home / 'agents/personal-reader.toml'
        personal.parent.mkdir(parents=True)
        personal.write_text('name = "personal-reader"\ndescription = "Read a fixture"\ndeveloper_instructions = "Inspect the fixture."\n')
        backup = harness.install(args)
        try:
            harness.doctor(args)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            env = {**os.environ, "CODEX_HOME": str(args.codex_home)}
            command = [binary, "debug", "prompt-input"]
            result = subprocess.run(command, cwd=root, env=env, capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError(result.stderr)
            json.loads(result.stdout)
            for name in ('ponytail', 'sage-design', 'token-efficiency', 'sage-review'):
                assert name in result.stdout, f"Native core skill discovery failed: {name}"
            assert "personal-reader" in result.stdout, "Native personal agent discovery failed"
            assert list(personal.parent.iterdir()) == [personal]
            assert not (args.skills_dir / "sage-genomics").exists(), "Catalog skill should be lazy-routed by default"
            assert (args.codex_home / "skills-catalog/sage-genomics/SKILL.md").is_file(), "Catalog skill missing"
            (root / "main.nf").write_text("nextflow.enable.dsl=2\n")
            hook_proc = subprocess.run(
                ["python3", str(args.codex_home / "sage/route_skills.py"), "--client", "codex"],
                input=json.dumps({"cwd": str(root), "session_id": "smoke", "hook_event_name": "SessionStart"}),
                capture_output=True, text=True, check=True, timeout=15,
            )
            assert "sage-genomics" in hook_proc.stdout, f"Skill router failed on .nf workspace: {hook_proc.stdout}"
            hooks = json.loads((args.codex_home / "hooks.json").read_text())['hooks']
            prompt_command = hooks['UserPromptSubmit'][-1]['hooks'][0]['command']
            prompt = {'cwd': str(root), 'session_id': 'smoke', 'hook_event_name': 'UserPromptSubmit',
                      'prompt': 'Stress-test this plan.'}
            result = subprocess.run(shlex.split(prompt_command), input=json.dumps(prompt),
                                    capture_output=True, text=True, check=True, timeout=15)
            output = json.loads(result.stdout)['hookSpecificOutput']
            assert output['hookEventName'] == 'UserPromptSubmit'
            assert '`red-team`' in output['additionalContext'] and 'grill-with-docs' not in output['additionalContext']
            print("Lazy core + catalog routing validated without activating all catalog skills.")
        finally:
            harness.restore(backup)

        full_args = argparse.Namespace(**vars(args), all_skills=True)
        backup = harness.install(full_args)
        try:
            harness.doctor(full_args)
            env = {**os.environ, "CODEX_HOME": str(full_args.codex_home)}
            result = subprocess.run([binary, "debug", "prompt-input"], cwd=root, env=env, capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError(result.stderr)
            json.loads(result.stdout)
            assert "sage-genomics" in result.stdout, "Native skill discovery failed"
            for name in ('ponytail', 'grilling', 'domain-modeling', 'sage-mcp-builder', 'token-efficiency',
                         'variant-analysis', 'differential-review', 'vercel-react-best-practices'):
                assert name in result.stdout, f"Native skill discovery failed: {name}"
            catalog = asyncio.run(skill_catalog(binary, env, root))
            graph_skill = catalog.get('workflow-graph', {})
            assert graph_skill.get('enabled'), 'Shared workflow graph skill missing from native discovery'
            assert Path(graph_skill['path']).resolve() == (harness.LIBRARY / 'skills/workflow-graph/SKILL.md').resolve()
            assert catalog.get('grill-with-docs', {}).get('enabled'), 'Explicit grill-with-docs skill missing from native selector'
            assert 'grill-me' not in catalog, 'Retired grill-me skill remains installed'
            print('Native selector discovers original explicit-only grill-with-docs and both full dependencies.')
            print("Ordinary Codex discovered the installed skills and the personal agent.")
            result = subprocess.run([binary, "app-server", "--strict-config", "--print-startup-config"],
                                    env=env,
                                    capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError(result.stderr)
            json.loads(result.stdout)
            print("Native Codex accepted the passive configuration with strict validation.")
        finally:
            harness.restore(backup)
    print("Native smoke test passed; no model requests were made.")


if __name__ == "__main__":
    main()
