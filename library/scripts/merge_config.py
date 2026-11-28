#!/usr/bin/env python3
"""Merge client JSON defaults without replacing user preferences."""
import copy
import re


def defaults(template, current):
    if not isinstance(template, dict) or not isinstance(current, dict):
        return copy.deepcopy(current)
    result = copy.deepcopy(template)
    for key, value in current.items():
        result[key] = defaults(result[key], value) if key in result else copy.deepcopy(value)
    return result


def merge(template, current, previous, client, disable_hybrid=False):
    result = defaults(template, current)
    key = 'mcp' if client == 'opencode' else 'mcpServers'
    servers = copy.deepcopy(current.get(key, {}))
    for name, incoming in template.get(key, {}).items():
        old = previous.get(key, {}).get(name)
        live = servers.get(name)
        if live is None:
            servers[name] = copy.deepcopy(incoming)
        elif isinstance(live, dict) and isinstance(old, dict) and all(live.get(k) == old.get(k) for k in ('type', 'command', 'args', 'url')):
            server = {**copy.deepcopy(live), **copy.deepcopy(incoming)}
            server['enabled' if client == 'opencode' else 'disabled'] = live.get(
                'enabled' if client == 'opencode' else 'disabled', client == 'opencode')
            for field in ('enabled', 'disabled'):
                if field in live:
                    server[field] = live[field]
            for field in ('env', 'environment', 'headers'):
                if field in live:
                    server[field] = defaults(incoming.get(field, {}), live[field])
            servers[name] = server
        # A custom registration sharing a template name is not adopted.
    for name, old in previous.get(key, {}).items():
        if name == 'hybrid-sage' or name in template.get(key, {}):
            continue
        live = servers.get(name)
        if not isinstance(live, dict) or not isinstance(old, dict):
            continue
        flag, default = ('enabled', True) if client == 'opencode' else ('disabled', False)
        if {flag: default, **live} == {flag: default, **old}:
            servers.pop(name, None)
    if disable_hybrid and isinstance(servers.get('hybrid-sage'), dict):
        servers['hybrid-sage']['enabled' if client == 'opencode' else 'disabled'] = client != 'opencode'
    result[key] = servers
    if client == 'opencode':
        incoming = template.get('lsp', {})
        live = current.get('lsp')
        old = previous.get('lsp')
        if 'lsp' in previous and live == old:
            result['lsp'] = copy.deepcopy(incoming)
        elif isinstance(live, dict) and isinstance(incoming, dict):
            lsps = copy.deepcopy(live)
            old = old if isinstance(old, dict) else {}
            for name, entry in incoming.items():
                if name not in live or live[name] == old.get(name):
                    lsps[name] = copy.deepcopy(entry)
            for name in old.keys() - incoming.keys():
                if name in live and live[name] == old[name]:
                    del lsps[name]
            result['lsp'] = lsps
        plugins = []
        for entry in template.get('plugins', []) + current.get('plugins', []) + current.get('plugin', []):
            if isinstance(entry, list) and len(entry) == 2:
                entry = {'package': entry[0], 'options': entry[1]}
            name = entry.get('package', '') if isinstance(entry, dict) else str(entry)
            if name == '@dietrichgebert/ponytail':
                continue  # Original native skill replaces this old unpinned injector.
            if disable_hybrid and re.search(r'(?:^|[/@:])hybrid-sage(?=$|[/@]|\.(?:mjs|cjs|js|ts)(?:$|[?#]))', name):
                continue
            if entry not in plugins:
                plugins.append(entry)
        result.pop('plugin', None)
        result['plugins'] = plugins
    return result


def render(value, replacements):
    if isinstance(value, dict):
        return {k: render(v, replacements) for k, v in value.items()}
    if isinstance(value, list):
        return [render(v, replacements) for v in value]
    return replacements.get(value, value) if isinstance(value, str) else value
