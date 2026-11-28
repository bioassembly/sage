"""Measure workspace scans and warm prompt matching on a fixed synthetic workload."""
import argparse
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
from time import perf_counter_ns


def measure(action, samples):
    durations = []
    for _ in range(samples):
        started = perf_counter_ns()
        action()
        durations.append((perf_counter_ns() - started) / 1e6)
    return round(statistics.median(durations), 3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1], help='SAGE checkout to measure')
    args = parser.parse_args()
    root = args.root.resolve()
    sys.path.insert(0, str(root))
    from library import profiles
    from library.runtime.skill_router.route_skills import match_prompt, match_workspace

    with tempfile.TemporaryDirectory(prefix='sage-router-benchmark-') as temp:
        workspace = Path(temp) / 'work'
        catalog = Path(temp) / 'skills-catalog'
        workspace.mkdir()
        catalog.mkdir()
        with (workspace / 'pyproject.toml').open('wb') as manifest:
            manifest.write(b'[project]\ndependencies=["biopython"]\n')
            manifest.truncate(32 * 1024 * 1024)
        prompt = 'Review the working diff.'
        execution = profiles.routing(profiles.profile('codex', root), root / 'library')
        rules = execution['rules']
        assert match_workspace([workspace], rules) == ['biopython']
        assert match_prompt(prompt, rules) == ['sage-review']
        print(json.dumps({'runtime': 'python', 'workspace_median_ms': measure(lambda: match_workspace([workspace], rules), 7),
                          'prompt_batch_1000_median_ms': measure(lambda: [match_prompt(prompt, rules) for _ in range(1000)], 7)}))

        (catalog / 'routing.json').write_text(json.dumps(profiles.routing(profiles.profile('opencode', root), root / 'library')))
        package = catalog / 'sage-review'
        package.mkdir()
        (package / 'SKILL.md').touch()
        subprocess.run(['node', Path(__file__).with_name('router_benchmark.mjs'), root, workspace, catalog, prompt], check=True)


if __name__ == '__main__':
    main()
