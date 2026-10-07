---
paths:
  - "api/**/*.py"
---

# API validation rule

- Marker: 🟧 PATH-RULE (.claude/rules/api-validation.md, loaded only when a file matching api/**/*.py is read)
- Every API handler must validate its input with an explicit validation function before using it.
