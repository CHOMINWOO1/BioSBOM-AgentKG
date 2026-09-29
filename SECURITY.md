# Security and public-data boundary

- `.env`, private inputs, keys, run directories and service databases are excluded by `.gitignore`. Already tracked files require a separate content scan; ignore rules alone do not sanitize them.
- The examples contain synthetic assets and either explicitly synthetic advisories or factual extracts from public OSV records. They contain no patient data, internal inventories or production addresses.
- The default mode performs no network calls. Model-backed mode sends typed package, vulnerability and asset-context information to the explicitly configured provider. Use only data you are authorized to send there.
- API credentials are read from `BIOSBOM_API_KEY`, sent only in the authorization header and omitted from run artifacts. Remote endpoints require HTTPS; redirects are rejected to prevent forwarding credentials elsewhere.
- Advisory descriptions are excluded from prompts. All model output is untrusted, schema-validated and independently checked. These measures reduce exposure but are not a proof against all prompt-injection attacks.
- HTML values are escaped; the report contains no JavaScript or remote resources. CSV input-controlled cells are protected against common spreadsheet formula prefixes.
- Status `affected` means an explicit version match in the supplied advisory, not demonstrated exploitation or runtime reachability. Unknown versions and unsupported ranges retain review status.
- This tool proposes triage priorities. It never executes shell commands, upgrades packages, changes infrastructure or sends messages as an agent action.
- Saved input files can contain sensitive information if a user supplies it. Keep `runs/` local and protect the folder. Hashes are not anonymization, signatures or access control.

Remaining work: authenticated reviewers, signed snapshots, OSV range interpreters with ecosystem-specific tests, larger independent labels, and live-model evaluations with measured usage. If a real credential has already been exposed, remove it from publication and rotate it; adding an ignore rule cannot undo exposure.
