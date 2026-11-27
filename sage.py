#!/usr/bin/env python3
"""Inspect, synchronize and activate the SAGE harness profiles."""
import argparse
from pathlib import Path
import os
import subprocess
import sys

from library import index, profiles
from library.scripts import client_state
from library.lsp.provision import provision

ROOT = profiles.ROOT
GRAPH = ROOT / 'library/skills/workflow-graph/scripts/render.py'


def run(argv):
    subprocess.run(argv, check=True, cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('check', 'sync', 'show'):
        sub.add_parser(name).add_argument('client', nargs='?', choices=profiles.CLIENTS)
    sub.add_parser('eval-routing', help='replay labeled cases through the native catalog matchers').add_argument(
        'client', nargs='?', choices=profiles.CLIENTS)
    lookup = sub.add_parser('index', help='find capabilities by purpose, name or type')
    lookup.add_argument('terms', nargs='*')
    lookup.add_argument('--client', choices=profiles.CLIENTS)
    sub.add_parser('restore', help='restore an install journal').add_argument('journal', type=Path)
    doctor = sub.add_parser('doctor', help='check an installed profile for drift')
    doctor.add_argument('client', choices=profiles.CLIENTS)
    doctor.add_argument('--home', type=Path)
    graphs = sub.add_parser('graph')
    graphs.add_argument('--check', action='store_true')
    lsp = sub.add_parser('lsp')
    lsp.add_argument('client', choices=profiles.CLIENTS)
    mode = lsp.add_mutually_exclusive_group()
    mode.add_argument('--install', action='store_true')
    mode.add_argument('--check', action='store_true', help='return an error if selected executables are missing')
    lsp.add_argument('--prefix', type=Path, default=Path.home() / '.local')
    install = sub.add_parser('install', help='activate one harness, forwarding native installer options')
    install.add_argument('client', choices=profiles.CLIENTS)
    install.add_argument('--home', type=Path, help='redirect every installation target to a test user root')
    install.add_argument('--dry-run', action='store_true')
    args, native = parser.parse_known_args()
    if native and args.command != 'install':
        parser.error('unrecognized arguments: ' + ' '.join(native))
    client = getattr(args, 'client', None)
    clients = [client] if client else profiles.CLIENTS
    if args.command == 'show':
        for name in clients:
            plan = profiles.profile(name)
            print(f'{name}  {len(plan["core"])} core skills, {len(plan["catalog"])} catalog skills')
            for key in ('core', 'catalog', 'mcp', 'optional_mcp', 'lsp'):
                print(f'  {key}: {", ".join(plan[key]) or "none"}')
    elif args.command == 'eval-routing':
        from evals.routing import evaluate
        if evaluate(clients):
            sys.exit(1)
    elif args.command == 'index':
        print(index.render(ROOT, ' '.join(args.terms), client), end='')
    elif args.command == 'sync':
        profiles.validate()
        changed = index.sync(write=True)
        print('Updated library/INDEX.md.' if changed else 'Library index is current.')
    elif args.command == 'check':
        profiles.validate(clients)
        index.sync()
        run([sys.executable, ROOT / 'library/scripts/validate-skills.py'])
        if 'codex' in clients:
            import tomllib
            tomllib.loads((ROOT / 'clients/codex/defaults.toml').read_text())
        print('Profiles, functional index and package integrity checks passed.')
    elif args.command == 'restore':
        client_state.restore(args.journal)
    elif args.command == 'doctor':
        home = args.home or (Path(os.environ['SAGE_USER_HOME']) if os.environ.get('SAGE_USER_HOME') else None)
        if client == 'codex':
            overrides = ['--codex-home', home / '.codex', '--skills-dir', home / '.agents/skills'] if home else []
            run([sys.executable, ROOT / 'clients/codex/installer.py', 'doctor', *overrides])
        else:
            home = (home or Path.home()).expanduser().resolve()
            target = home / ('.config/opencode' if client == 'opencode' else '.gemini/config')
            profiles.read(target / ('opencode.json' if client == 'opencode' else 'mcp_config.json'))
            for name, digest in profiles.read(target / 'sage/latest.json').items():
                path = Path(name)
                if client_state.fingerprint(client_state.snapshot(path)) != digest or not path.exists():
                    raise ValueError(f'Installed entry changed or missing: {path}')
            print(f'{client} configuration and recorded files are intact.')
    elif args.command == 'graph':
        run([sys.executable, GRAPH, ROOT / 'docs/architecture', *(['--check'] if args.check else [])])
    elif args.command == 'lsp':
        plan = profiles.profile(client)
        catalog = profiles.read(ROOT / 'library/lsp/servers.json')
        profiles.selected(plan['lsp'], catalog, 'LSP')
        missing = provision(plan['lsp'], catalog, args.prefix, args.install)
        if args.check and missing:
            raise ValueError(f'Missing selected language servers: {", ".join(missing)}')
    else:
        entry = ([ROOT / 'clients/codex/installer.py', 'install'] if client == 'codex' else
                 [ROOT / 'library/scripts/install_client.py', '--client', client])
        if native[:1] == ['--']:
            native = native[1:]
        user_home = args.home or (Path(os.environ['SAGE_USER_HOME']) if os.environ.get('SAGE_USER_HOME') else None)
        if user_home and client == 'codex':
            home = user_home.expanduser().resolve()
            if any(a.split('=')[0] in ('--codex-home', '--skills-dir', '--bin-dir') for a in native):
                parser.error('--home sets all Codex destinations and cannot be combined with individual path overrides')
            native += ['--codex-home', str(home / '.codex'), '--skills-dir', str(home / '.agents/skills'),
                       '--bin-dir', str(home / '.local/bin')]
        elif user_home:
            native += ['--home', str(user_home.expanduser().resolve())]
        if args.dry_run:
            native.append('--dry-run')
        run([sys.executable, *entry, *native])


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        sys.exit(f'SAGE: {exc}')
