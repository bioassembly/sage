---
name: agentic-coding
description: Plan, implement and verify a scoped coding change across multiple files.
---

Trace the current behavior through its entry point, callers and tests. For a consequential change, record the intended observable outcome, the smallest coherent implementation and a check that would fail if the change were wrong.

Work in verifiable increments. Preserve existing callers and unrelated changes. When verification fails, reproduce it and check the underlying assumption before editing again. Record a short checkpoint if the work spans sessions. Report what changed, what ran and which results still need verification.
