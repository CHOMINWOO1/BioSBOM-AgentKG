# External reviewed-reference evaluation and independent human review

## 결과 요약 — 공개 검토 자료 기준 평가 완료

2026-09-29에 기존 개발 패널과 advisory ID가 겹치지 않는 10개 패키지·40개 버전 사례를 평가했다. **GitHub reviewed advisory 조회 결과와 BioSBOM 판정이 40/40 일치**했다. 영향 있음 20개, 해당 advisory 범위 밖 20개이며 오탐·미탐·판정 보류는 각각 0개였다.

**실제 신규 전문가 참여자는 0명이다.** GitHub와 OSV가 원천 advisory 정보를 공유하므로 이 결과는 외부 검토 자료와의 버전 판정 일치도다. 독립 전문가 정확도, 취약점 발견 성능, 실제 배포 환경의 보안 정확도 또는 전체 멀티에이전트 성능을 입증하지 않는다. 이 실험의 모델 호출은 0회다.

![External reviewed-reference results](experiments/reviewed-reference-v1.png)

| 외부 기준 / 시스템 판정 | 영향 있음 | 해당 advisory 범위 밖 | 판정 보류 |
|---|---:|---:|---:|
| 영향 있음 | 20 | 0 | 0 |
| 해당 advisory 범위 밖 | 0 | 20 | 0 |

- 전체 일치도 40/40, 판정 커버리지 40/40, 이 표본 내 민감도 20/20·특이도 20/20.
- 패치 경계 주변의 역사적 버전을 선택했다. 무작위 운영 표본이 아니며 같은 advisory의 네 버전은 서로 연관된다. 일반화 성능이나 독립 표본을 가정한 신뢰구간을 제시하지 않는다.
- 각 사례의 입력·정답·조회 시각·출처 해시와 오탐/미탐 목록을 공개했다. 오류 목록이 비어 있다는 사실은 이 40개 사례에만 해당한다.
- 실제 전문가용 양식과 두 평가자 채점 도구는 준비했으며, 인간 평가 결과는 아직 없다. 평가자 원답변·신원·연결표는 기본적으로 Git에서 제외되는 `private/`에 저장한다.

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

## Selected advisories

| Package | Advisory | Versions (ordered) | Agreement |
|---|---|---|---:|
| joblib | [GHSA-6hrg-qmvc-2xh8](https://github.com/advisories/GHSA-6hrg-qmvc-2xh8) | 1.1.0, 1.1.1, 1.2.0, 1.3.0 | 4/4 |
| scikit-learn | [GHSA-jxfp-4rvq-9h9m](https://github.com/advisories/GHSA-jxfp-4rvq-9h9m) | 0.24.2, 1.0, 1.0.1, 1.0.2 | 4/4 |
| scipy | [GHSA-xp76-357g-9wqq](https://github.com/advisories/GHSA-xp76-357g-9wqq) | 0.11.0, 0.12.0, 0.12.1, 0.13.0 | 4/4 |
| torch | [GHSA-47fc-vmwq-366v](https://github.com/advisories/GHSA-47fc-vmwq-366v) | 1.12.1, 1.13.0, 1.13.1, 2.0.0 | 4/4 |
| transformers | [GHSA-282v-666c-3fvg](https://github.com/advisories/GHSA-282v-666c-3fvg) | 4.29.1, 4.29.2, 4.30.0, 4.30.1 | 4/4 |
| tensorflow | [GHSA-jfq2-rj7f-9gvf](https://github.com/advisories/GHSA-jfq2-rj7f-9gvf) | 1.5.0, 1.5.1, 1.6.0, 1.7.0 | 4/4 |
| onnx | [GHSA-ffxj-547x-5j7c](https://github.com/advisories/GHSA-ffxj-547x-5j7c) | 1.11.0, 1.12.0, 1.13.0, 1.13.1 | 4/4 |
| mlflow | [GHSA-vqj2-4v8m-8vrq](https://github.com/advisories/GHSA-vqj2-4v8m-8vrq) | 1.22.0, 1.23.0, 1.23.1, 1.24.0 | 4/4 |
| gradio | [GHSA-rhq2-3vr9-6mcr](https://github.com/advisories/GHSA-rhq2-3vr9-6mcr) | 2.4.5, 2.4.6, 2.5.0, 2.5.1 | 4/4 |
| fastapi | [GHSA-8h2j-cgx8-6xv7](https://github.com/advisories/GHSA-8h2j-cgx8-6xv7) | 0.65.0, 0.65.1, 0.65.2, 0.65.3 | 4/4 |

Candidate exclusions are recorded in provenance; all 10 packages yielded an eligible record.

## Frozen evidence and reproduction

The protocol was committed at `ba8207f` before acquisition. Cases, reference labels, acquisition provenance and protocol were committed at `40ff2f3` before the first prediction. The application source digest manifest was also recorded locally before predictions. At that evaluation, application Python files were identical to the frozen 0.4.2 baseline; no matcher adjustment was made for that result. The later 0.5 implementation has separate [regression results](DISCOVERY_AND_REMEDIATION.md) and does not overwrite this historical panel.

- [Frozen inputs and per-file SHA-256](../benchmarks/reviewed-reference-v1/frozen-inputs.json)
- [Acquisition sources, timestamps and exclusions](../benchmarks/reviewed-reference-v1/provenance.json)
- [External reference labels and exact query URLs](../benchmarks/reviewed-reference-v1/reference-labels.json)
- [Predictions saved before joining reference labels](experiments/reviewed-reference-v1/predictions.json)
- [All 40 rows as CSV](experiments/reviewed-reference-v1/case-results.csv), [summary JSON](experiments/reviewed-reference-v1/summary.json), [errors/abstentions](experiments/reviewed-reference-v1/errors.json)

To reproduce this historical result, use a separate checkout at `da5c2a0` (application still 0.4.2), then install `.[web,dev]`. From that repository root:

```bash
python benchmarks/run_reviewed_reference.py --output runs/reviewed-reference-reproduction
```

Use a new output directory each time. This offline command checks canonical-LF input hashes and frozen application source hashes, then computes predictions before reading the labels. No API key or model connection is required. Future application changes intentionally fail the fixed-baseline check; evaluate such changes as a separate panel rather than replacing this result.

Optional source reacquisition needs GitHub API access through `gh`, public OSV and PyPI access:

```bash
python benchmarks/fetch_reviewed_reference.py --output runs/new-reference-acquisition
```

Live services may revise advisories or releases; reacquisition is a new snapshot, not a guarantee of identical labels. Do not overwrite the frozen files. To regenerate the figure, install matplotlib/numpy and run `python benchmarks/render_reviewed_reference.py`.

## Actual human review: ready, not performed

```bash
python benchmarks/human_review.py prepare --output private/human-review-v1
```

Send only `private/human-review-v1/reviewer-packet.zip` separately to each reviewer. It contains randomly ordered opaque case IDs, advisory inputs and source links, a blank `review.csv`, a blank `reviewer.json`, and instructions. It contains no system predictions, query-derived reference labels or coordinator mapping. The advisory range evidence is intentionally visible: evaluating it is the task. Do not send this report or the public result links before review. The public repository remains discoverable, so exposure declarations are necessary and blinding is not guaranteed.

Retain `coordinator-map.json` privately. Save completed forms in two separate private directories, then run:

```bash
python benchmarks/human_review.py score --mapping private/human-review-v1/coordinator-map.json --reviews private/reviewer-a private/reviewer-b --predictions docs/experiments/reviewed-reference-v1/predictions.json --output private/human-review-score.json
```

The scorer rejects missing/duplicate case IDs, blank answers, unsupported labels, reused reviewer IDs, absent qualifications/declarations, declared prior output exposure and mismatched prediction input hashes. Declarations do not authenticate identity or qualifications; the coordinator must verify expertise and assess conflicts before interpreting results. Raw score output includes reviewer declarations and must remain private until an appropriate de-identified release is prepared.

It reports three-label inter-rater agreement and Cohen's kappa, disagreements, shared uncertainty, determinate consensus coverage, and system agreement on provisional consensus. System abstentions remain errors in the consensus denominator. Unresolved cases remain in total coverage calculations; no final expert reference standard is claimed without documented adjudication. No synthetic test response is included in the research results.

The present deliverable finishes the public-reference stage requested while no human reviewers are available. Actual independent human evaluation remains pending; multi-user service work is outside the requested scope.
