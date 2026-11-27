"""Replay labeled requests and workspaces through the shipped catalog matchers."""
import json
from pathlib import Path
import subprocess
import tempfile

from library import profiles
from library.runtime.skill_router.route_skills import match_prompt, match_workspace


def evaluate(clients, root=profiles.ROOT):
    fixtures = profiles.read(root / 'evals/routing.json')
    failed = 0
    with tempfile.TemporaryDirectory() as tmp:
        for client in clients:
            cases = [c for c in fixtures if client in c.get('clients', profiles.CLIENTS)]
            if not cases:
                raise ValueError(f'No labeled routing cases for {client}')
            rules = profiles.routing(profiles.profile(client, root), root / 'library')['rules']
            inputs = []
            for number, case in enumerate(cases):
                workspace = Path(tmp) / client / str(number)
                workspace.mkdir(parents=True)
                for name in case.get('files', []):
                    if Path(name).is_absolute() or '..' in Path(name).parts:
                        raise ValueError(f'Invalid workspace marker in {case["id"]}: {name}')
                    path = workspace / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.touch()
                inputs.append({'workspace': str(workspace), 'prompt': case['prompt']})
            if client == 'opencode':
                proc = subprocess.run(['node', root / 'evals/opencode-routing.mjs'], check=True,
                                      input=json.dumps({'rules': rules, 'cases': inputs}),
                                      stdout=subprocess.PIPE, text=True)
                results = json.loads(proc.stdout)
            else:
                results = [match_workspace([Path(i['workspace'])], rules) + match_prompt(i['prompt'], rules)
                           for i in inputs]
            errors = 0
            for case, result in zip(cases, results, strict=True):
                actual, expected = set(result), set(case['expect'])
                if actual != expected:
                    errors += 1
                    print(f"  {client}/{case['id']}  missing={sorted(expected - actual)}  unexpected={sorted(actual - expected)}")
            print(f'{client}  {len(cases) - errors}/{len(cases)} exact matches')
            failed += errors
    return failed
