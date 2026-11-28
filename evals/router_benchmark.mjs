import assert from "node:assert/strict"
import { join } from "node:path"
import { pathToFileURL } from "node:url"

const [root, workspace, catalogDir, prompt] = process.argv.slice(2)
const { createRouter, matchWorkspace } = await import(pathToFileURL(join(root, "clients/opencode/router.ts")))
const router = createRouter({ coreDir: join(workspace, "skills"), catalogDir })
const scan = () => matchWorkspace([workspace], router.routing.rules)
assert.deepEqual(scan(), ["biopython"])
assert.deepEqual(router.matchCatalogPrompt(prompt), ["sage-review"])

function medianMilliseconds(action) {
  const samples = Array.from({ length: 7 }, () => {
    const start = performance.now()
    action()
    return performance.now() - start
  })
  return Number(samples.sort((a, b) => a - b)[3].toFixed(3))
}

console.log(JSON.stringify({
  runtime: "node",
  workspace_median_ms: medianMilliseconds(scan),
  prompt_batch_1000_median_ms: medianMilliseconds(() => {
    for (let i = 0; i < 1000; i++) router.matchCatalogPrompt(prompt)
  }),
}))
