---
name: doctor
description: Check the SAGE profile, installed files and language-tool availability for a native client.
---

From the SAGE checkout, run `python3 sage.py doctor CLIENT` for the requested client. Pass `--home PATH` for an isolated installation. For questions about profile selection or language tools, also run `python3 sage.py show CLIENT` and `python3 sage.py lsp CLIENT --check`. Report the first failing path or executable, the observed result and its effect. Live service availability requires a separate check with the native client.
