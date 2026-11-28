# Profile and installation contracts

A profile selects ordered lists of core skills, catalog skills, default MCP servers, optional MCP servers and LSP servers. The three profiles inherit `core` and `catalog` from [the shared skill defaults](../library/default-skills.json). Set either list in a client's `profile.json` to replace that list for that client. Catalog skills require a routing rule. A profile can override rule fields or clear an inherited field with JSON null. The functional index reflects the resolved profiles.

Core contains three short, reusable workflows for scoped implementation, checkpoints and concise work. Catalog covers task-specific workflows such as debugging, code review and token analysis. Each default profile uses one primary skill per workflow. The library includes additional variants that can be selected for a project with different needs.

| Client | MCP defaults | Language tooling |
| --- | --- | --- |
| Codex | Native tools at startup. Context7, DeepWiki and Serena are opt-ins whose tools are available through deferred discovery. | The profile can provision Python, shell, YAML, TypeScript and Markdown servers for separate use. |
| OpenCode | Context7 for version-specific documentation. DeepWiki, Serena and REA are opt-ins. | Native registrations for all eight shared definitions. The client starts a server for matching files. |
| Antigravity | Context7 for version-specific documentation. DeepWiki, Serena and REA are opt-ins. | The profile can provision Python, shell, YAML, TypeScript and Markdown servers for separate use. |

Context7 and DeepWiki use remote endpoints. Serena is most useful when a task needs symbol operations beyond the client's existing tools. Serena has its own language configuration. Upgrades retire an unchanged MCP registration that was removed from defaults. An explicit `--mcp NAME` choice and custom registration fields persist across upgrades.

Installation builds a native config in memory. Codex uses its app-server to merge TOML. OpenCode and Antigravity merge JSON and preserve existing settings. OpenCode adds skill packages to its native editor when an ID is free. An existing personal or project skill keeps precedence. The OpenCode local provider preset requires an explicit provider option. A role brief is library documentation and has no native registration. [OpenCode skill editor](https://opencode.ai/docs/build/plugins/server/#skills)

In the default catalog install, Codex routes at session start and on user prompts. OpenCode and Antigravity use their native plugin events. OpenCode supplies prompt matches to the current request and registers workspace matches with the native skill editor. SAGE reads `disable-model-invocation` frontmatter and the `agents/openai.yaml` implicit-invocation policy when compiling the manifest. Either policy can require a direct request. Use `$grill-with-docs` or “Run a design interview” to request the interview and its glossary and questioning companions. Named skill requests take priority over incidental words in the same prompt. [Codex hook events](https://developers.openai.com/codex/hooks/) · [Routing cases](../evals/routing.json)

The router matches prompt prose and skips Markdown quotes and fenced blocks. Workspace scans follow regular files within the selected roots and read at most 16 KiB from each manifest. Codex restores the active skill hints after context compaction. A direct skill request can surface the same skill again on a later turn. The Python hooks remember the workspace signature and rescan when a session changes roots. [Codex session-start contract](https://learn.chatgpt.com/docs/hooks#sessionstart)

Activation stages files, saves a private before/after journal and rolls back completed writes if a write fails. Restore preflights conflicts across the journal and can resume after an interruption. During an upgrade, a matching journal can release a former agent override or restore the personal file it replaced. Unrecorded definitions, edits made after installation and ambiguous ownership stay with the user.

The shared index checker enforces a purpose and group for every capability. The numbered diagrams link to implementation evidence. Profile integration tests exercise an isolated install and restore. Native smoke checks exercise client discovery, and the LSP checks request an initialization handshake from the selected executables. [Numbered architecture](architecture/README.md)
