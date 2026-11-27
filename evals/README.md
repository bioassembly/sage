# Frozen Eval Suite

Use the same fixtures, client, model and settings to compare two profiles. Record the assertions, tool calls, tokens and elapsed time for each run.

## Catalog routing

Run `python3 sage.py eval-routing` for all three profiles or append one client name. The suite builds temporary workspaces, compiles the selected profile and runs its shipped workspace and prompt matchers. OpenCode uses Node.js 24 or newer. Each case specifies the exact set of catalog skills a fresh session should surface, including companions. A mismatch prints the missing and unexpected names and exits with status 1. [Labeled requests and workspaces](routing.json)

Add both a matching request and a plausible near miss when tuning a route. Use the model-run protocol below to measure task success, latency and token use.

## Protocol

1. **Freeze** — record before running:
   ```bash
   jq -S . ~/.config/opencode/opencode.json | sha256sum
   nvidia-smi --query-gpu=name --format=csv,noheader   # + model + quant from the tested matrix
   ```
2. **Preconditions** — llama-server up and otherwise idle (`pgrep -f llama-server`; no other GPU work) for local-model runs. Fresh client session per case. Temperature pinned per the case file.
3. **Run** — paste the task verbatim into a session whose working directory is the case's scratch dir.
4. **Grade** — every check must be a command with a pass/fail output, never eyeballed. Store `{check, passed, evidence}` per check.
5. **Record** — one row per case in `evals/results.md` (create on first run):

| Date | Config hash | Case | Pass rate | Tool calls | Tokens (est.) | Wall clock | Notes |
|---|---|---|---|---|---|---|---|

n=3 minimum per case when comparing variants; report mean ± spread.

## Cases

| File | Type | Catches |
|---|---|---|
| [api-accuracy.md](cases/api-accuracy.md) | API accuracy | context7 value, model drift |
| [multi-step-edit.md](cases/multi-step-edit.md) | Multi-step edit | agentic-coding discipline, LSP value |
| [procedure-selection.md](cases/procedure-selection.md) | Skill routing | Procedure selection and false positives |
| [retrieval.md](cases/retrieval.md) | Retrieval | token-efficiency ladder |
| [long-horizon-checkpoint.md](cases/long-horizon-checkpoint.md) | Long-horizon | checkpoint + NOTES.md protocol surviving compaction/restart |
| [injection-canary.md](cases/injection-canary.md) | Refusal/hygiene | prompt-injection posture |

Scratch dirs live under `/tmp/opencode/evals/<case>/` — recreatable from each case's Setup section.
