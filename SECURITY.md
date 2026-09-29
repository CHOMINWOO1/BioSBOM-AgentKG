# Security and public-data boundary

- `.env`, private inputs, keys, run directories and service databases are excluded by `.gitignore`. Already tracked files require a separate content scan; ignore rules alone do not sanitize them.
- The examples contain synthetic assets and either explicitly synthetic advisories or factual extracts from public OSV records. They contain no patient data, internal inventories or production addresses.
- The default mode performs no network calls. Model-backed mode sends typed package, vulnerability and asset-context information to the explicitly configured provider. Use only data you are authorized to send there.
- API credentials are read from `BIOSBOM_API_KEY`, sent only in the authorization header and omitted from run artifacts. Remote endpoints require HTTPS; redirects are rejected to prevent forwarding credentials elsewhere.
- Advisory descriptions are excluded from prompts. All model output is untrusted, schema-validated and independently checked. These measures reduce exposure but are not a proof against all prompt-injection attacks.
- HTML values are escaped; the report contains no JavaScript or remote resources. CSV input-controlled cells are protected against common spreadsheet formula prefixes.
- Status `affected` means an explicit version or supported release-range match in the supplied advisory, not demonstrated exploitation or runtime reachability. Unknown versions and unsupported ranges retain review status.
- This tool proposes triage priorities. It never executes shell commands, upgrades packages, changes infrastructure or sends messages as an agent action.
- Saved input files can contain sensitive information if a user supplies it. Keep `runs/` local and protect the folder. Hashes are not anonymization, signatures or access control.

Remaining work: authenticated reviewers, signed snapshots, additional ecosystem range interpreters, larger independent labels, and larger held-out live-model evaluations beyond the published 24-run development panel. If a real credential has already been exposed, remove it from publication and rotate it; adding an ignore rule cannot undo exposure.

## Local web workbench (0.4)

- The CLI binds only to 127.0.0.1. Allowed Host values are the configured localhost/loopback port; cross-origin requests and cross-site fetches are refused.
- A signed random, HttpOnly, SameSite=Strict session cookie and a per-session CSRF token protect mutations. The cookie is HTTP-only loopback and is not a remote authentication mechanism. Sessions rotate when the server restarts.
- The UI has no third-party scripts, fonts, analytics or CDN dependencies. CSP disallows inline scripts and framing. Source documents are rendered with textContent, never HTML injection.
- Requests are bounded to 2 MB; the queue and matching workload are bounded. Download filenames are allowlisted and artifact integrity is rechecked before viewing, export or human review.
- The SQLite database, worker lock, inputs, events and reviews stay under the ignored runs directory. File permissions and disk encryption remain the local operator's responsibility. Unsigned manifests detect accidental edits, not a malicious owner rewriting all files.
- The service is not hardened for shared machines, authenticated multi-user review or internet exposure. A local malicious process with the same OS access can use the service. Do not reverse-proxy it publicly as an authenticated application.
- Cancellation is cooperative. An already dispatched provider call may continue and incur usage until it returns or times out. Queued LLM jobs are persisted; restarting the server continues queued jobs, while interrupted running jobs require an explicit retry.
