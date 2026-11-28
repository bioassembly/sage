#!/usr/bin/env python3
"""Install and inspect SAGE using only Python 3.11+ standard library."""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import tomllib
import uuid

CLIENT = Path(__file__).resolve().parent
ROOT = CLIENT.parents[1]
LIBRARY = ROOT / 'library'
sys.path.insert(0, str(ROOT))
from library import profiles
from library.scripts import agent_migration
from library.scripts.client_state import apply_state, file_state, fingerprint, merge_instructions, restore, snapshot

RETIRED_MCP_SERVERS = ("memory", "openai-docs", "playwright")


def read_toml(path: Path) -> dict:
    return tomllib.loads(path.read_text())


def merge_settings(current: dict, additions: dict) -> dict:
    if not isinstance(current, dict):
        raise ValueError("An existing scalar conflicts with a SAGE configuration table")
    merged = copy.deepcopy(current)
    for key, value in additions.items():
        if isinstance(value, dict):
            merged[key] = merge_settings(merged.get(key, {}), value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def respect_user_choices(settings: dict, current: dict) -> dict:
    """Defaults and MCP on/off switches never override explicit user choices."""
    result = copy.deepcopy(settings)

    def preserve(target: dict, defaults: dict, live: dict) -> None:
        for key, value in defaults.items():
            if key not in live:
                continue
            if isinstance(value, dict):
                if isinstance(live[key], dict) and isinstance(target.get(key), dict):
                    preserve(target[key], value, live[key])
            else:
                target[key] = copy.deepcopy(live[key])

    preserve(result, read_toml(CLIENT / 'defaults.toml'), current)
    for name, server in result.get('mcp_servers', {}).items():
        live = current.get('mcp_servers', {}).get(name)
        if isinstance(live, dict) and ('enabled' in live or 'enabled' in server):
            server['enabled'] = live.get('enabled', True)
    return result


def mcp_templates() -> dict:
    plan = profiles.profile('codex')
    servers = profiles.servers('codex', plan['mcp'] + plan['optional_mcp'], LIBRARY)
    return {name: {'mcp_servers': {name: body}} for name, body in servers.items()}


def migrated_skill_settings(live, previous, core_dir, catalog_dir, skill_links):
    entries = live.get('skills', {}).get('config', [])
    additions = []
    for destination, source in skill_links.items():
        name = destination.name
        new_file = destination / 'SKILL.md'
        new_source = source / 'SKILL.md'
        if any(e.get('name') == name or e.get('path') in (str(new_file), str(new_source)) for e in entries):
            continue
        candidates = [core_dir / name, catalog_dir / name]
        if name in ('checkpoint', 'token-efficiency'):
            candidates.append(core_dir / ('sage-' + name))
        old_links = [path for path in candidates if path != destination and path.is_symlink()
                     and previous.get(str(path)) == fingerprint(snapshot(path))]
        old_paths = {str(p) for link in old_links for p in (link / 'SKILL.md', link.resolve() / 'SKILL.md')}
        for entry in entries:
            if entry.get('enabled') is not False:
                continue
            if any(link.name != name and entry.get('name') == link.name for link in old_links):
                additions.append({'name': name, 'enabled': False})
                break
            if entry.get('path') in old_paths:
                additions.append({'path': str(new_source), 'enabled': False})
                break
    return {'skills': {'config': [*entries, *additions]}} if additions else {}


def stage_config(current: str, settings: dict, *, retire_agents=False, agents=None) -> str:
    """Use Codex's native TOML writer in isolation, before changing live files."""
    binary = shutil.which("codex")
    if not binary:
        raise ValueError("Codex CLI 0.169+ is required to merge configuration safely")
    edits = []

    def flatten(values: dict, prefix: str = "") -> None:
        for key, value in values.items():
            path = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                flatten(value, path)
            else:
                edits.append({"keyPath": path, "value": value, "mergeStrategy": "replace"})

    flatten(settings)
    expected = merge_settings(tomllib.loads(current), settings)
    if retire_agents:
        if agents is agent_migration.MISSING:
            # Removing the whole table in Codex also erases comments attached to its header.
            for key in ('enabled', 'max_concurrent_threads_per_session'):
                if key in expected['agents']:
                    edits.append({'keyPath': 'agents.' + key, 'value': None, 'mergeStrategy': 'replace'})
            expected.pop('agents')
        else:
            # The only scalar agent settings ever written by SAGE. Native edits preserve comments.
            for key in ('enabled', 'max_concurrent_threads_per_session'):
                if expected.get('agents', {}).get(key) != agents.get(key):
                    edits.append({'keyPath': 'agents.' + key, 'value': agents.get(key), 'mergeStrategy': 'replace'})
            expected['agents'] = agents

    async def write(staged: Path) -> None:
        proc = await asyncio.create_subprocess_exec(
            binary, "app-server", "--stdio", cwd=staged.parent,
            env={**os.environ, "CODEX_HOME": str(staged.parent)},
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL)

        async def request(identifier: int, method: str, params: dict) -> None:
            proc.stdin.write((json.dumps({"id": identifier, "method": method, "params": params}) + "\n").encode())
            await proc.stdin.drain()
            while True:
                line = await proc.stdout.readline()
                if not line:
                    raise ValueError("Codex config writer exited before returning a result")
                result = json.loads(line)
                if result.get("id") == identifier:
                    if "error" in result:
                        raise ValueError("Codex rejected the staged configuration update")
                    return

        try:
            await asyncio.wait_for(request(1, "initialize", {
                "clientInfo": {"name": "sage-installer", "version": "1"}}), timeout=30)
            await asyncio.wait_for(request(2, "config/batchWrite", {
                "filePath": str(staged), "edits": edits, "reloadUserConfig": False}), timeout=30)
        finally:
            proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), timeout=3)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()

    with tempfile.TemporaryDirectory(prefix="sage-config-") as temp:
        staged = Path(temp) / "config.toml"
        staged.write_text(current)
        try:
            asyncio.run(write(staged))
        except TimeoutError as error:
            raise ValueError("Codex's native config writer timed out; live configuration was not changed") from error
        output = staged.read_text()
    if retire_agents and agents is agent_migration.MISSING and tomllib.loads(output).get('agents') == {}:
        # Drop just the now-empty table marker. Validate the edit against the full parse
        # so a lookalike header in a multiline TOML string can never be removed.
        key = r"""(?:agents|"agents"|'agents')"""
        header = rf'(?m)^[ \t]*(?:\[[ \t]*{key}[ \t]*\]|{key}[ \t]*=[ \t]*\{{[ \t]*\}})[ \t]*(?P<comment>#[^\n]*)?$'
        for match in re.finditer(header, output):
            candidate = output[:match.start()] + (match['comment'] or '') + output[match.end():]
            if tomllib.loads(candidate) == expected:
                output = candidate
                break
    if tomllib.loads(output) != expected:
        raise ValueError("Native config merge changed an unrelated setting; installation stopped")
    return output


def is_router_hook(item, router_path: Path) -> bool:
    if not isinstance(item, dict) or item.get('type') != 'command' or not isinstance(item.get('command'), str):
        return False
    try:
        parts = shlex.split(item['command'])
    except ValueError:
        return False
    return (len(parts) >= 4 and Path(parts[0]).name == 'python3' and parts[1] == str(router_path)
            and parts[2:] in (['--client', 'codex'], ['--client', 'codex', '--prompt']))


def merge_router_hooks(hooks_path: Path, enable: bool) -> dict | None:
    if hooks_path.exists():
        data = json.loads(hooks_path.read_text())
        if not isinstance(data, dict):
            raise ValueError(f'Invalid hooks.json object: {hooks_path}')
    elif enable:
        data = {}
    else:
        return None
    hooks = data.setdefault('hooks', {})
    if not isinstance(hooks, dict):
        raise ValueError(f'Invalid hooks section in {hooks_path}')
    router = hooks_path.parent / 'sage/route_skills.py'
    for event, flags in (('SessionStart', []), ('UserPromptSubmit', ['--prompt'])):
        groups = hooks.get(event, [])
        if not isinstance(groups, list):
            raise ValueError(f'Invalid {event} hooks list in {hooks_path}')
        kept = []
        registered = False
        command = shlex.join(['python3', str(router), '--client', 'codex', *flags])
        for group in groups:
            items = group.get('hooks') if isinstance(group, dict) else None
            if not isinstance(items, list) or not items:
                kept.append(group)
                continue
            retained = []
            for item in items:
                if not is_router_hook(item, router):
                    retained.append(item)
                elif enable and not registered:
                    retained.append({**item, 'command': command})
                    registered = True
            if retained:
                kept.append({**group, 'hooks': retained})
        if enable and not registered:
            kept.append({'hooks': [{'type': 'command', 'command': command}]})
        if kept or (event in hooks and not groups):
            hooks[event] = kept
        else:
            hooks.pop(event, None)
    return file_state(json.dumps(data, indent=2) + "\n")


def check() -> None:
    profiles.validate(['codex'])
    read_toml(CLIENT / 'defaults.toml')
    subprocess.run([sys.executable, str(LIBRARY / 'scripts/validate-skills.py')], check=True,
                   stdout=subprocess.DEVNULL)


def install(args: argparse.Namespace) -> Path | None:
    check()
    codex_home = args.codex_home.resolve()
    config = codex_home / "config.toml"
    config_before = snapshot(config)
    live_config = read_toml(config) if config.exists() else {}
    managed_path = codex_home / "sage/managed-config.json"
    settings = json.loads(managed_path.read_text()) if managed_path.exists() else {}
    latest = codex_home / "sage/latest.json"
    previous = json.loads(latest.read_text()) if latest.exists() else {}
    old_agent_settings = settings.pop('agents', None)
    roles = {name for name in previous if agent_migration.owned_path(Path(name), codex_home)}
    history = agent_migration.active_history(latest, roles | {str(config)}) if roles or old_agent_settings else []
    previous_managed = copy.deepcopy(settings.get("mcp_servers", {}))
    templates = mcp_templates()
    selection_path = codex_home / 'sage/mcp-selection.json'
    prior_selection = json.loads(selection_path.read_text()) if selection_path.is_file() else {}
    if prior_selection:
        explicit = set(prior_selection['explicit'])
    else:
        # Earlier Codex installations shipped every registered template as an opt-in.
        explicit = {name for name in templates if {'url', 'command'} & previous_managed.get(name, {}).keys()}
    explicit = (explicit | set(args.mcp)) & templates.keys()
    selected = explicit | set(profiles.profile("codex")["mcp"])
    settings = merge_settings(settings, read_toml(CLIENT / 'defaults.toml'))
    for name in sorted(selected):
        template = copy.deepcopy(templates[name])
        if name == 'memory':
            template['mcp_servers']['memory']['env']['MEMORY_FILE_PATH'] = str(codex_home / 'sage/memory.json')
        settings = merge_settings(settings, template)
    if args.with_hybrid:
        server = args.with_hybrid.resolve() / "plugins/mcp_server.py"
        if not server.is_file():
            raise ValueError(f"Hybrid SAGE server missing: {server}")
        settings = merge_settings(settings, {'mcp_servers': {'hybrid-sage': {
            'command': sys.executable, 'args': [str(server)]}}})
    settings = respect_user_choices(settings, live_config)
    library_servers = profiles.read(profiles.ROOT / 'library/mcp/servers.json')
    known = set(prior_selection.get('selected', [])) | library_servers.keys()
    retired = (set(previous_managed) & known) - selected
    for name in retired | (set(RETIRED_MCP_SERVERS) - selected):
        if name not in previous_managed:
            continue
        live = live_config.get('mcp_servers', {}).get(name)
        if not isinstance(live, dict):
            settings.get('mcp_servers', {}).pop(name, None)
            continue
        prev_body = {k: v for k, v in previous_managed[name].items() if k != 'enabled'}
        live_body = {k: v for k, v in live.items() if k != 'enabled'}
        if live_body == prev_body:
            settings.setdefault('mcp_servers', {}).setdefault(name, {})['enabled'] = False
        else:
            settings.get('mcp_servers', {}).pop(name, None)
    for name in getattr(args, 'disable_mcp', []):
        server_id = next(iter(templates[name]['mcp_servers'])) if name in templates else name
        if server_id in settings.get('mcp_servers', {}) or server_id in live_config.get('mcp_servers', {}):
            settings.setdefault('mcp_servers', {}).setdefault(server_id, {})['enabled'] = False
    global_agents = codex_home / "AGENTS.md"
    current = global_agents.read_text() if global_agents.exists() else ""
    for marker in ('start', 'end'):
        current = current.replace(f'<!-- codex-sage:{marker} -->', f'<!-- sage-harness:{marker} -->')
    all_skills = getattr(args, 'all_skills', False)
    plan = profiles.profile('codex')
    core_dir = args.skills_dir.resolve()
    catalog_dir = codex_home / 'skills-catalog'
    local = CLIENT / 'skills.local'
    overlays = {p.parent.name: p.parent for p in local.glob('*/SKILL.md')}
    skill_links = {}
    for name in sorted(set(plan['core'] + plan['catalog']) | overlays.keys()):
        skill = overlays.get(name, LIBRARY / 'skills' / name)
        directory = core_dir if all_skills or name in plan['core'] or name in overlays else catalog_dir
        dest = directory / name
        if dest.is_symlink() and dest.resolve() != skill.resolve() and previous.get(str(dest)) != fingerprint(snapshot(dest)):
            raise ValueError(f'Personal skill link preserved: {dest}')
        skill_links[dest] = skill
    config_text = config.read_text() if config.exists() else ''
    config_settings = {**settings, **migrated_skill_settings(live_config, previous, core_dir, catalog_dir, skill_links)}
    if old_agent_settings and history and 'agents' in live_config:
        agents = agent_migration.original_section(config, 'agents', live_config['agents'], history, tomllib.loads)
        staged = stage_config(config_text, config_settings, retire_agents=True, agents=agents)
    else:
        staged = stage_config(config_text, config_settings)
    plans = {
        config: file_state(staged),
        selection_path: file_state(json.dumps({'explicit': sorted(explicit), 'selected': sorted(selected)}) + "\n"),
        codex_home / "sage/managed-config.json": file_state(json.dumps(settings, indent=2) + "\n"),
        global_agents: file_state(merge_instructions(current, (LIBRARY / "guidance.md").read_text())),
    }
    plans.update({dest: {'kind': 'symlink', 'target': str(skill)} for dest, skill in skill_links.items()})
    routing = None if all_skills else profiles.routing(plan, LIBRARY)
    if routing is not None:
        plans[codex_home / "skills-catalog/routing.json"] = file_state(json.dumps(routing, indent=2) + "\n", 0o644)
        router_dest = codex_home / "sage/route_skills.py"
        plans[router_dest] = file_state((LIBRARY / "runtime/skill_router/route_skills.py").read_text(), 0o755)
    hook_state = merge_router_hooks(codex_home / "hooks.json", enable=routing is not None)
    if hook_state is not None:
        plans[codex_home / "hooks.json"] = hook_state
    hybrid_state = settings.get('mcp_servers', {}).get('hybrid-sage',
                        live_config.get('mcp_servers', {}).get('hybrid-sage'))
    hybrid_enabled = hybrid_state is not None and hybrid_state.get('enabled', True)
    if args.with_hybrid and hybrid_enabled:
        for name in ('model-router', 'sage'):
            skill = args.with_hybrid.resolve() / 'skills' / name
            if not (skill / 'SKILL.md').is_file():
                raise ValueError(f"Hybrid SAGE skill missing; update the checkout: {skill}")
            plans[args.skills_dir.resolve() / name] = {'kind': 'symlink', 'target': str(skill)}
    released = set()
    for name, installed_hash in previous.items():
        path = Path(name)
        if not any(path.is_relative_to(directory) for directory in (codex_home, args.skills_dir.resolve(), args.bin_dir.resolve())):
            continue
        if path.is_dir() and not path.is_symlink():
            continue
        if (hybrid_enabled and path.parent == args.skills_dir.resolve()
                and path.name in ('sage', 'model-router') and path not in plans
                and fingerprint(snapshot(path)) == installed_hash):
            plans[path] = snapshot(path)
        if path not in plans and fingerprint(snapshot(path)) == installed_hash:
            if agent_migration.owned_path(path, codex_home):
                live = snapshot(path)
                original = agent_migration.previous_file(path, live, history)
                if original is not None and original != live:
                    plans[path] = original
                    released.add(path)
            else:
                plans[path] = {"kind": "absent"}
    if snapshot(config) != config_before:
        raise ValueError("config.toml changed while staging; retry with the updated configuration")
    entries = [{"path": str(p), "before": snapshot(p), "after": state} for p, state in plans.items()]
    if args.dry_run:
        for entry in entries:
            action = 'remove' if entry['after']['kind'] == 'absent' else 'install'
            print(f"Would {action}: {entry['path']}")
        return None
    # Save the journal before any installed file changes. No auth files are read.
    entries.append({"path": str(latest), "before": snapshot(latest), "after": file_state(json.dumps({
        str(p): fingerprint(state) for p, state in plans.items() if state["kind"] != "absent" and p != config and p not in released
    }, indent=2) + "\n")})
    backup_dir = codex_home / "sage/backups"
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    backup = backup_dir / f"{uuid.uuid4().hex}.json"
    apply_state(backup, file_state(json.dumps({"entries": entries}, indent=2) + "\n"))
    applied = []
    try:
        for entry in entries:
            apply_state(Path(entry["path"]), entry["after"])
            applied.append(entry)
    except Exception:
        for entry in reversed(applied):
            apply_state(Path(entry["path"]), entry["before"])
        raise
    print(f"Installed {len(plans)} entries. Restart Codex to discover the skills.")
    print(f"Restore with python3 {shlex.quote(str(ROOT / 'sage.py'))} restore {shlex.quote(str(backup))}")
    return backup


def doctor(args: argparse.Namespace) -> None:
    check()
    home = args.codex_home.resolve()
    config = read_toml(home / "config.toml")
    managed = json.loads((home / "sage/managed-config.json").read_text())
    if merge_settings(config, respect_user_choices(managed, config)) != config:
        raise ValueError("SAGE settings changed in config.toml; review the passive configuration")
    latest = json.loads((home / "sage/latest.json").read_text())
    drift = [p for p, digest in latest.items() if fingerprint(snapshot(Path(p))) != digest]
    if drift:
        raise ValueError("Installed entries changed or missing: " + ", ".join(drift))
    for directory in (args.skills_dir.resolve(), home / "skills-catalog"):
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if path.is_symlink() and not path.exists():
                raise ValueError(f"Broken skill link: {path}")
    active_skills = sum(1 for p in args.skills_dir.resolve().iterdir() if (p / "SKILL.md").is_file()) if args.skills_dir.exists() else 0
    catalog_dir = home / "skills-catalog"
    catalog_skills = sum(1 for p in catalog_dir.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()) if catalog_dir.exists() else 0
    if (home / "AGENTS.override.md").exists():
        print("Notice: AGENTS.override.md takes precedence over the installed global AGENTS.md.")
    servers = config.get('mcp_servers', {})
    enabled = [name for name in managed.get('mcp_servers', {}) if servers.get(name, {}).get('enabled', True)]
    disabled = [name for name in servers if not servers[name].get('enabled', True)]
    print(f"Installation intact. Active skills: {active_skills}; catalog skills: {catalog_skills}")
    print(f"Enabled SAGE MCP servers: {', '.join(enabled) or 'none'}")
    print(f"Disabled MCP servers: {', '.join(disabled) or 'none'}")
    if args.native:
        binary = shutil.which("codex")
        if not binary:
            raise ValueError("Codex CLI not found on PATH")
        result = subprocess.run([binary, "mcp", "list", "--json"],
                                env={**os.environ, "CODEX_HOME": str(home)}, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise ValueError("Native config validation failed; run codex mcp list")
        print("Ordinary Codex loaded the passive MCP configuration.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="Validate repository assets without installing")
    for name in ("install", "doctor"):
        command = sub.add_parser(name)
        command.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))))
        command.add_argument("--skills-dir", type=Path, default=Path.home() / ".agents/skills")
        if name == "install":
            command.add_argument("--bin-dir", type=Path, default=Path.home() / ".local/bin")
            command.add_argument("--mcp", action="append", choices=sorted(mcp_templates()), default=[])
            command.add_argument("--disable-mcp", action="append", choices=sorted(mcp_templates()) + ['hybrid-sage'], default=[],
                                 help="Keep a registered server disabled; harmless when absent")
            command.add_argument("--with-hybrid", type=Path, metavar="REPO", help="Register a local hybrid-sage checkout")
            command.add_argument("--all-skills", action="store_true", help="Install all catalog skills directly instead of lazy routing")
            command.add_argument("--dry-run", action="store_true")
        else:
            command.add_argument("--native", action="store_true", help="Also ask ordinary Codex to validate its configuration")
    sub.add_parser("restore").add_argument("backup", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "install":
            install(args)
        elif args.command == "restore":
            restore(args.backup)
        elif args.command == "doctor":
            doctor(args)
        else:
            check()
    except (OSError, ValueError, KeyError, TimeoutError, subprocess.SubprocessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
