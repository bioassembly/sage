#!/usr/bin/env python3
"""Install shared SAGE capabilities in a native client, with rollback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import uuid
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from library import profiles
from library.lsp.provision import native_command
from library.scripts import agent_migration, client_state as harness, merge_config


def install(root, user_home, client, key=None, base_url=None, with_rea=False, disable_hybrid=True, dry_run=False,
            all_skills=False, extra_mcp=()):
    root, user_home = root.resolve(), user_home.resolve()
    source = root / 'clients' / client
    library = root / 'library'
    plan = profiles.profile(client, root)
    target = user_home / ('.config/opencode' if client == 'opencode' else '.gemini/config')
    config_name = 'opencode.json' if client == 'opencode' else 'mcp_config.json'
    config = target / config_name
    before_config = harness.snapshot(config)
    # Antigravity creates an empty MCP file on the first native CLI invocation.
    content = config.read_text() if config.exists() else ''
    current = json.loads(content) if content.strip() else {}
    routing = None if all_skills else profiles.routing(plan, library)
    public = {name: library / 'skills' / name for name in plan['core'] + plan['catalog']}
    local = {p.parent.name: p.parent.resolve() for p in (source / 'skills.local').glob('*/SKILL.md')}
    core_names = set(public if all_skills else plan['core']) | local.keys()
    replacements = {'__UNSLOTH_API_KEY__': key or 'local-opencode', '__BASE_URL__': base_url or 'http://127.0.0.1:8080/v1',
                    '__MEMORY_PATH__': str(target / 'memory.json')}
    template = profiles.native_config(client, plan, root)
    if client == 'opencode' and (key is not None or base_url is not None):
        template.update(merge_config.render(profiles.read(source / 'local-provider.json'), replacements))
    if client == 'opencode' and isinstance(template.get('lsp'), dict):
        for entry in template['lsp'].values():
            if 'command' in entry:
                entry['command'] = native_command(entry['command'])
    state = target / 'sage/source-template.json'
    latest = target / 'sage/latest.json'
    previous_files = json.loads(latest.read_text()) if latest.exists() else {}
    previous = json.loads((state if state.exists() else source / 'migration/legacy-mcp.json').read_text().replace('${HOME}', str(user_home)))
    previous = merge_config.render(previous, replacements)
    remembered = set(previous.get('explicit_mcp', [])) & set(plan['optional_mcp'] + plan['mcp'])
    requested = remembered | set(extra_mcp) | ({'rea'} if with_rea else set())
    if requested:
        available = profiles.read(library / 'mcp/servers.json')
        profiles.selected(sorted(requested), plan['mcp'] + plan['optional_mcp'], 'requested MCP')
        table = template.setdefault('mcp' if client == 'opencode' else 'mcpServers', {})
        for name in sorted(requested):
            table[name] = profiles.native_mcp(client, available[name])
    roles = {path for path in previous_files if agent_migration.owned_path(Path(path), target)}
    history = agent_migration.active_history(latest, roles | {str(config)}) if roles else []
    if client == 'opencode' and history and 'agent' in current:
        restored = agent_migration.original_section(config, 'agent', current['agent'], history, json.loads)
        if restored is agent_migration.MISSING:
            del current['agent']
        else:
            current['agent'] = restored
    settings = merge_config.merge(template, current, previous, client, disable_hybrid)
    if client == 'opencode':
        for option, value in (('apiKey', key), ('baseURL', base_url)):
            if value is not None:
                settings.setdefault('provider', {}).setdefault('strata', {}).setdefault('options', {})[option] = value
    mcp_key = 'mcp' if client == 'opencode' else 'mcpServers'
    recorded_template = {mcp_key: template.get(mcp_key, {}), 'explicit_mcp': sorted(requested)}
    if 'lsp' in template:
        recorded_template['lsp'] = template['lsp']
    plans = {config: harness.file_state(json.dumps(settings, indent=2) + '\n'),
             state: harness.file_state(json.dumps(recorded_template, indent=2) + '\n')}
    global_rules = target / 'AGENTS.md'
    rules = global_rules.read_text() if global_rules.exists() else ''
    legacy = profiles.read(source / 'migration/guidance.json')
    for match in re.finditer(re.escape(legacy['first_line']), rules):
        start = match.start()
        end = start + legacy['characters']
        if hashlib.sha256(rules[start:end].encode()).hexdigest() == legacy['sha256']:
            rules = rules[:start] + rules[end:]
            break
    plans[global_rules] = harness.file_state(harness.merge_instructions(rules, (library / 'guidance.md').read_text()))

    def add_tree(directory, destination, override=False):
        if destination.is_symlink():
            owned = previous_files.get(str(destination)) == harness.fingerprint(harness.snapshot(destination))
            if destination.resolve() != directory.resolve() and not (override or owned):
                raise ValueError(f'Unowned directory link preserved: {destination}')
            plans[destination] = {'kind': 'symlink', 'target': str(directory)}
        elif not destination.exists():
            plans[destination] = {'kind': 'symlink', 'target': str(directory)}
        elif destination.is_dir():
            for src in directory.rglob('*'):
                if src.is_file() and '__pycache__' not in src.relative_to(directory).parts:
                    dst = destination / src.relative_to(directory)
                    if any(parent.is_symlink() for parent in dst.parents if parent != destination and destination in parent.parents):
                        raise ValueError(f'Nested personal directory link preserved: {dst}')
                    plans[dst] = harness.snapshot(src.resolve())
        else:
            raise ValueError(f'Personal path collision preserved: {destination}')

    for name, skill in sorted(public.items()):
        if name in local:
            continue
        if name in core_names:
            if client == 'antigravity':
                add_tree(skill, target / 'skills' / name)
        else:
            add_tree(skill, target / 'skills-catalog' / name)
    if client == 'antigravity':
        for name, skill in sorted(local.items()):
            add_tree(skill, target / 'skills' / name, override=True)
    if client == 'opencode':
        # Register real source paths with the native editor, below existing skills.
        sources = {**public, **local}
        routing = routing or {'version': 1, 'rules': []}
        routing['core'] = sorted(core_names)
        routing['core_packages'] = {
            name: {'path': str(sources[name] / 'SKILL.md'),
                   'explicit_only': profiles.requires_invocation(sources[name])}
            for name in sorted(core_names)
        }
    if routing is not None:
        plans[target / 'skills-catalog/routing.json'] = harness.file_state(
            json.dumps(routing, indent=2) + '\n', mode=0o644)
    if client == 'opencode':
        for src in (source / 'commands').glob('*.md'):
            destination = target / 'command' / src.name
            if destination.is_dir():
                continue
            if (not destination.exists() and not destination.is_symlink()
                    or previous_files.get(str(destination)) == harness.fingerprint(harness.snapshot(destination))):
                plans[destination] = harness.snapshot(src)
        plugin = source / 'router.ts'
        if plugin.is_file():
            plans[target / 'plugins/sage-skill-router.ts'] = harness.snapshot(plugin)
    else:
        plugin = library / 'runtime/skill_router'
        if plugin.is_dir():
            add_tree(plugin, target / 'plugins/sage-skill-router')
    if (library / 'shared').is_dir():
        add_tree(library / 'shared', target / 'shared')
    released = set()
    for path, digest in previous_files.items():
        path = Path(path)
        if not path.is_relative_to(target):
            continue
        if path in plans or (path.is_dir() and not path.is_symlink()):
            continue
        live = harness.snapshot(path)
        if harness.fingerprint(live) != digest:
            continue
        if agent_migration.owned_path(path, target):
            original = agent_migration.previous_file(path, live, history)
            if original is not None and original != live:
                plans[path] = original
                released.add(path)
        else:
            plans[path] = {'kind': 'absent'}
    if disable_hybrid:
        for name in ('model-router', 'sage'):
            path = target / 'skills' / name
            if path.is_symlink() and 'hybrid-sage' in str(path.resolve()):
                plans[path] = {'kind': 'absent'}
        if client == 'opencode':
            for directory in ('plugin', 'plugins'):
                for extension in ('mjs', 'cjs', 'js', 'ts'):
                    path = target / directory / ('hybrid-sage.' + extension)
                    if path.exists() or path.is_symlink():
                        plans[path] = {'kind': 'absent'}
        else:
            symlink = target / 'plugins/hybrid-sage'
            if symlink.is_symlink() and 'hybrid-sage' in str(symlink.resolve()):
                plans[symlink] = {'kind': 'absent'}
            else:
                path = symlink / 'plugin.json'
                if path.exists() or path.is_symlink():
                    plans[path] = {'kind': 'absent'}
            legacy_link = user_home / '.gemini/antigravity-cli/plugins/hybrid-sage'
            if legacy_link.is_symlink() and 'hybrid-sage' in str(legacy_link.resolve()):
                plans[legacy_link] = {'kind': 'absent'}
    if harness.snapshot(config) != before_config:
        raise ValueError('Client config changed while staging; no files were installed')
    entries = [{'path': str(path), 'before': harness.snapshot(path), 'after': value} for path, value in plans.items()]
    if dry_run:
        print(f'Validated {len(entries)} native {client} entries; dry run made no changes.')
        return None
    entries.append({'path': str(latest), 'before': harness.snapshot(latest), 'after': harness.file_state(json.dumps({
        str(p): harness.fingerprint(value) for p, value in plans.items() if p != config and p not in released and value['kind'] != 'absent'
    }, indent=2) + '\n')})
    backup = target / 'sage/backups' / f'{uuid.uuid4().hex}.json'
    backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    harness.apply_state(backup, harness.file_state(json.dumps({'entries': entries}, indent=2) + '\n'))
    applied = []
    try:
        for entry in entries:
            harness.apply_state(Path(entry['path']), entry['after'])
            applied.append(entry)
    except Exception:
        for entry in reversed(applied):
            harness.apply_state(Path(entry['path']), entry['before'])
        raise
    prune_roots = {target / 'skills', target / 'skills-catalog', target / 'plugins'}
    for entry in applied:
        if entry['after'].get('kind') == 'absent':
            parent = Path(entry['path']).parent
            while parent not in prune_roots and any(parent.is_relative_to(root) for root in prune_roots):
                if parent.is_dir() and not parent.is_symlink() and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
                else:
                    break
    print(f'Config JSON valid. Installed {client} skills and native configuration; restart the client.')
    print(f"Restore with python3 {shlex.quote(str(root / 'sage.py'))} restore {shlex.quote(str(backup))}")
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', required=True, choices=['antigravity', 'opencode'])
    parser.add_argument('--home', type=Path, default=Path(os.environ.get('SAGE_USER_HOME', str(Path.home()))))
    parser.add_argument('--key')
    parser.add_argument('--base-url')
    parser.add_argument('--with-rea', action='store_true')
    parser.add_argument('--mcp', action='append', default=[], metavar='NAME', help='Enable an optional profile MCP')
    parser.add_argument('--disable-hybrid', action='store_true', default=True)
    parser.add_argument('--enable-hybrid', action='store_false', dest='disable_hybrid')
    parser.add_argument('--all-skills', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    root = profiles.ROOT
    profiles.validate([args.client], root)
    subprocess.run([sys.executable, str(root / 'library/scripts/validate-skills.py')], check=True)
    install(root, args.home, args.client, args.key, args.base_url, args.with_rea, args.disable_hybrid, args.dry_run,
            args.all_skills, args.mcp)


if __name__ == '__main__':
    main()
