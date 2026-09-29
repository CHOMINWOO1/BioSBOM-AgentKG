# BioSBOM analysis: public-osv-snapshot-synthetic-deployment

State: **awaiting_human** · Mode: `deterministic` · Synthetic: `True`

`affected` means the installed version is explicitly listed in the input advisory. It does not establish reachability or exploitation. A report is not permission to remediate.

Unmatched packages are not certified safe; advisory coverage is limited to the supplied snapshot.

| Package | Version | Advisory | Match | Status | Priority | CVSS |
|---|---|---|---|---|---|---:|
| requests | 2.30.0 | PYSEC-2023-74 | exact_version | affected | review | None |
| requests | 2.31.0 | PYSEC-2023-74 | ambiguous | under_investigation | review | None |
| requests | unknown | PYSEC-2023-74 | version_missing | under_investigation | review | None |
| werkzeug | 2.2.2 | PYSEC-2023-58 | exact_version | affected | review | None |
| werkzeug | 2.2.3 | PYSEC-2023-58 | ambiguous | under_investigation | review | None |

## Evidence and coverage

Components: 6; findings: 5.
- `requests-affected`: matched
- `requests-newer`: ambiguous
- `requests-unknown`: version_missing
- `werkzeug-affected`: matched
- `werkzeug-newer`: ambiguous
- `unrelated`: unmatched

## Audit

Passed: True

## Runtime

Calls: 0; reserved completion tokens: 0; reported total tokens: 0; usage complete: True; elapsed seconds: 0.000853.

Reservation is a completion-token ceiling, not a dollar budget. Reported total tokens include prompt usage when provided by the backend.

Full citations, input hashes, the dependency graph, and agent transitions accompany this report.
