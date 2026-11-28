"""Validate and render the functional index from the library and client profiles."""
from collections import defaultdict
import re

from library import profiles


def inventory(root):
    lib = root / 'library'
    return {
        'skill': {p.parent.name: p for p in (lib / 'skills').glob('*/SKILL.md')},
        'mcp': {n: lib / 'mcp/servers.json' for n in profiles.read(lib / 'mcp/servers.json')},
        'lsp': {n: lib / 'lsp/servers.json' for n in profiles.read(lib / 'lsp/servers.json')},
        'brief': {p.stem: p for p in (lib / 'agents').glob('*.md')},
        'tool': {'rtk': lib / 'scripts/install_rtk.py', 'token-audit': lib / 'scripts/token_audit.py'},
    }


def availability(kind, name, plan, client):
    if kind == 'brief':
        return 'Manual'
    if kind == 'tool':
        if name == 'token-audit':
            return 'Manual' if client == 'codex' else '—'
        return 'Optional'
    if kind == 'lsp':
        return ('Native' if client == 'opencode' else 'Provision') if name in plan['lsp'] else '—'
    if kind == 'mcp':
        return 'Default' if name in plan['mcp'] else 'Optional' if name in plan['optional_mcp'] else '—'
    return 'Core' if name in plan['core'] else 'Catalog' if name in plan['catalog'] else '—'


def rows(root):
    lib = root / 'library'
    assets = inventory(root)
    plans = {c: profiles.profile(c, root) for c in profiles.CLIENTS}
    seen = set()
    result = []
    for group, kinds in profiles.read(lib / 'functions.json').items():
        for kind, members in kinds.items():
            for name, purpose in members.items():
                key = (kind, name)
                path = assets.get(kind, {}).get(name)
                if key in seen or not path or not path.is_file() or not purpose.strip():
                    raise ValueError(f'Invalid or duplicate functional index entry: {kind} {name}')
                seen.add(key)
                modes = {c: availability(kind, name, plan, c) for c, plan in plans.items()}
                if kind == 'skill' and profiles.requires_invocation(path.parent):
                    modes = {c: (mode + ' · explicit' if mode != '—' else mode) for c, mode in modes.items()}
                result.append((group, kind, name, purpose, path.relative_to(lib), modes))
    missing = {(k, n) for k, items in assets.items() for n in items} - seen
    if missing:
        raise ValueError(f'Add a purpose and group in library/functions.json for {sorted(missing)}')
    return result


def render(root=profiles.ROOT, query='', client=None):
    groups = defaultdict(list)
    clients = [client] if client else profiles.CLIENTS
    labels = {'mcp': 'MCP', 'lsp': 'LSP', 'skill': 'Skill', 'brief': 'Brief', 'tool': 'Tool'}
    terms = query.casefold().split()
    for group, kind, name, purpose, path, modes in rows(root):
        searchable = f"{group} {kind}s {name} {purpose} {' '.join(modes[c] for c in clients)}".casefold()
        if (client and modes[client] == '—') or not all(term in searchable for term in terms):
            continue
        status = ' | '.join(modes[c] for c in clients)
        groups[group].append(f'| {labels[kind]} | [{name}]({path.as_posix()}) | {purpose} | {status} |')
    lines = ['# SAGE library index', '']
    if not groups:
        return f'No capabilities match {query!r}' + (f' in {client}.\n' if client else '.\n')
    lines += [
        '## Status legend',
        '',
        '- **Core** skills are visible at startup.',
        '- **Catalog** skills load on demand.',
        '- **Explicit** skills require a direct request.',
        '- **Default** MCP servers are selected at install.',
        '- **Optional** entries require an explicit opt-in.',
        '- **Native** LSP entries have an OpenCode registration.',
        '- **Provision** means SAGE can install the executable for that profile.',
        '- **Manual** entries are read or run on request.',
        '- A dash (**—**) means the profile omits that capability.',
        '',
        '## Browse by purpose',
        '',
    ]
    for group in groups:
        anchor = re.sub(r'[^a-z0-9 -]', '', group.lower()).replace(' ', '-')
        lines.append(f'- [{group}](#{anchor})')
    for group, entries in groups.items():
        headings = ['Type', 'Capability', 'Use it for', *[{'codex': 'Codex', 'opencode': 'OpenCode', 'antigravity': 'Antigravity'}[c] for c in clients]]
        lines += ['', f'## {group}', '', '| ' + ' | '.join(headings) + ' |', '| ' + ' | '.join(['---'] * len(headings)) + ' |', *entries]
    return '\n'.join(lines) + '\n'


def sync(root=profiles.ROOT, write=False):
    expected = render(root)
    dest = root / 'library/INDEX.md'
    if dest.is_file() and dest.read_text() == expected:
        return False
    if not write:
        raise ValueError('Stale library/INDEX.md. Run python3 sage.py sync.')
    dest.write_text(expected)
    return True
