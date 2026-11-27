#!/usr/bin/env python3
"""Check skill metadata, bundled resources and duplicate packages."""
from hashlib import sha256
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


def outside_fences(text: str) -> str:
    lines = []
    fence = None
    for line in text.splitlines():
        marker = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if marker:
            if fence is None:
                fence = marker[1]
            elif marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return '\n'.join(lines)


def package_key(skill: Path) -> tuple:
    files = []
    for path in sorted(skill.parent.rglob('*')):
        relative = path.relative_to(skill.parent)
        if not path.is_file() or '__pycache__' in relative.parts or path.suffix == '.pyc':
            continue
        data = path.read_bytes()
        if path == skill:
            front, separator, body = data.partition(b'\n---')
            # Ignore only the declared name. Prose, resources and executable modes matter.
            front = re.sub(rb'^name:[^\r\n]*', b'name:', front, count=1, flags=re.M)
            data = front + separator + body
        files.append((relative, bool(path.stat().st_mode & 0o111), sha256(data).digest()))
    return tuple(files)


def validate(root: Path) -> list[str]:
    errors = []
    seen = {}
    skills = sorted(root.glob('*/SKILL.md'))
    if not skills:
        return [f'{root}: no skills found']
    for skill in skills:
        text = skill.read_text(encoding='utf-8')
        frontmatter = re.match(r'\A---\s*\n(.*?)\n---(?:\n|$)', text, re.S)
        if not frontmatter:
            errors.append(f'{skill}: missing YAML frontmatter')
            continue
        key = package_key(skill)
        if key in seen:
            errors.append(f'{skill}: duplicate skill package of {seen[key]}')
        else:
            seen[key] = skill.parent.name
        for key in ('name', 'description'):
            match = re.search(rf'^{key}:\s*(\S.*)$', frontmatter[1], re.M)
            if not match:
                errors.append(f'{skill}: missing {key}')
            elif key == 'name' and match[1].strip().strip('\"\'') != skill.parent.name:
                errors.append(f'{skill}: name must match directory')
        for document in sorted(skill.parent.rglob('*.md')):
            content = outside_fences(document.read_text(encoding='utf-8'))
            targets = re.findall(r'\]\(([^\s)]+)(?:\s+[^)]*)?\)', content)
            # Inline guide paths are instructions to read a bundled resource too.
            targets += re.findall(r'`((?:\./)?references?/[^`\s]+\.md)`', content)
            for target in sorted(set(targets)):
                url = urlsplit(target.strip('<>'))
                if url.scheme or url.netloc or not url.path or url.path.startswith(('~', '/')):
                    continue
                path = document.parent / unquote(url.path)
                if not path.exists() and url.path.startswith(("references/", "reference/")):
                    path = skill.parent / unquote(url.path)
                if not path.exists():
                    errors.append(f'{document}: missing local resource {target}')
    return errors


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    default = repo / 'skills'
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    errors = validate(root)
    if (repo / "third_party/lock.json").exists():
        from validate_vendor import validate as validate_vendor
        errors.extend(validate_vendor(repo, root))
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f'Validated {len(list(root.glob("*/SKILL.md")))} skills: metadata and local resources present.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
