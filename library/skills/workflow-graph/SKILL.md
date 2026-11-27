---
name: workflow-graph
description: Trace a repository's architecture, workflow, control flow or data flow from source and render editable Graphviz DOT, SVG diagrams and an offline guide. Use for requests to map a project or refresh an existing workflow diagram.
---

# Workflow graph

Start with the question the diagram should answer. For a system overview, follow a real input from an entry point to an observable result. For architecture, show which component owns each decision and which artifacts cross its boundary. Reuse the project's diagram directory and source format when updating existing work.

## Trace the implementation

- Find the actual entry points in commands, routes, build targets, job definitions or installer scripts. Read the callers and the configuration they load. A directory name alone establishes containment, not execution.
- Trace one ordinary path all the way through. Record the files or symbols behind each important edge. Identify who writes a file, who reads it, and when. For queues or hooks, distinguish registration from the later event that invokes the handler.
- Follow consequential branches through their outcomes, including fallback, retry, failure, cleanup and restore when present. Use tests or a small observed run to check the surprising parts. Mark an inferred boundary in the notes if the implementation is external or unavailable.
- Choose detail views where another diagram answers a different question. Keep the overview readable at README width. Repeated instances with the same behavior can share one node.

## Draw and publish within the repository

Use Graphviz `dot` for directed workflows. Choose a stable identifier and a short verb phrase for each operation. Label decision edges with their actual condition. Use a consistent direction and explicit arrow labels where dependency and data movement could be confused. Use shape or text as well as color. A feedback loop should identify what triggers the next pass.

Number workflow nodes in the visible label, starting at `1 ·` in each view. Use consecutive stages along the ordinary path. Give alternatives or simultaneous operations the same number with letters, such as `3a ·` and `3b ·`. Label the arrows with the condition or say that both execute. A merge takes the next whole number. Draw a retry back to the original numbered step and name the condition. Keep step numbers separate from stable node IDs and URLs. For structural components with no execution order, group them as inputs to their first operation or use a separate, explicitly structural view.

Give each important decision a source link in a nearby text key or detail view. Prefer repository-relative paths and named symbols, which survive line movement. For a requested single diagram, an editable DOT file and readable SVG can suffice. For a navigable set, use the bundled [renderer](scripts/render.py) with a manifest alongside the DOT sources.

```text
docs/architecture/
  workflow.json
  overview.dot
  activation.dot
```

```json
{
  "title": "Project workflows",
  "numbered": true,
  "views": [
    {
      "id": "overview",
      "title": "System overview",
      "description": "Follow a request from intake to the stored result.",
      "evidence": [{"label": "Request entry point", "path": "../../src/app.py"}]
    },
    {
      "id": "activation",
      "title": "Activation",
      "description": "See how configuration becomes active."
    }
  ]
}
```

A workflow node can be written as `parse [label="1 · Parse request"]`. With `"numbered": true`, rendering and checking verify the visible numbers, consecutive stages and unique branch labels in every view. The viewer numbers its navigation by manifest order.

An ID names its DOT file, SVG and viewer section. Link an overview node to a detail with `URL="index.html#activation", target="_top"`. Use relative local files for evidence. To render, run `python3 <skill-dir>/scripts/render.py docs/architecture` from the target checkout with Graphviz on PATH. Each diagram directory holds one manifest. Regeneration retires intact, previously generated previews when their views are removed. Commit the editable sources, manifest and requested previews together. The generated HTML embeds its diagrams for offline reading. Source and evidence links work alongside the repository. The same command with `--check` verifies saved outputs without requiring matching fonts or a local Graphviz installation.

## Acceptance

Compare each arrow with its source or test. Inspect the actual SVG at the intended size for clipped labels, ambiguous crossings and unreadable text. Open the viewer locally, follow at least one overview-to-detail link and check that the keyboard navigation and source paths work. Put the overview in the project's normal documentation entry point and record the regeneration command. Describe important unverified external behavior in the text beside the graph.
