import { closeSync, constants, existsSync, fstatSync, openSync, readdirSync, readFileSync, readSync, realpathSync, statSync } from "node:fs"
import { dirname, join, relative, resolve } from "node:path"
import { fileURLToPath } from "node:url"

export type RoutingRule = {
  skill: string
  category?: string
  summary?: string
  files?: string[]
  dirs?: string[]
  deps?: string[]
  patterns?: string[]
  requests?: string[]
  companions?: string[]
  explicit_only?: boolean
}

export type RoutingConfig = {
  version: number
  core: string[]
  core_packages?: Record<string, { path: string; explicit_only: boolean }>
  rules: RoutingRule[]
}

const IGNORE_DIRS = new Set([
  ".git",
  ".hg",
  "node_modules",
  ".venv",
  "venv",
  "__pycache__",
  "target",
  "dist",
  "build",
  ".next",
  "work",
  ".cache",
])

const MANIFEST_NAMES = new Set([
  "package.json",
  "pyproject.toml",
  "environment.yml",
  "environment.yaml",
  "Cargo.toml",
  "go.mod",
  "CMakeLists.txt",
])

export function parseFrontmatter(raw: string, fallbackName: string): {
  name: string
  description: string
  content: string
} {
  const match = raw.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/)
  if (!match) {
    return { name: fallbackName, description: fallbackName, content: raw }
  }
  const front = match[1]
  const content = raw.slice(match[0].length)
  const lines = front.split(/\r?\n/)
  let name = fallbackName
  let description = fallbackName

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const kv = line.match(/^([a-zA-Z0-9_-]+):\s*(.*)$/)
    if (!kv) continue
    const [, key, rest] = kv
    const trimmed = rest.trim()
    if (key === "name" && trimmed) {
      name = trimmed.replace(/^["']|["']$/g, "")
    } else if (key === "description") {
      if (trimmed === ">" || trimmed === ">-" || trimmed === "|" || trimmed === "|-") {
        const block: string[] = []
        while (i + 1 < lines.length && /^[ \t]+\S/.test(lines[i + 1])) {
          i++
          block.push(lines[i].trim())
        }
        if (block.length > 0) description = block.join(" ")
      } else if (trimmed) {
        description = trimmed.replace(/^["']|["']$/g, "")
      }
    }
  }
  return { name, description, content }
}

function globToRegExp(glob: string): RegExp {
  const escaped = glob
    .replace(/[.+^${}()|[\]\\]/g, "\\$&")
    .replace(/\*/g, ".*")
    .replace(/\?/g, ".")
  return new RegExp(`^${escaped}$`)
}

function manifestPrefix(path: string): string {
  const fd = openSync(path, constants.O_RDONLY | (constants.O_NOFOLLOW ?? 0) | (constants.O_NONBLOCK ?? 0))
  try {
    if (!fstatSync(fd).isFile()) return ""
    const buffer = Buffer.alloc(16384)
    const bytes = readSync(fd, buffer, 0, buffer.length, 0)
    return buffer.toString("utf8", 0, bytes).toLowerCase()
  } finally {
    closeSync(fd)
  }
}

export function collectWorkspaceSignals(
  roots: string[],
  maxDepth = 2,
  maxEntries = 400,
): { files: Set<string>; relPaths: Set<string>; manifestText: string } {
  const files = new Set<string>()
  const relPaths = new Set<string>()
  const manifests: string[] = []
  const seenRoots = new Set<string>()
  let count = 0

  for (const rawRoot of roots) {
    if (!rawRoot) continue
    let root: string
    try {
      root = realpathSync(rawRoot)
      if (!statSync(root).isDirectory() || seenRoots.has(root)) continue
    } catch {
      continue
    }
    seenRoots.add(root)
    const queue: Array<[string, number]> = [[root, 0]]
    while (queue.length > 0 && count < maxEntries) {
      const [dir, depth] = queue.shift()!
      let entries
      try {
        entries = readdirSync(dir, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))
      } catch {
        continue
      }
      for (const entry of entries) {
        if (count >= maxEntries) break
        const name = entry.name
        if (IGNORE_DIRS.has(name) || (name.startsWith(".") && name !== ".semgrep.yml" && name !== ".semgrep.yaml" && name !== ".github")) {
          continue
        }
        count++
        const full = join(dir, name)
        const rel = relative(root, full).replace(/\\/g, "/")
        relPaths.add(rel)
        if (entry.isDirectory()) {
          if (depth < maxDepth) queue.push([full, depth + 1])
        } else if (entry.isFile()) {
          files.add(name)
          if (depth === 0 && (MANIFEST_NAMES.has(name) || (/^requirements.*\.txt$/).test(name))) {
            try {
              manifests.push(manifestPrefix(full))
            } catch {
              // ignore unreadable manifest
            }
          }
        }
      }
    }
  }
  return { files, relPaths, manifestText: manifests.join("\n") }
}

export function resolveCompanions(skills: string[], rules: RoutingRule[]): string[] {
  const byName = new Map(rules.map((r) => [r.skill, r]))
  const ordered: string[] = []
  const seen = new Set<string>()
  const queue = [...skills]
  while (queue.length > 0) {
    const id = queue.shift()!
    if (seen.has(id) || !byName.has(id)) continue
    seen.add(id)
    ordered.push(id)
    for (const comp of byName.get(id)?.companions ?? []) {
      if (!seen.has(comp)) queue.push(comp)
    }
  }
  return ordered
}

export function matchWorkspace(roots: string[], rules: RoutingRule[]): string[] {
  if (!rules.some((rule) => rule.files?.length || rule.dirs?.length || rule.deps?.length)) return []
  const { files, relPaths, manifestText } = collectWorkspaceSignals(roots)
  const fileList = Array.from(files)
  const relList = Array.from(relPaths)
  const matched: string[] = []

  for (const rule of rules) {
    let hit = (rule.files ?? []).some((pat) => {
      const rx = globToRegExp(pat)
      return fileList.some((name) => rx.test(name))
    })
    if (!hit) {
      hit = (rule.dirs ?? []).some((d) => relList.some((rel) => rel === d || rel.startsWith(d + "/")))
    }
    if (!hit && manifestText) {
      hit = (rule.deps ?? []).some((dep) => {
        const rx = new RegExp(`(?:^|[^a-z0-9_-])${dep.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:$|[^a-z0-9_-])`)
        return rx.test(manifestText)
      })
    }
    if (hit) matched.push(rule.skill)
  }
  return resolveCompanions(matched, rules)
}

function promptProse(text: string): string {
  if (!/[\u0060~>]/.test(text)) return text
  const lines: string[] = []
  let fence = ""
  for (const line of text.split(/\r?\n/)) {
    const marker = line.match(/^ {0,3}(\u0060{3,}|~{3,})(.*)$/)
    if (fence) {
      if (marker?.[1].startsWith(fence) && !marker[2].trim()) fence = ""
    } else if (marker) {
      fence = marker[1]
    } else if (!line.trimStart().startsWith(">")) {
      lines.push(line)
    }
  }
  return lines.join("\n")
}

function createPromptMatcher(rules: RoutingRule[]) {
  const compile = (patterns: string[] = []) => patterns.flatMap((pattern) => {
    try { return [new RegExp(pattern, "i")] } catch { return [] }
  })
  const compiled = rules.map((rule) => ({ rule, requests: compile(rule.requests), patterns: compile(rule.patterns) }))
  return (raw: string): string[] => {
    const text = promptProse(raw)
    if (!text.trim()) return []
    const requested = compiled.filter((entry) => entry.requests.some((pattern) => pattern.test(text)))
    if (requested.length) return resolveCompanions(requested.map(({ rule }) => rule.skill), rules)
    const matched = compiled.filter((entry) => entry.patterns.some((pattern) => pattern.test(text)))
    const legacyExplicit = matched.filter(({ rule }) => rule.explicit_only)
    return resolveCompanions((legacyExplicit.length ? legacyExplicit : matched).map(({ rule }) => rule.skill), rules)
  }
}

export function matchPrompt(text: string, rules: RoutingRule[]): string[] {
  return createPromptMatcher(rules)(text)
}

export function extractLatestUserText(messages: unknown): string {
  if (!Array.isArray(messages)) return ""
  for (let i = messages.length - 1; i >= 0; i--) {
    const msg = messages[i] as any
    const role = msg?.role ?? msg?.info?.role
    if (role !== "user") continue
    if (typeof msg?.content === "string") return msg.content
    const parts = Array.isArray(msg?.parts) ? msg.parts : Array.isArray(msg?.content) ? msg.content : []
    const texts = parts
      .map((p: any) => (typeof p === "string" ? p : typeof p?.text === "string" ? p.text : ""))
      .filter(Boolean)
    if (texts.length > 0) return texts.join("\n")
  }
  return ""
}

function appendSystem(system: unknown[], text: string): void {
  if (system.some((entry) => (typeof entry === "string" ? entry : (entry as any)?.text ?? "").includes(text))) {
    return
  }
  const first = system[0]
  if (first !== undefined && typeof first === "object" && first !== null) {
    system.push({ type: "text", text })
  } else {
    system.push(text)
  }
}

export function defaultBaseDirs(metaUrl = import.meta.url): { coreDir: string; catalogDir: string } {
  const envCatalog = process.env.SAGE_ROUTER_CATALOG
  const base = envCatalog ? resolve(dirname(envCatalog)) : resolve(dirname(fileURLToPath(metaUrl)), "..")
  return {
    coreDir: join(base, "skills"),
    catalogDir: envCatalog || join(base, "skills-catalog"),
  }
}

export function createRouter(dirs = defaultBaseDirs()) {
  const routingPath = join(dirs.catalogDir, "routing.json")
  const routing: RoutingConfig = existsSync(routingPath)
    ? JSON.parse(readFileSync(routingPath, "utf8"))
    : { version: 1, core: [], rules: [] }
  const rules = routing.rules ?? []
  const selectPrompt = createPromptMatcher(rules)
  const coreSet = new Set(routing.core ?? [])
  const active = new Set<string>()
  const nativeOverrides = new Set<string>()

  const isCoreOrLocal = (id: string) =>
    coreSet.has(id) || nativeOverrides.has(id) || existsSync(join(dirs.coreDir, id, "SKILL.md"))

  const readSkill = (id: string, skillPath: string, explicitOnly = false) => {
    if (!existsSync(skillPath)) return null
    const raw = readFileSync(skillPath, "utf8")
    const parsed = parseFrontmatter(raw, id)
    return { id, path: skillPath, ...parsed, ...(explicitOnly ? { autoinvoke: false } : {}) }
  }

  return {
    routing,
    active,
    activateWorkspace(roots: string[]): string[] {
      const added: string[] = []
      for (const id of matchWorkspace(roots, rules)) {
        if (!active.has(id) && !isCoreOrLocal(id) && existsSync(join(dirs.catalogDir, id, "SKILL.md"))) {
          active.add(id)
          added.push(id)
        }
      }
      return added
    },
    matchCatalogPrompt(text: string): string[] {
      return selectPrompt(text).filter(
        (id) => !isCoreOrLocal(id) && existsSync(join(dirs.catalogDir, id, "SKILL.md")),
      )
    },
    registerIntoEditor(editor: any) {
      nativeOverrides.clear()
      for (const { skill: id } of rules) {
        const existing = editor.get?.(id)
        if (existing && existing.path !== join(dirs.catalogDir, id, "SKILL.md")) nativeOverrides.add(id)
      }
      for (const [id, entry] of Object.entries(routing.core_packages ?? {})) {
        if (editor.get?.(id)) continue
        const loaded = readSkill(id, entry.path, entry.explicit_only)
        if (loaded) editor.add(loaded)
      }
      for (const id of active) {
        if (editor.get?.(id) || isCoreOrLocal(id)) continue
        const loaded = readSkill(id, join(dirs.catalogDir, id, "SKILL.md"))
        if (loaded) editor.add(loaded)
      }
    },
    buildIntro(): string {
      if (rules.length === 0) return ""
      const loadedList = active.size > 0 ? `Auto-loaded for this project: ${Array.from(active).join(", ")}. ` : ""
      return (
        `[SAGE Auto-Skill Router] ${loadedList}` +
        `Use ${routingPath} to find other relevant skills. Read matched SKILL.md files and honor explicit-only entries.`
      )
    },
  }
}

const SageSkillRouterPlugin = {
  id: "sage-skill-router",
  async setup(ctx: any) {
    const dirs = defaultBaseDirs()
    const router = createRouter(dirs)
    const roots = [ctx.location?.directory, ctx.location?.worktree].filter(
      (p): p is string => typeof p === "string" && p.length > 0,
    )
    if (roots.length === 0) roots.push(process.cwd())
    router.activateWorkspace(roots)

    if (ctx.skill?.transform) {
      await ctx.skill.transform((editor: any) => {
        router.registerIntoEditor(editor)
      })
    }

    if (ctx.session?.hook) {
      await ctx.session.hook("context", async (event: any) => {
        const userText = extractLatestUserText(event?.messages)
        // OpenCode's registry is workspace-wide. Keep prompt matches within the current request.
        const matched = router.matchCatalogPrompt(userText)
        if (Array.isArray(event?.system)) {
          const intro = router.buildIntro()
          if (intro) appendSystem(event.system, intro)
          if (matched.length > 0) {
            const paths = matched
              .map((id) => `\`${id}\` (${join(dirs.catalogDir, id, "SKILL.md")})`)
              .join(", ")
            appendSystem(event.system, `[SAGE Auto-Skill Router] Matched task skill(s): ${paths}. Read and follow now.`)
          }
        }
      })
    }
  },

  async server() {
    const router = createRouter()
    router.activateWorkspace([process.cwd()])
    return {
      "experimental.chat.system.transform": async (_input: any, output: any) => {
        if (Array.isArray(output?.system)) {
          const intro = router.buildIntro()
          if (intro) appendSystem(output.system, intro)
        }
      },
    }
  },
}

export default SageSkillRouterPlugin
