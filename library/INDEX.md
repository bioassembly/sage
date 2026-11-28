# SAGE library index

## Status legend

- **Core** skills are visible at startup.
- **Catalog** skills load on demand.
- **Explicit** skills require a direct request.
- **Default** MCP servers are selected at install.
- **Optional** entries require an explicit opt-in.
- **Native** LSP entries have an OpenCode registration.
- **Provision** means SAGE can install the executable for that profile.
- **Manual** entries are read or run on request.
- A dash (**—**) means the profile omits that capability.

## Browse by purpose

- [Token savings and context](#token-savings-and-context)
- [Planning and design](#planning-and-design)
- [Debugging, tests and review](#debugging-tests-and-review)
- [Code navigation and language intelligence](#code-navigation-and-language-intelligence)
- [Documentation, research and visualization](#documentation-research-and-visualization)
- [Git and repository maintenance](#git-and-repository-maintenance)
- [Skills, integrations and evaluation](#skills-integrations-and-evaluation)
- [Web applications](#web-applications)
- [Security review and static inspection](#security-review-and-static-inspection)
- [Scientific workflows, data and reporting](#scientific-workflows-data-and-reporting)

## Token savings and context

| Type | Capability | Use it for | Codex | OpenCode | Antigravity |
| --- | --- | --- | --- | --- | --- |
| Skill | [token-efficiency](skills/token-efficiency/SKILL.md) | Measure token use and reduce excess context with targeted retrieval and bounded output. | Catalog | Catalog | Catalog |
| Skill | [ponytail](skills/ponytail/SKILL.md) | Keep implementation and responses small enough for the task. | Core | Core | Core |
| Skill | [checkpoint](skills/checkpoint/SKILL.md) | Save the state needed to resume after compaction or interruption. | Core | Core | Core |
| Tool | [rtk](scripts/install_rtk.py) | Filter repetitive terminal output before it enters the model context. | Optional | Optional | Optional |
| Tool | [token-audit](scripts/token_audit.py) | Measure input, cached input, output and reasoning tokens in local Codex session logs. | Manual | — | — |

## Planning and design

| Type | Capability | Use it for | Codex | OpenCode | Antigravity |
| --- | --- | --- | --- | --- | --- |
| Skill | [agentic-coding](skills/agentic-coding/SKILL.md) | Take a scoped implementation from inspection through verification. | Core | Core | Core |
| Skill | [sage-design](skills/sage-design/SKILL.md) | Design a module interface and check consequential trade-offs. | Catalog | Catalog | Catalog |
| Skill | [domain-modeling](skills/domain-modeling/SKILL.md) | Document domain terminology and architecture decisions. | Catalog | Catalog | Catalog |
| Skill | [grill-with-docs](skills/grill-with-docs/SKILL.md) | Interview a design while maintaining the glossary and decision records. | Catalog · explicit | Catalog · explicit | Catalog · explicit |
| Skill | [grilling](skills/grilling/SKILL.md) | Resolve a design decision through one focused question at a time. | Catalog | Catalog | Catalog |
| Skill | [to-spec](skills/to-spec/SKILL.md) | Turn agreed requirements into a verifiable implementation specification. | Catalog · explicit | Catalog · explicit | Catalog · explicit |
| Skill | [sage-spec](skills/sage-spec/SKILL.md) | Define an outcome, its constraints and acceptance checks. | Catalog | Catalog | Catalog |
| Skill | [to-tickets](skills/to-tickets/SKILL.md) | Slice a specification into independently actionable work items. | Catalog · explicit | Catalog · explicit | Catalog · explicit |
| Skill | [sage-tickets](skills/sage-tickets/SKILL.md) | Split a specification into verifiable tickets with dependencies. | Catalog | Catalog | Catalog |

## Debugging, tests and review

| Type | Capability | Use it for | Codex | OpenCode | Antigravity |
| --- | --- | --- | --- | --- | --- |
| Skill | [sage-debug](skills/sage-debug/SKILL.md) | Reproduce a defect and verify its root cause and fix. | Catalog | Catalog | Catalog |
| Skill | [sage-test-design](skills/sage-test-design/SKILL.md) | Choose behavior-focused tests and useful regression cases. | Catalog | Catalog | Catalog |
| Skill | [test-driven-development](skills/test-driven-development/SKILL.md) | Build a change through a failing test, implementation and refactoring. | Catalog | Catalog | Catalog |
| Skill | [verification-before-completion](skills/verification-before-completion/SKILL.md) | Run the checks that substantiate a completion claim. | Catalog | Catalog | Catalog |
| Skill | [sage-review](skills/sage-review/SKILL.md) | Review a change or pull request and report actionable findings. | Catalog | Catalog | Catalog |
| Skill | [red-team](skills/red-team/SKILL.md) | Stress-test a design or plan for failure modes and mistaken assumptions. | Catalog | Catalog | Catalog |

## Code navigation and language intelligence

| Type | Capability | Use it for | Codex | OpenCode | Antigravity |
| --- | --- | --- | --- | --- | --- |
| Skill | [read-only](skills/read-only/SKILL.md) | Trace a code path and answer questions without editing the project. | Catalog | Catalog | Catalog |
| MCP | [serena](mcp/servers.json) | Find definitions, references and symbols in a project using semantic tools. | Optional | Optional | Optional |
| LSP | [pyright](lsp/servers.json) | Python type diagnostics and symbol navigation. | Provision | Native | Provision |
| LSP | [typescript](lsp/servers.json) | JavaScript, JSX, TypeScript and TSX diagnostics and navigation. | Provision | Native | Provision |
| LSP | [bash](lsp/servers.json) | Shell script definitions, completions and diagnostics. | Provision | Native | Provision |
| LSP | [yaml](lsp/servers.json) | YAML schema completion and validation. | Provision | Native | Provision |
| LSP | [json](lsp/servers.json) | JSON and JSONC schema completion and validation. | — | Native | — |
| LSP | [marksman](lsp/servers.json) | Markdown and Quarto document symbols, headings and links. | Provision | Native | Provision |
| LSP | [php](lsp/servers.json) | PHP symbol navigation, completion and diagnostics. | — | Native | — |
| LSP | [tailwind](lsp/servers.json) | Tailwind CSS class completion and diagnostics in templates. | — | Native | — |

## Documentation, research and visualization

| Type | Capability | Use it for | Codex | OpenCode | Antigravity |
| --- | --- | --- | --- | --- | --- |
| Skill | [workflow-graph](skills/workflow-graph/SKILL.md) | Trace source-backed workflow steps and publish numbered, navigable Graphviz diagrams. | Catalog | Catalog | Catalog |
| Skill | [sage-explain](skills/sage-explain/SKILL.md) | Explain an implementation or result from first principles. | Catalog | Catalog | Catalog |
| Skill | [sage-overnight](skills/sage-overnight/SKILL.md) | Run an extended investigation with checkpoints and stopping conditions. | Catalog | Catalog | Catalog |
| Skill | [sage-pdf-editing](skills/sage-pdf-editing/SKILL.md) | Apply localized PDF changes and verify the rendered result. | Catalog | Catalog | Catalog |
| Skill | [sage-web-scraping](skills/sage-web-scraping/SKILL.md) | Collect web data with bounded requests and validate the extracted records. | Catalog | Catalog | Catalog |
| MCP | [context7](mcp/servers.json) | Look up version-specific library and framework documentation. | Optional | Default | Default |
| MCP | [deepwiki](mcp/servers.json) | Explore indexed public repository documentation and architecture. | Optional | Optional | Optional |

## Git and repository maintenance

| Type | Capability | Use it for | Codex | OpenCode | Antigravity |
| --- | --- | --- | --- | --- | --- |
| Skill | [sage-git-commit](skills/sage-git-commit/SKILL.md) | Verify and stage authorized changes before committing or pushing. | Catalog | Catalog | Catalog |
| Skill | [sage-git-worktrees](skills/sage-git-worktrees/SKILL.md) | Create and verify a worktree with the repository's setup. | Catalog | Catalog | Catalog |
| Skill | [sage-repo-maintenance](skills/sage-repo-maintenance/SKILL.md) | Make a repository easier to reproduce, maintain and release. | Catalog | Catalog | Catalog |

## Skills, integrations and evaluation

| Type | Capability | Use it for | Codex | OpenCode | Antigravity |
| --- | --- | --- | --- | --- | --- |
| Skill | [doctor](skills/doctor/SKILL.md) | Check a SAGE profile, its installed files and language tools. | Catalog | Catalog | Catalog |
| Skill | [mcp-builder](skills/mcp-builder/SKILL.md) | Design and evaluate a Model Context Protocol server. | Catalog | Catalog | Catalog |
| Skill | [skill-acquisition](skills/skill-acquisition/SKILL.md) | Find, vet and install a reusable skill when the library has a gap. | Catalog | Catalog | Catalog |
| Skill | [skill-maker](skills/skill-maker/SKILL.md) | Author a skill with clear triggers, resources and acceptance checks. | Catalog | Catalog | Catalog |
| Skill | [sage-harness-eval](skills/sage-harness-eval/SKILL.md) | Measure a harness or routing change against a fixed baseline. | Catalog | Catalog | Catalog |
| Skill | [setup-matt-pocock-skills](skills/setup-matt-pocock-skills/SKILL.md) | Configure project-specific conventions used by Matt Pocock's skills. | Catalog · explicit | Catalog · explicit | Catalog · explicit |

## Web applications

| Type | Capability | Use it for | Codex | OpenCode | Antigravity |
| --- | --- | --- | --- | --- | --- |
| Skill | [vercel-react-best-practices](skills/vercel-react-best-practices/SKILL.md) | Find concrete rendering, bundle and data-loading improvements in React. | Catalog | Catalog | Catalog |
| Skill | [sage-webapp-testing](skills/sage-webapp-testing/SKILL.md) | Verify visible web behavior and capture reproducible browser evidence. | Catalog | Catalog | Catalog |

## Security review and static inspection

| Type | Capability | Use it for | Codex | OpenCode | Antigravity |
| --- | --- | --- | --- | --- | --- |
| Skill | [sage-security-audit](skills/sage-security-audit/SKILL.md) | Inspect a codebase for security risks and recommend fixes. | Catalog | Catalog | Catalog |
| Skill | [differential-review](skills/differential-review/SKILL.md) | Assess the security impact of a code change using its history and tests. | Catalog | Catalog | Catalog |
| Skill | [variant-analysis](skills/variant-analysis/SKILL.md) | Find related instances of a known defect for remediation. | Catalog | Catalog | Catalog |
| Skill | [sage-binary-inspection](skills/sage-binary-inspection/SKILL.md) | Identify the format and dependencies of an artifact using static evidence. | Catalog | Catalog | Catalog |
| MCP | [rea](mcp/servers.json) | Inspect packaged artifacts and binary metadata when source is unavailable. | — | Optional | Optional |

## Scientific workflows, data and reporting

| Type | Capability | Use it for | Codex | OpenCode | Antigravity |
| --- | --- | --- | --- | --- | --- |
| Skill | [nextflow](skills/nextflow/SKILL.md) | Inspect and maintain Nextflow pipelines and their process boundaries. | Catalog | Catalog | Catalog |
| Skill | [pysam](skills/pysam/SKILL.md) | Work with alignment and variant files using pysam. | Catalog | Catalog | Catalog |
| Skill | [biopython](skills/biopython/SKILL.md) | Read, transform and validate biological data formats with Biopython. | Catalog | Catalog | Catalog |
| Skill | [sage-genomics](skills/sage-genomics/SKILL.md) | Inspect sequencing pipelines, file processing and QC outputs. | Catalog | Catalog | Catalog |
| Skill | [fair-data-principles](skills/fair-data-principles/SKILL.md) | Check scientific data for findability, accessibility and reuse. | Catalog | Catalog | Catalog |
| Skill | [statistical-data-visualization](skills/statistical-data-visualization/SKILL.md) | Choose appropriate statistical plots and check how they encode data. | Catalog | Catalog | Catalog |
| Skill | [sage-results-package](skills/sage-results-package/SKILL.md) | Assemble reproducible outputs, figures and provenance into a results package. | Catalog | Catalog | Catalog |
| Skill | [sage-scientific-report](skills/sage-scientific-report/SKILL.md) | Produce a scientific report with traceable analyses and figures. | Catalog | Catalog | Catalog |
| Brief | [scientific-workflows](agents/scientific-workflows.md) | Give the active assistant or a user-selected native agent a sequencing QC review brief. | Manual | Manual | Manual |
