# Public advisory snapshot smoke experiment

## Inputs and provenance

- Public OSV records: [PYSEC-2023-74](https://osv.dev/vulnerability/PYSEC-2023-74), [PYSEC-2023-58](https://osv.dev/vulnerability/PYSEC-2023-58).
- [Frozen factual extracts](../../examples/public-snapshot-case.json) include IDs, aliases, modified timestamps and affected-package/version/range fields. Advisory prose is omitted.
- [Acquisition provenance](../../examples/public-snapshot-provenance.json) records API URLs, retrieval time, original-response SHA-256 and the projection applied.
- The six package records and deployment attributes are synthetic. This is not an SBOM extracted from an actual hospital, laboratory or production bioinformatics pipeline.

## Observed result

| Package condition | Disposition | Reason |
|---|---|---|
| requests 2.30.0 | matched | Version explicitly listed in the frozen advisory |
| requests 2.31.0 | ambiguous | Range interpretation intentionally unsupported |
| requests, version missing | version_missing | Insufficient installed-version evidence |
| werkzeug 2.2.2 | matched | Version explicitly listed in the frozen advisory |
| werkzeug 2.2.3 | ambiguous | Range interpretation intentionally unsupported |
| unrelated-example 1.0 | unmatched | No package identity match in the two-record snapshot |

All six components were retained. Five findings were produced. The two explicit version matches have `affected` status; the three uncertain findings remain `under_investigation`. All five have review priority because no numeric severity sidecar was supplied. Severity, EPSS and KEV values were not invented.

The newer versions in this example expose a limitation: a conservative unresolved range can still create a review candidate. The runtime must not be represented as a complete OSV vulnerability scanner. Nor does an unmatched record certify a package as safe.

## Reproduce

```bash
biosbom-agentkg run --case examples/public-snapshot-case.json --output runs/public-snapshot
biosbom-agentkg verify runs/public-snapshot
```

The command reads the checked-in snapshot and performs no network requests. [Recorded dispositions](public-snapshot-dispositions.csv) and [recorded result](public-snapshot-result.json) preserve the observed run.
