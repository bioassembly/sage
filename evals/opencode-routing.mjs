import { readFileSync } from "node:fs"
import { matchPrompt, matchWorkspace } from "../clients/opencode/router.ts"

const { rules, cases } = JSON.parse(readFileSync(0, "utf8"))
const selections = cases.map(({ workspace, prompt }) => [
  ...new Set([...matchWorkspace([workspace], rules), ...matchPrompt(prompt, rules)]),
])
process.stdout.write(JSON.stringify(selections))
