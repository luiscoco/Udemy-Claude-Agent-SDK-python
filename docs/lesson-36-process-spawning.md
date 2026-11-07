# Lesson 36: Process spawning

The pinned lesson asks the host to control a child launch while preserving the SDK stream. The installed Python SDK exposes `ClaudeSDKClient` and a transport interface but no public custom-spawner option. This Python exercise therefore launches an owned host child and runs a separate real SDK CLI turn. The host child does not transport SDK messages.

`probe_child` launches a fixed Python script with `create_subprocess_exec`, explicit argv, one of two local cwd aliases, and separate stdout and stderr pipes. `FrameTap` buffers split JSONL frames and forwards every original byte chunk. A passing report requires init, host_tool and done frames, `HOST_OK_36`, byte equality, clean exit, reaped child, and a successful matching SDK session with `SPAWN_OK_36`. Timeout and cancellation verify cleanup while failing the success check. Failed launch records its error. The dry route only shows planned options.

The controls are action and location. `/api/c36` exposes state, dry plan, run, alias, debug, failures, reset and three source excerpts. `machine-a` and `machine-b` are directories on this machine; neither is a remote host. Offline mode uses explicitly recorded SDK fixtures but still starts the actual host child. Live mode makes a bounded provider-backed SDK turn. Seven explained questions cover the process, tap, failure and dry-run boundaries.

The live smoke report is `.lab-data/lesson-live-smoke/lesson-36-20261103T200504332493Z/report.json`: success and stderr passed; failed launch, timeout and cancellation correctly required review. Native SDK spawn replacement and remote launch remain unsupported adaptations. Recorded narration and visuals remain separate media work.
