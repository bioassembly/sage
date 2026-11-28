import test from "node:test"
import assert from "node:assert/strict"
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import SageSkillRouterPlugin, {
  createRouter,
  extractLatestUserText,
  matchWorkspace,
  parseFrontmatter,
} from "./router.ts"

const SAMPLE_ROUTING = {
  version: 1,
  core: ["agentic-coding", "skill-acquisition"],
  rules: [
    {
      skill: "nextflow",
      category: "bioinformatics",
      summary: "Nextflow DSL2",
      files: ["*.nf", "nextflow.config"],
      patterns: ["\\bnextflow\\b"],
      companions: ["fair-data-principles"],
    },
    {
      skill: "fair-data-principles",
      category: "bioinformatics",
      summary: "FAIR metadata",
      files: ["codemeta.json"],
      patterns: ["\\bfair data\\b"],
    },
    {
      skill: "vercel-react-best-practices",
      category: "web",
      summary: "React",
      deps: ["react"],
      patterns: ["\\breact\\b"],
    },
    {
      skill: "pdf-inplace-editing",
      category: "documents",
      summary: "PDF edit",
      patterns: ["\\bpdf\\b|\\bredact\\b"],
    },
  ],
}

test("parseFrontmatter supports quoted and folded descriptions", () => {
  const parsed = parseFrontmatter(
    "---\nname: example-skill\ndescription: >-\n  Multi-line\n  description.\n---\nBody text\n",
    "fallback",
  )
  assert.equal(parsed.name, "example-skill")
  assert.equal(parsed.description, "Multi-line description.")
  assert.equal(parsed.content, "Body text\n")
})

test("workspace and prompt routing only select matching skills plus companions", () => {
  const root = mkdtempSync(join(tmpdir(), "sage-router-"))
  try {
    const coreDir = join(root, "skills")
    const catalogDir = join(root, "skills-catalog")
    const workDir = join(root, "proj")
    mkdirSync(coreDir, { recursive: true })
    mkdirSync(workDir, { recursive: true })
    for (const s of ["nextflow", "fair-data-principles", "vercel-react-best-practices", "pdf-inplace-editing"]) {
      mkdirSync(join(catalogDir, s), { recursive: true })
      writeFileSync(join(catalogDir, s, "SKILL.md"), `---\nname: ${s}\ndescription: ${s} desc\n---\nBody ${s}\n`)
    }
    writeFileSync(join(catalogDir, "routing.json"), JSON.stringify(SAMPLE_ROUTING))
    writeFileSync(join(workDir, "main.nf"), "process FOO {}")

    const router = createRouter({ coreDir, catalogDir })
    const ws = router.activateWorkspace([workDir])
    assert.deepEqual(ws, ["nextflow", "fair-data-principles"])
    assert.equal(router.active.has("vercel-react-best-practices"), false)

    const editorAdded = []
    router.registerIntoEditor({ add: (entry) => editorAdded.push(entry) })
    assert.deepEqual(editorAdded.map((e) => e.id), ["nextflow", "fair-data-principles"])

    // Local override in coreDir prevents shadowing by catalog.
    mkdirSync(join(coreDir, "pdf-inplace-editing"), { recursive: true })
    writeFileSync(join(coreDir, "pdf-inplace-editing", "SKILL.md"), "---\nname: pdf-inplace-editing\ndescription: local\n---\n")
    assert.deepEqual(router.matchCatalogPrompt("please redact this pdf"), [])
    rmSync(join(coreDir, "pdf-inplace-editing"), { recursive: true })
    router.registerIntoEditor({
      add: () => {},
      get: (id) => id === "pdf-inplace-editing" ? { path: join(workDir, "pdf/SKILL.md") } : undefined,
    })
    assert.deepEqual(router.matchCatalogPrompt("please redact this pdf"), [])

    // A direct request can use a bundle without registering it for other sessions.
    const manual = { skill: "interview", explicit_only: true, patterns: ["^/interview"], companions: ["notes"] }
    for (const name of ["interview", "notes"]) {
      mkdirSync(join(catalogDir, name))
      writeFileSync(join(catalogDir, name, "SKILL.md"), "# " + name)
    }
    writeFileSync(join(catalogDir, "routing.json"), JSON.stringify({
      ...SAMPLE_ROUTING, rules: [...SAMPLE_ROUTING.rules, manual, { skill: "notes" }],
    }))
    const session = createRouter({ coreDir, catalogDir })
    assert.deepEqual(session.matchCatalogPrompt("/interview"), ["interview", "notes"])
    assert.equal(session.active.size, 0)
    assert.deepEqual(session.matchCatalogPrompt("Fix a typo"), [])
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test("extractLatestUserText handles v2 parts and string messages", () => {
  assert.equal(
    extractLatestUserText([
      { role: "assistant", parts: [{ type: "text", text: "ignored" }] },
      { role: "user", parts: [{ type: "text", text: "scrape this table" }] },
    ]),
    "scrape this table",
  )
  assert.equal(typeof SageSkillRouterPlugin.setup, "function")
  assert.equal(typeof SageSkillRouterPlugin.server, "function")
})

test("workspace scans limit manifest reads and ignore symlink targets", () => {
  const root = mkdtempSync(join(tmpdir(), "sage-workspace-"))
  try {
    const workspace = join(root, "project")
    const external = join(root, "external")
    mkdirSync(workspace)
    mkdirSync(external)
    writeFileSync(join(external, "outside.nf"), "")
    writeFileSync(join(external, "pyproject.toml"), "nextflow")
    symlinkSync(external, join(workspace, "link"))
    const manifest = join(workspace, "pyproject.toml")
    symlinkSync(join(external, "pyproject.toml"), manifest)
    const rules = [{ skill: "nextflow", files: ["*.nf"], deps: ["nextflow"] }]
    assert.deepEqual(matchWorkspace([workspace], rules), [])
    rmSync(manifest)
    writeFileSync(manifest, " ".repeat(16384) + "nextflow")
    assert.deepEqual(matchWorkspace([workspace], rules), [])
    writeFileSync(manifest, "nextflow")
    assert.deepEqual(matchWorkspace([workspace], rules), ["nextflow"])
  } finally {
    rmSync(root, { recursive: true, force: true })
  }
})

test("setup(ctx) registers workspace skills and keeps prompt matches scoped to each request", async () => {
  const root = mkdtempSync(join(tmpdir(), "sage-router-setup-"))
  const prevEnv = process.env.SAGE_ROUTER_CATALOG
  try {
    const coreDir = join(root, "skills")
    const catalogDir = join(root, "skills-catalog")
    const workDir = join(root, "proj")
    mkdirSync(coreDir, { recursive: true })
    mkdirSync(workDir, { recursive: true })
    for (const s of ["nextflow", "fair-data-principles", "pdf-inplace-editing"]) {
      mkdirSync(join(catalogDir, s), { recursive: true })
      writeFileSync(join(catalogDir, s, "SKILL.md"), `---\nname: ${s}\ndescription: ${s} desc\n---\nBody ${s}\n`)
    }
    writeFileSync(join(catalogDir, "routing.json"), JSON.stringify(SAMPLE_ROUTING))
    writeFileSync(join(workDir, "main.nf"), "nextflow.enable.dsl=2\n")

    process.env.SAGE_ROUTER_CATALOG = catalogDir
    let transformFn
    let contextHook
    let registeredIds = []

    const runTransform = async () => {
      const added = []
      await transformFn({ add: (entry) => added.push(entry) })
      registeredIds = added.map((e) => e.id)
    }

    await SageSkillRouterPlugin.setup({
      location: { directory: workDir, worktree: workDir },
      skill: {
        transform: async (cb) => {
          transformFn = cb
          await runTransform()
        },
      },
      session: {
        hook: async (name, cb) => {
          if (name === "context") contextHook = cb
        },
      },
    })

    assert.deepEqual(registeredIds, ["nextflow", "fair-data-principles"])
    assert.equal(typeof contextHook, "function")

    const event1 = {
      system: ["Base prompt"],
      messages: [{ role: "user", parts: [{ type: "text", text: "please redact this pdf" }] }],
    }
    await contextHook(event1)
    await runTransform()
    assert.deepEqual(registeredIds, ["nextflow", "fair-data-principles"])
    assert.ok(event1.system.some((line) => typeof line === "string" && line.includes("[SAGE Auto-Skill Router]")))
    assert.ok(event1.system.some((line) => typeof line === "string" && line.includes("pdf-inplace-editing")))
    const otherSession = { system: [], messages: [{ role: "user", content: "Fix a typo" }] }
    await contextHook(otherSession)
    assert.ok(otherSession.system.every((line) => !line.includes("pdf-inplace-editing")))
  } finally {
    if (prevEnv === undefined) delete process.env.SAGE_ROUTER_CATALOG
    else process.env.SAGE_ROUTER_CATALOG = prevEnv
    rmSync(root, { recursive: true, force: true })
  }
})

test("the client profile selects disjoint real library packages", () => {
  const client = dirname(fileURLToPath(import.meta.url))
  const library = resolve(client, "../../library")
  const profile = {
    ...JSON.parse(readFileSync(join(library, "default-skills.json"), "utf8")),
    ...JSON.parse(readFileSync(join(client, "profile.json"), "utf8")),
  }
  const rules = JSON.parse(readFileSync(join(library, "routing.json"), "utf8"))
  const selected = [...profile.core, ...profile.catalog]
  assert.equal(new Set(selected).size, selected.length)
  for (const name of selected) assert.ok(existsSync(join(library, "skills", name, "SKILL.md")), name)
  for (const name of profile.catalog) assert.ok(rules[name], name)
})
