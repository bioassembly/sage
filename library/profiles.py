"""Resolve a client profile against the canonical capability library."""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CLIENTS = ('codex', 'opencode', 'antigravity')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def formatted(value):
    return json.dumps(value, indent=2, ensure_ascii=False) + '\n'


def profile(client, root=ROOT):
    return read(root / 'clients' / client / 'profile.json')


def native_mcp(client, spec):
    if 'url' in spec:
        body = {'url': spec['url']}
    else:
        context = 'agent' if client == 'opencode' else client
        command = [arg.replace('{context}', context) for arg in spec['command']]
        body = {'command': command} if client == 'opencode' else {'command': command[0], 'args': command[1:]}
        if 'env' in spec:
            body['environment' if client == 'opencode' else 'env'] = spec['env']
    if client == 'opencode':
        body.update(type='remote' if 'url' in spec else 'local', enabled=True, timeout=1000 * spec['startup_seconds'])
    elif client == 'codex':
        body.update(startup_timeout_sec=spec['startup_seconds'], tool_timeout_sec=spec['tool_seconds'],
                    omit_tools_from=['direct'])
    return body


def selected(names, available, field):
    if not isinstance(names, list) or any(not isinstance(n, str) or not re.fullmatch('[a-z0-9][a-z0-9-]*', n) for n in names):
        raise ValueError(f'{field} must be a list of capability names')
    unknown = set(names) - set(available)
    if len(names) != len(set(names)) or unknown:
        raise ValueError(f'{field} contains duplicate or unknown names: {sorted(unknown)}')


def requires_invocation(directory):
    document = (directory / 'SKILL.md').read_text(encoding='utf-8')
    front = re.match(r'\A---[ \t]*\n(.*?)^---[ \t]*(?:\n|$)', document, re.M | re.S)
    if front and re.search(r'^disable-model-invocation:[ \t]*true[ \t]*(?:#.*)?$', front[1], re.M | re.I):
        return True
    metadata = directory / 'agents/openai.yaml'
    if metadata.is_file():
        policy = re.search(r'^policy:[ \t]*\n((?:[ \t]+[^\n]*\n?)+)', metadata.read_text(encoding='utf-8'), re.M)
        return bool(policy and re.search(r'^[ \t]+allow_implicit_invocation:[ \t]*false[ \t]*(?:#.*)?$', policy[1], re.M))
    return False


def invocation_patterns(name, aliases):
    names = [name, *aliases]
    if any(not re.fullmatch(r'[a-z0-9]+(?:[ -][a-z0-9]+)*', n) for n in names):
        raise ValueError(f'{name} needs literal invocation aliases')
    commands = '|'.join(re.escape(n) for n in names if ' ' not in n)
    phrases = '|'.join(re.escape(n).replace(r'\ ', r'\s+') for n in names)
    end = r'`?(?=$|[\s,!?:;]|\.(?:\s|$))'
    return [rf'^\s*`?[/$](?:{commands}){end}', rf'^\s*\[\$(?:{commands})\]\([^\n)]+\)',
            rf'^\s*(?:please\s+)?(?:use|run|apply|invoke|start|conduct)\s+(?:(?:a|an|the)\s+)?`?[/$]?(?:{phrases}){end}']


def routing(plan, library):
    rules = read(library / 'routing.json')
    core, catalog = plan['core'], plan['catalog']
    available = {p.parent.name for p in (library / 'skills').glob('*/SKILL.md')}
    selected(core + catalog, available, 'core and catalog')
    selected(catalog, rules, 'catalog routing')
    overrides = plan.get('rule_overrides', {})
    selected(list(overrides), catalog, 'rule_overrides')
    manual = {n for n in core + catalog if requires_invocation(library / 'skills' / n)}
    entries = []
    for name in catalog:
        rule = {**rules[name], **overrides.get(name, {})}
        rule = {k: v for k, v in rule.items() if v is not None}
        selected(rule.get('companions', []), core + catalog, f'{name} companions')
        if manual.intersection(rule.get('companions', [])):
            raise ValueError(f'{name} cannot activate an explicit-only companion')
        aliases = rule.pop('invocation_aliases', [])
        if name in manual:
            for key in ('files', 'dirs', 'deps'):
                rule.pop(key, None)
            rule['patterns'] = invocation_patterns(name, aliases)
            rule['explicit_only'] = True
        elif aliases:
            raise ValueError(f'{name} needs explicit-only policy to declare invocation aliases')
        for pattern in rule.get('patterns', []):
            re.compile(pattern)
        entries.append({'skill': name, **rule})
    return {'version': 1, 'core': core, 'rules': entries}


def servers(client, names, library):
    catalog = read(library / 'mcp/servers.json')
    selected(names, catalog, 'MCP')
    return {name: native_mcp(client, catalog[name]) for name in names}


def native_config(client, plan, root=ROOT):
    library = root / 'library'
    mcp = servers(client, plan['mcp'], library)
    if client == 'antigravity':
        return {'mcpServers': mcp}
    if client == 'codex':
        return {'mcp_servers': mcp}
    config = read(root / 'clients/opencode/defaults.json')
    catalog = read(library / 'lsp/servers.json')
    config['lsp'] = {name: {key: catalog[name][key] for key in ('command', 'extensions')} for name in plan['lsp']}
    config['mcp'] = mcp
    return config


def validate(clients=CLIENTS, root=ROOT):
    validate_catalog(root)
    library = root / 'library'
    for client in clients:
        plan = profile(client, root)
        routing(plan, library)
        selected(plan['mcp'] + plan['optional_mcp'], read(library / 'mcp/servers.json'), 'MCP')
        selected(plan['lsp'], read(library / 'lsp/servers.json'), 'LSP')


def check_registrations(kind, entries):
    seen = {}
    for name, definition in entries:
        key = json.dumps(definition, sort_keys=True)
        if key in seen:
            raise ValueError(f'{kind} {name} duplicates the registration for {seen[key]}')
        seen[key] = name


def validate_catalog(root=ROOT):
    library = root / 'library'
    mcps = read(library / 'mcp/servers.json')
    lsps = read(library / 'lsp/servers.json')
    check_registrations('MCP', ((name, (spec.get('url'), spec.get('command'), spec.get('env', {})))
                                for name, spec in mcps.items()))
    check_registrations('LSP', ((name, (spec['command'], sorted(spec['extensions'])))
                                for name, spec in lsps.items()))
    commands = {arg for spec in mcps.values() for arg in spec.get('command', [])}
    lock = read(library / 'sources.lock.json')
    for source in lock['sources']:
        if not re.fullmatch(r'[0-9a-f]{40}', source['revision']):
            raise ValueError(f'Invalid reviewed revision for {source["repository"]}')
    for package, version in lock['mcp_packages'].items():
        if not {f'{package}@{version}', f'{package}=={version}'} & commands:
            raise ValueError(f'MCP command differs from the reviewed pin for {package}')
    for name, spec in lsps.items():
        if not spec['extensions'] or not spec['command']:
            raise ValueError(f'{name} needs a command and file extensions')
        for package in spec.get('npm', []):
            if not re.fullmatch(r'(?:@[\w.-]+/)?[\w.-]+@\d+\.\d+\.\d+(?:-[\w.-]+)?', package):
                raise ValueError(f'{name} requires an exact package version: {package}')
        for asset, checksum in spec.get('linux', {}).values():
            if not re.fullmatch('[0-9a-f]{64}', checksum):
                raise ValueError(f'{asset} requires a SHA-256 checksum')
