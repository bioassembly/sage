#!/usr/bin/env python3
"""Route session skills from workspace markers and prompt intent via routing.json."""
from __future__ import annotations

import argparse
from collections import deque
from fnmatch import fnmatch
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import time
import tomllib

IGNORE_DIRS = {'.git', '.hg', 'node_modules', '.venv', 'venv', '__pycache__', 'target', 'dist', 'build', '.next', 'work', '.cache'}
MANIFEST_NAMES = ('package.json', 'pyproject.toml', 'environment.yml', 'environment.yaml', 'Cargo.toml', 'go.mod', 'CMakeLists.txt')
MANIFEST_BYTES = 16384
FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})(.*)$')


def resolve_catalog_dir(script_path: Path, client: str) -> Path:
    env = os.environ.get('SAGE_ROUTER_CATALOG')
    if env:
        return Path(env)
    script_abs = Path(os.path.abspath(str(script_path)))
    if client == 'antigravity':
        candidate = script_abs.parents[2] / 'skills-catalog'
        if candidate.is_dir():
            return candidate
        return Path(os.environ.get('SAGE_USER_HOME', str(Path.home()))) / '.gemini/config/skills-catalog'
    candidate = script_abs.parents[1] / 'skills-catalog'
    if candidate.is_dir():
        return candidate
    return Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'skills-catalog'


def load_routing(catalog_dir: Path) -> dict:
    path = catalog_dir / 'routing.json'
    if not path.is_file():
        return {'version': 1, 'core': [], 'rules': []}
    return json.loads(path.read_text())


def enabled_codex_rules(catalog: Path, rules: list[dict]) -> list[dict]:
    config = catalog.parent / 'config.toml'
    if not config.is_file():
        return rules
    with config.open('rb') as source:
        entries = tomllib.load(source).get('skills', {}).get('config', [])
    disabled = [entry for entry in entries if entry.get('enabled') is False]
    names = {entry['name'] for entry in disabled if entry.get('name')}
    paths = {Path(entry['path']).expanduser().resolve() for entry in disabled if entry.get('path')}
    return [r for r in rules if r['skill'] not in names
            and (not paths or (catalog / r['skill'] / 'SKILL.md').resolve() not in paths)]


def manifest_prefix(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    try:
        with os.fdopen(os.open(path, flags), 'rb') as source:
            if stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                return source.read(MANIFEST_BYTES).decode('utf-8', errors='replace').lower()
    except OSError:
        pass
    return ''


def collect_workspace_signals(roots: list[Path], max_depth: int = 2, max_entries: int = 400) -> tuple[set[str], set[str], str]:
    files: set[str] = set()
    rel_paths: set[str] = set()
    manifests: list[str] = []
    seen_roots: set[Path] = set()
    seen_count = 0
    for root in roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if not resolved.is_dir() or resolved in seen_roots:
            continue
        seen_roots.add(resolved)
        stack = deque([(resolved, 0)])
        while stack and seen_count < max_entries:
            directory, depth = stack.popleft()
            try:
                with os.scandir(directory) as listing:
                    entries = sorted(listing, key=lambda p: p.name)
            except OSError:
                continue
            for entry in entries:
                if seen_count >= max_entries:
                    break
                name = entry.name
                if name in IGNORE_DIRS or (name.startswith('.') and name not in ('.semgrep.yml', '.semgrep.yaml', '.github')):
                    continue
                seen_count += 1
                path = Path(entry.path)
                rel = path.relative_to(resolved).as_posix()
                rel_paths.add(rel)
                if entry.is_dir(follow_symlinks=False):
                    if depth < max_depth:
                        stack.append((path, depth + 1))
                elif entry.is_file(follow_symlinks=False):
                    files.add(name)
                    if depth == 0 and (name in MANIFEST_NAMES or (name.startswith('requirements') and name.endswith('.txt'))):
                        manifests.append(manifest_prefix(path))
    return files, rel_paths, '\n'.join(manifests)


def match_workspace(roots: list[Path], rules: list[dict]) -> list[str]:
    if not any(rule.get(key) for rule in rules for key in ('files', 'dirs', 'deps')):
        return []
    files, rel_paths, manifest_text = collect_workspace_signals(roots)
    matched: list[str] = []
    for rule in rules:
        hit = any(fnmatch(name, pat) for pat in rule.get('files', []) for name in files)
        if not hit:
            hit = any(rel == d or rel.startswith(d + '/') for d in rule.get('dirs', []) for rel in rel_paths)
        if not hit and manifest_text:
            hit = any(re.search(r'(?:^|[^a-z0-9_-])' + re.escape(dep.lower()) + r'(?:$|[^a-z0-9_-])', manifest_text)
                      for dep in rule.get('deps', []))
        if hit:
            matched.append(rule['skill'])
    return resolve_companions(matched, rules)


def prompt_prose(text: str) -> str:
    if not any(marker in text for marker in ('`', '~', '>')):
        return text
    lines = []
    fence = ''
    for line in text.splitlines():
        marker = FENCE.match(line)
        if fence:
            if marker and marker[1].startswith(fence) and not marker[2].strip():
                fence = ''
        elif marker:
            fence = marker[1]
        elif not line.lstrip().startswith('>'):
            lines.append(line)
    return '\n'.join(lines)


def select_prompt(text: str, rules: list[dict]) -> tuple[list[str], bool]:
    text = prompt_prose(text)
    if not text.strip():
        return [], False
    requested = [r['skill'] for r in rules if any(re.search(p, text, re.IGNORECASE) for p in r.get('requests', []))]
    if requested:
        return resolve_companions(requested, rules), True
    matched = [r for r in rules if any(re.search(p, text, re.IGNORECASE) for p in r.get('patterns', []))]
    legacy_explicit = [r for r in matched if r.get('explicit_only')]
    return resolve_companions([r['skill'] for r in legacy_explicit or matched], rules), bool(legacy_explicit)


def match_prompt(text: str, rules: list[dict]) -> list[str]:
    return select_prompt(text, rules)[0]


def resolve_companions(skills: list[str], rules: list[dict]) -> list[str]:
    by_name = {rule['skill']: rule for rule in rules}
    ordered: list[str] = []
    seen: set[str] = set()
    queue = list(skills)
    while queue:
        name = queue.pop(0)
        if name in seen or name not in by_name:
            continue
        seen.add(name)
        ordered.append(name)
        for companion in by_name[name].get('companions', []):
            if companion not in seen:
                queue.append(companion)
    return ordered


def digest(value) -> str:
    return sha256(json.dumps(value, separators=(',', ':')).encode()).hexdigest()


def save_session_state(path: Path | None, state: dict) -> None:
    if not path:
        return
    staged = None
    try:
        new = not path.exists()
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as output:
            staged = Path(output.name)
            json.dump({**state, 'ts': time.time()}, output)
        staged.replace(path)
        if new:
            # Trim only when a session is added and tolerate concurrent hook processes.
            entries = []
            for entry in path.parent.glob('*.json'):
                try:
                    entries.append((entry.stat().st_mtime, entry))
                except OSError:
                    continue
            for _, stale in sorted(entries, reverse=True)[40:]:
                if stale != path:
                    stale.unlink(missing_ok=True)
    except OSError:
        pass
    finally:
        if staged:
            staged.unlink(missing_ok=True)


def build_message(matched: list[str], catalog_dir: Path, rules: list[dict], include_intro: bool) -> str:
    lines: list[str] = []
    if matched:
        lines.append('[SAGE Auto-Skill Router] Auto-selected relevant session skills (read & apply now):')
        by_name = {r['skill']: r for r in rules}
        for name in matched:
            skill_md = catalog_dir / name / 'SKILL.md'
            if skill_md.is_file():
                summary = by_name.get(name, {}).get('summary', '')
                suffix = f' — {summary}' if summary else ''
                lines.append(f'- `{name}`: {skill_md}{suffix}')
    if include_intro and rules:
        lines.append(
            f'[SAGE On-Demand Catalog] Use {catalog_dir}/routing.json to find other relevant skills. '
            'Read matched SKILL.md files and honor explicit-only entries.'
        )
    return '\n'.join(lines)


def route_hook(payload: dict, client: str, prompt_only: bool, script_path: Path) -> dict:
    catalog_dir = resolve_catalog_dir(script_path, client)
    routing = load_routing(catalog_dir)
    rules = routing.get('rules', [])
    if client == 'codex':
        rules = enabled_codex_rules(catalog_dir, rules)
    if not rules:
        return {}
    target_base = catalog_dir.parent
    common = payload.get('common') or {}
    conv_id = common.get('conversationId') or payload.get('session_id') or payload.get('sessionId') or ''
    sfile = target_base / 'sage/router-state' / f'{digest(conv_id)}.json' if conv_id else None
    state_data = {}
    if sfile and sfile.is_file():
        try:
            state_data = json.loads(sfile.read_text())
        except (OSError, json.JSONDecodeError):
            state_data = {}
    if not isinstance(state_data, dict) or not isinstance(state_data.get('ts'), (int, float)):
        state_data = {}
    if time.time() - state_data.get('ts', 0) >= 86400:
        state_data = {}
    source = payload.get('source') if not prompt_only else None
    previous_active = state_data.get('active', []) if source != 'clear' else []
    if source in ('clear', 'compact'):
        state_data = {}
    sent = set(state_data.get('skills', []))
    intro_sent = bool(state_data.get('intro'))

    raw_roots = list(common.get('workspacePaths') or [])
    cwd = common.get('cwd') or payload.get('cwd')
    if cwd:
        raw_roots.append(cwd)
    roots = [Path(p) for p in raw_roots if isinstance(p, str) and p]
    workspace = digest(sorted({str(p) for p in roots}))
    prompt_text = common.get('lastUserInput') or payload.get('prompt') or payload.get('user_prompt') or ''
    prompt_skills, explicit = select_prompt(prompt_text, rules)
    active = prompt_skills if prompt_text else previous_active
    turn = payload.get('turn_id') or common.get('turnId')
    previous_request = state_data.get('request')
    request = previous_request
    if prompt_text:
        request = digest([turn, prompt_text]) if explicit else None
    repeatable = set(prompt_skills) if explicit and request != previous_request else set()

    changed_workspace = workspace != state_data.get('workspace')
    workspace_skills = match_workspace(roots, rules) if roots and (not prompt_only or changed_workspace) else []

    core = set(routing.get('core', []))
    selected = workspace_skills + (active if source == 'compact' else prompt_skills)
    allowed = {rule['skill'] for rule in rules} - core
    fresh = [name for name in dict.fromkeys(selected)
             if name in allowed and (name not in sent or name in repeatable)
             and (catalog_dir / name / 'SKILL.md').is_file()]
    text = build_message(fresh, catalog_dir, rules, not intro_sent)
    if text or (intro_sent and (changed_workspace or request != previous_request or active != previous_active)):
        save_session_state(sfile, {'skills': sorted(sent.union(fresh)), 'intro': intro_sent or bool(text),
                                  'workspace': workspace, 'request': request, 'active': active})
    if not text:
        return {}

    if client == 'antigravity':
        return {'injectSteps': [{'systemMessage': {'systemMessage': text, 'renderInfo': {'hidden': True}}}]}
    return {'hookSpecificOutput': {'hookEventName': payload.get('hook_event_name', 'SessionStart'), 'additionalContext': text}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client', choices=['antigravity', 'codex'], default='antigravity')
    parser.add_argument('--prompt', action='store_true')
    args = parser.parse_args()
    raw = sys.stdin.read().strip()
    payload = json.loads(raw) if raw else {}
    result = route_hook(payload, args.client, args.prompt, Path(__file__))
    if result:
        print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
