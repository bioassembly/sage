"""Release old agent overrides using the active install's private restore journals."""
import base64
import json

from library.scripts.client_state import snapshot

MISSING = object()


def active_history(latest, relevant):
    """Follow the manifest snapshots backwards, skipping unrelated or restored runs."""
    cursor = snapshot(latest)
    history = []
    journals = sorted((latest.parent / 'backups').glob('*.json'), key=lambda p: p.stat().st_mtime_ns, reverse=True)
    for path in journals:
        if cursor['kind'] == 'absent':
            break
        entries = {e['path']: e for e in json.loads(path.read_text())['entries']}
        manifest = entries.get(str(latest))
        if manifest and manifest['after'] == cursor:
            history.append({path: entries[path] for path in relevant if path in entries})
            cursor = manifest['before']
    return history


def owned_path(path, target):
    """These are the native agent and shortcut locations previous releases managed."""
    if not path.is_relative_to(target):
        return False
    parts = path.relative_to(target).parts
    if len(parts) < 2:
        return False
    if parts[0] in ('agent', 'agents'):
        return True
    return parts[0] == 'command' and parts[1] in {
        'checkpoint.md', 'doctor.md', 'grill-with-docs.md', 'red-team.md', 'review.md',
    }


def previous_file(path, state, history):
    """Return the pre-install state when a matching journal proves ownership."""
    original = None
    for entries in history:
        entry = entries.get(str(path))
        if entry is None:
            continue
        if entry['after'] != state:
            break
        original = state = entry['before']
        if state['kind'] == 'absent':
            break
    return original


def undo_defaults(current, before, after):
    if before == after:
        return current
    if type(current) is type(after) and current == after:
        return before
    if isinstance(current, dict) and isinstance(after, dict) and (before is MISSING or isinstance(before, dict)):
        result = current.copy()
        prior = {} if before is MISSING else before
        for key, saved in after.items():
            value = undo_defaults(current.get(key, MISSING), prior.get(key, MISSING), saved)
            if value is MISSING:
                result.pop(key, None)
            else:
                result[key] = value
        if result == current:
            return current
        return result if result or before is not MISSING else MISSING
    return current


def original_section(config, key, live, history, loads):
    def section(state):
        if state['kind'] == 'file':
            return loads(base64.b64decode(state['data']).decode()).get(key, MISSING)
        return MISSING

    for entries in history:
        entry = entries.get(str(config))
        if entry:
            # A symlink target's contents were never saved in these snapshots.
            if any(entry[side]['kind'] not in ('file', 'absent') for side in ('before', 'after')):
                break
            live = undo_defaults(live, section(entry['before']), section(entry['after']))
    return live
