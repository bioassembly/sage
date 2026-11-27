# Skill provenance

The package manifest records the repository, revision, file hashes and license information for each vendored skill. The source lock also records reviewed tool versions. The functional index shows which clients select each package. [Package manifest](third_party/lock.json) · [Source lock](sources.lock.json) · [Third-party notices](THIRD_PARTY_NOTICES.md) · [Functional index](INDEX.md)

| Source | Material used in SAGE |
| --- | --- |
| DietrichGebert/ponytail | Ponytail implementation and response guidance. |
| mattpocock/skills | Design interviews, domain modeling, specifications, tickets, codebase design and project setup. The pinned `grill-with-docs` package uses both `grilling` and `domain-modeling`. |
| obra/superpowers | Debugging, test-driven development, worktrees and verification. |
| anthropics/skills | MCP authoring and browser testing. The MCP evaluation helper contains a recorded patch to return a result for every tool request. |
| K-Dense-AI/scientific-agent-skills | Nextflow, pysam and Biopython workflows. |
| trailofbits/skills | Differential review and variant analysis. |
| vercel-labs/agent-skills | React performance guidance. The manifest records compatibility file aliases. |
| rtk-ai/rtk | Optional terminal-output filtering and its native hooks. |

## Locally maintained work

SAGE maintains its profile-aware workflows and the plain-language scientific review brief. The skill-authoring workflow draws on Anthropic and Superpowers guidance. Repository-maintenance guidance also draws on Papers with Code and nf-core conventions. The FAIR data workflows draw on the FAIR principles described by Wilkinson and colleagues.

The workflow graph skill and renderer are maintained here under the repository license. The SangerAnalyst API diagrams informed the overview, detail views and offline navigation. Rendering tests cover both the SAGE diagrams and an independent example project.

When adding or updating an external package, record its source, revision, license, upstream file hashes and any local patches in the appropriate manifest. Retain required notices with the package.
