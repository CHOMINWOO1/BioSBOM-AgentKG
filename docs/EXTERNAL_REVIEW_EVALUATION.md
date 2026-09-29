# External reviewed-reference evaluation and independent human review

## Evaluation status and scope

This study separates two tasks:

1. **External reviewed-reference agreement:** compare the frozen BioSBOM version matcher with GitHub's reviewed-advisory package/version query. Labels come from an external service, not BioSBOM's own matcher or policy. GitHub curator review is not a new expert review of BioSBOM.
2. **Independent human evaluation:** qualified reviewers receive system-blinded cases and submit their own labels and evidence. No human review is counted until actual responses are supplied. Model-generated labels cannot stand in for expert participants.

OSV and GitHub can share the same underlying advisory curation. Therefore the first task measures consistency with externally curated affected-version information, not independent vulnerability discovery, exploitability, remediation priority, clinical safety or full multi-agent accuracy. The second task requires actual human participation and remains pending until completed.

## Fixed prospective protocol

- Freeze application implementation at `29f15ec795e92e4ed1da827d03a801d568e9a28b` (0.4.2). Do not change the matcher in response to this evaluation.
- Candidate Python research/ML packages, fixed before predictions: joblib, scikit-learn, scipy, torch, transformers, tensorflow, onnx, mlflow, gradio, fastapi.
- For each package, query the first 100 GitHub-reviewed advisories in ascending publication order, published through 2025-12-31. Select the earliest non-withdrawn record with a reviewed timestamp, a stable patched version published on PyPI, and no GHSA/CVE overlap with prior BioSBOM benchmark/example/experiment files.
- Choose the two preceding and the patched and next stable PyPI releases, when available. Do not choose cases according to BioSBOM predictions or force an assumed positive/negative balance. Log exclusions and actual label balance.
- Ask GitHub's advisory query for each exact package/version and advisory ID. Its presence means affected; absence means outside **that advisory**, not generally safe. Preserve retrieval times, query URLs, response hashes and projected source fields.
- Supply BioSBOM with the corresponding OSV advisory projection and a synthetic deployment context. Reference labels, GitHub vulnerable-version strings and reviewer answers are not passed to the matcher. Freeze inputs and labels before the first prediction.
- Disclose shared-curation dependence. Cases are new to this project's recorded panels, not necessarily unseen in foundation-model training. No model is called in this matcher-only reference evaluation.
- Report all cases, false positives, false negatives, abstentions, coverage and package-level counts. Boundary samples are selected cases, not prevalence estimates; correlated versions must not be presented as independent clinical observations.

## Human review protocol

Use at least two independent reviewers with relevant software-security or bioinformatics infrastructure expertise. Give each the same case materials without system output, reference answers or the other reviewer's decisions. Randomize opaque case IDs. Ask about version affectedness separately from confidence, rationale, source references and any operational priority opinion. The latter requires real deployment information and is outside this synthetic panel's accuracy claims.

Record pseudonymous reviewer ID, relevant expertise, conflicts and independence declaration. Do not invent reviewers, credentials or agreement. Keep participant identity and raw responses local by default. Independent agreements form a provisional consensus; unresolved disagreements remain reported and require documented adjudication for a final reference label. Report both coverage and disagreements, not just agreed cases.

Public benchmark results are visible in this repository, so a reviewer must receive only the separate blinded packet and disclose prior exposure. This is system-output blinding, not a guarantee that public advisory knowledge is hidden.

## Sources and attribution

- [GitHub Advisory Database](https://github.com/github/advisory-database): reviewed records are maintained by its security advisory curation process; OSV data may share this source. Database facts are attributed to GitHub and contributors under [CC BY 4.0](https://github.com/github/advisory-database/blob/main/LICENSE.md).
- [Global security advisory API](https://docs.github.com/en/rest/security-advisories/global-advisories): package/version filters provide the external reference response.
- [OSV](https://osv.dev/): runtime advisory-format snapshot. No unsupported claim of source independence is made.

Results and reviewer participation status will be appended after acquisition and evaluation.
