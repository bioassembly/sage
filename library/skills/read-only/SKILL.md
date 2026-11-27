---
name: read-only
description: Trace a code path, configuration or failure while keeping an investigation read-only.
---

Start at the user-visible symptom or entry point. Locate relevant files and symbols using read-only tools. Follow the callers and inspect the smallest data or test fixture that explains the behavior. Keep file writes, dependency installation and running state-changing jobs outside a read-only investigation. Return the evidence, file locations and any uncertainty that needs a separate test.
