# Working on SAGE

Keep shared capabilities in `library/`. Each directory in `clients/` holds a profile and native adapter files. Read assets directly from their canonical path. Keep the checkout free of symlinks, generated skill mirrors and duplicate vendor manifests.

A client owns its native agents, models, permissions and delegation settings. Store optional role briefs as Markdown in `library/agents/`. Test installation and upgrades in an isolated home. Preserve personal configuration, edited files, local overlays and reversible journals.

Group each capability once in `library/functions.json`. Run `python3 sage.py sync`, `python3 sage.py check` and the affected tests. Update and regenerate the numbered Graphviz views when architecture changes. Preserve upstream licenses and byte-level package checks when refreshing a vendor.
