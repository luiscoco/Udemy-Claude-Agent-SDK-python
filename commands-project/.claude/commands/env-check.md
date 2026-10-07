---
description: Reports the Python version and the data files, collected by shell commands before the model runs.
allowed-tools: Bash(python --version:*)
---

These lines were produced by shell commands when the command was expanded:

- Python: !`python --version`
- Data files: !`ls data`

Answer with exactly this layout, using the values above, and nothing else:

```
🧪 Env check
python: {version}
data: {file names, comma-separated}
```
