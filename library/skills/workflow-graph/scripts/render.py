#!/usr/bin/env python3
"""Render the DOT files in workflow.json, or verify the published offline bundle."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET

SVG = 'http://www.w3.org/2000/svg'
XLINK = 'http://www.w3.org/1999/xlink'
ET.register_namespace('', SVG)
ET.register_namespace('xlink', XLINK)
STAMP = re.compile(rb'<!-- workflow-graph source=([0-9a-f]{64}) svg=([0-9a-f]{64}) -->\n')


def digest(data):
    return hashlib.sha256(data).hexdigest().encode('ascii')


def views_for(directory):
    spec = json.loads((directory / 'workflow.json').read_text(encoding='utf-8'))
    if not isinstance(spec.get('title'), str) or not spec['title'].strip() or not spec.get('views'):
        raise ValueError('workflow.json needs a title and at least one view')
    ids = set()
    for view in spec['views']:
        name = view['id']
        if not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*', name) or name in ids:
            raise ValueError(f'Invalid or duplicate view ID: {name}')
        ids.add(name)
        if not all(isinstance(view.get(k), str) and view[k].strip() for k in ('title', 'description')):
            raise ValueError(f'{name} requires a title and a text description')
        for item in view.get('evidence', []):
            link = urlsplit(item['path'])
            path = Path(unquote(link.path))
            if (not item['label'] or link.scheme or link.netloc or path.is_absolute()
                    or not (directory / path).is_file()):
                raise ValueError(f'{name} has missing or nonlocal evidence: {item["path"]}')
    return spec


def check_numbers(svg, view):
    seen = set()
    stages = {}
    for node in svg.iter(f'{{{SVG}}}g'):
        if 'node' not in node.get('class', '').split():
            continue
        label = next(node.iter(f'{{{SVG}}}text'), None)
        text = ''.join(label.itertext()).strip() if label is not None else ''
        match = re.match(r'^([1-9][0-9]*)([a-z]?)(?:\s*·|[.)])\s+', text)
        if not match:
            raise ValueError(f'{view}: start each node label with its step number: {text}')
        number, branch = match.groups()
        tag = number + branch
        if tag in seen:
            raise ValueError(f'{view}: duplicate step {tag}')
        seen.add(tag)
        stages.setdefault(int(number), []).append(branch)
    if not stages or sorted(stages) != list(range(1, max(stages) + 1)):
        raise ValueError(f'{view}: number stages consecutively from 1')
    for number, branches in stages.items():
        if branches != [''] and sorted(branches) != [chr(97+i) for i in range(len(branches))]:
            raise ValueError(f'{view}: use consecutive branch letters at step {number}')


def embed(svg, view, ids, numbered=False):
    root = ET.fromstring(svg)
    if root.tag != f'{{{SVG}}}svg' or 'viewBox' not in root.attrib:
        raise ValueError(f'{view["id"]} did not produce a scalable SVG')
    if numbered:
        check_numbers(root, view['id'])
    # Each inline diagram gets its own ID space, including Graphviz gradient fills.
    prefix = view['id'] + '--'
    local_ids = {elem.attrib['id'] for elem in root.iter() if 'id' in elem.attrib}
    for elem in root.iter():
        if elem.tag.split('}')[-1].lower() in {'script', 'foreignobject', 'image', 'style', 'use'}:
            raise ValueError('Use self-contained Graphviz shapes and text in the offline viewer')
        for key, value in list(elem.attrib.items()):
            attr = key.split('}')[-1]
            if attr.lower().startswith('on'):
                raise ValueError(f'Unsupported active SVG attribute: {attr}')
            if attr == 'id':
                elem.set(key, prefix + value)
            elif attr == 'href':
                dest = urlsplit(value)
                if dest.scheme or dest.netloc:
                    raise ValueError(f'Use repository-relative diagram links: {value}')
                if dest.path == 'index.html' and dest.fragment:
                    if dest.fragment not in ids:
                        raise ValueError(f'Unknown detail view: {value}')
                    elem.set(key, '#' + dest.fragment)
                elif value.startswith('#') and value[1:] in local_ids:
                    elem.set(key, '#' + prefix + value[1:])
            elif 'url(#' in value:
                elem.set(key, re.sub(r'url\(#([^)]+)\)', lambda m: 'url(#' + prefix + m[1] + ')', value))
    root.set('aria-label', view['description'])
    root.set('role', 'group')
    return ET.tostring(root, encoding='unicode')


STYLE = """
:root{color-scheme:light;font:16px/1.5 system-ui,sans-serif;color:#173044;background:#f4f7f8}
*{box-sizing:border-box}body{max-width:76rem;margin:auto;padding:1.5rem clamp(.75rem,3vw,3rem)}
h1,h2{line-height:1.15}a{color:#11597a;text-underline-offset:.18em}
nav,footer{display:flex;flex-wrap:wrap;gap:.5rem 1.25rem}
section{margin:2rem 0;padding:clamp(.75rem,2vw,1.5rem);background:white;border:1px solid #b9cbd2;border-radius:.5rem}
section:target{outline:2px solid #237969}section p{max-width:70ch}
.figure{overflow:auto;margin:1rem 0}.figure svg{display:block;width:100%;height:auto;min-width:35rem}
:focus-visible{outline:3px solid #b14d11;outline-offset:3px}
@media print{body{background:white}nav,footer{display:none}section{break-inside:avoid}.figure svg{min-width:0}}
"""


def viewer(spec, diagrams):
    esc = html.escape
    title = esc(spec['title'])
    nav, sections = [], []
    for number, (view, svg) in enumerate(zip(spec['views'], diagrams, strict=True), start=1):
        name, heading = view['id'], f'View {number} · {esc(view["title"])}'
        nav.append(f'<a href="#{name}">{heading}</a>')
        links = [f'<a href="{name}.dot">Editable DOT</a>', f'<a href="{name}.svg">Full-size SVG</a>']
        links += [f'<a href="{esc(item["path"])}">{esc(item["label"])}</a>' for item in view.get('evidence', [])]
        sections.append(f'<section id="{name}" tabindex="-1"><h2>{heading}</h2><p>{esc(view["description"])}</p>'
                        f'<div class="figure">{svg}</div><footer>{" ".join(links)}</footer></section>')
    content = '\n'.join(sections)
    key = ('<p>Start at step 1 in each view. Letters share a stage. Follow the arrow labels to choose a branch.</p>'
           if spec.get('numbered') else '')
    return (f'<!doctype html>\n<html lang="en"><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{title}</title><style>{STYLE}</style>'
            f'<main><h1>{title}</h1>{key}<nav aria-label="Workflow views">{" ".join(nav)}</nav>\n'
            f'{content}</main></html>\n').encode()


def build(directory, check=False):
    spec = views_for(directory)
    ids = {view['id'] for view in spec['views']}
    if not check and not shutil.which('dot'):
        raise ValueError('Rendering requires Graphviz dot on PATH. The saved bundle can be verified with --check.')
    result, diagrams = {}, []
    obsolete = []
    for path in sorted(directory.glob('*.svg')):
        if path.stem in ids:
            continue
        saved = path.read_bytes()
        stamp = STAMP.match(saved)
        if stamp:
            if check or digest(saved[stamp.end():]) != stamp[2]:
                raise ValueError(f'Obsolete or edited managed preview: {path.name}')
            obsolete.append(path)
    for view in spec['views']:
        name = view['id']
        dot, out = directory / f'{name}.dot', directory / f'{name}.svg'
        source_hash = digest(dot.read_bytes())
        if check:
            saved = out.read_bytes()
            stamp = STAMP.match(saved)
            if not stamp or stamp[1] != source_hash or stamp[2] != digest(saved[stamp.end():]):
                raise ValueError(f'Stale or edited SVG: {out.name}')
            svg = saved[stamp.end():]
        else:
            proc = subprocess.run(['dot', '-Tsvg', dot.name], cwd=directory, capture_output=True, timeout=60)
            if proc.returncode:
                raise ValueError(f'{dot.name}: {proc.stderr.decode(errors="replace").strip()}')
            if proc.stderr:
                sys.stderr.write(proc.stderr.decode(errors='replace'))
            # Put the provenance comment before the SVG element, after removing the XML declaration/DTD.
            start = proc.stdout.find(b'<svg')
            if start == -1:
                raise ValueError(f'Graphviz returned no SVG for {dot.name}')
            svg = proc.stdout[start:]
            result[out] = b'<!-- workflow-graph source=' + source_hash + b' svg=' + digest(svg) + b' -->\n' + svg
        diagrams.append(embed(svg, view, ids, spec.get('numbered', False)))
    page = directory / 'index.html'
    result[page] = viewer(spec, diagrams)
    if check:
        if page.read_bytes() != result[page]:
            raise ValueError('Stale offline viewer: index.html')
    else:
        # Render and validate the entire set before publishing any output.
        with tempfile.TemporaryDirectory(dir=directory) as temp:
            for path, content in result.items():
                (Path(temp) / path.name).write_bytes(content)
            for path in result:
                os.replace(Path(temp) / path.name, path)
            for path in obsolete:
                path.unlink()
    print(f'{"Verified" if check else "Rendered"} {len(diagrams)} workflow views and {page.name}.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--check', action='store_true')
    options = parser.parse_args()
    try:
        build(options.directory.resolve(), options.check)
    except (OSError, ValueError, KeyError, ET.ParseError, subprocess.TimeoutExpired) as error:
        sys.exit(f'Workflow graph: {error}')
