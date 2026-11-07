# Lesson 16: Settings and environment

Choose **None**, **Owned project fixture** or **Owned project and local fixtures** in the lesson experiment. These map to explicit `setting_sources=[]`, `["project"]` and `["project", "local"]`. User settings, arbitrary paths, settings JSON and environment names are not accepted. The generated files contain only a harmless `LAB_SETTINGS_DEMO` variable with the values `project` and `local`; no fixture hooks or permission grants are installed.

The optional environment override supplies `alpha` or `beta` through `ClaudeAgentOptions.env`. Every run gets a private `CLAUDE_CONFIG_DIR` and disables automatic memory. This separates CLI state; it does not sanitize the inherited process environment. Provider credentials can still reach the SDK process, but the experiment never displays them.

The real Python child probe checks the config-directory value, automatic-memory flag and optional demo override. It returns comparisons, not inherited values. **It does not resolve CLI settings files or certify settings precedence.** Disabling the override leaves the demo comparison unknown, rather than inventing a result from project/local settings. The selected source list and the two authored files remain available for inspection.

The bounded automatic check additionally requires a unique, successful Read of the owned `notes.txt`, matching parent initialization and terminal session identity, terminal success and confirmed connection closure. A loaded settings file cannot expand the host's Read-only tool boundary. The check does not prove model adherence or all CLI settings behavior.

Offline runs execute an actual file read and Python child process, with explicitly recorded SDK identities. The missing-evidence, wrong-identity, wrong-environment and unmatched-read scenarios intentionally need review. Live runs collect actual SDK messages in one owning task and close the client after success, authentication failure, cancellation or a failed result. A failed disconnect cannot pass the closure criterion. There are no automatic paid retries.

```shell
uv run agent-lab lesson 16
uv run agent-lab lesson 16 --scenario wrong-environment
uv run agent-lab lesson 16 --lesson-options-file settings-options.json
```

Example options file: `{"sources":"project-local","env_override":true,"demo_value":"beta"}`. The normal `/api/lessons/16/run` route uses the same validated request. Negative scenarios are offline only. Seven explained questions, two hints, a worked challenge, three exact source excerpts and the content-derived seven-section Learning Guide accompany the experiment.

The pinned reference contract could not be retrieved during this implementation, so this is an incremental Python adaptation, not reference certification. Source selection and CLAUDE.md behavior were checked against the [official SDK documentation](https://code.claude.com/docs/en/agent-sdk/modifying-system-prompts). All four current bounded live variants passed on 3 November 2026; see [live acceptance](live-acceptance.md). CLI settings-resolution acceptance, authored media and recorded narration remain pending. Continue with [lesson 17, Checkpointing and rewind](lesson-17-checkpointing.md).
