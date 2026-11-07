# Lesson 43 lab walkthrough brief

1. Open `/api/c43/facts` and identify the fixed local actions, transports, tools and resource URIs.
2. Run local `auth`; inspect 401 for absent, foreign and expired credentials, 400 for missing initialize, and 404 for an unknown session. Follow the four discovery and grant steps.
3. Run `cache` and compare credential-1 before revocation with credential-2 after a new grant. Verify the old credential receives 401 and the incident resource is visible to the new host client.
4. Compare HTTP and SSE, the `find_order` resource link, and a runbook or order read. Match the returned digest and byte length to the resource handler log.
5. Use local `/api/c43/live` with `step=tool`, `resource`, then `rotate`; each is a host-only rehearsal with `agent_executed=false`.
6. With fresh live consent, inspect the provider-backed tool and resource calls, exact SDK IDs, authenticated wire marker/RPC ID, handler receipt, successful terminal, and connection cleanup.
7. Inspect the additional same-client reconnect action over HTTP or SSE. Its two turns share a session and credential label. Contrast that with the failed config-file rotation probe: reconnect kept the revoked header, so live `step=rotate` remains unavailable.
