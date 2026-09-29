# Validation record — 0.4.2

- Local Python 3.12: **146 tests passed**, plus **5 Node UI state tests**; Ruff and JavaScript syntax pass. Policy cases cover missing/zero CVSS, uncertain versions and severity/exposure boundaries. The original comparison payload is checked against published 0.4.1 digests.
- UI state tests cover out-of-order record/evidence responses, hidden stale controls after a failed load, immutable review target selection and safe non-JSON errors. They are targeted unit tests, not browser substitutes.
- Real browser: visible CVSS-missing explanation, record-specific review target, default hold decision, model-connection recovery guidance. Review dialog fits a requested 390px viewport (375px content width, 341px dialog) without horizontal overflow. Screenshot uses an existing synthetic deployment and does not submit a human decision.
- Real-model triage ablation: **48 runs / 75 calls / 118,108 reported tokens**. All final audits passed; revised single/multi each 12/12 without repair. Original multi had three review-required corrections. Single-token and multi-latency regressions are reported rather than hidden.
- All 48 saved run manifests and public trace totals verified. The 0.4.2 wheel was built with UI/example assets. Local original inputs and prior experiment exports are retained.
- Cross-platform release CI is recorded after publication. Prior experiments below retain their original interpretation; no cross-panel accuracy pooling.

## Historical validation — 0.4.1

- Local Python 3.12: **133 tests passed**; Ruff and JavaScript syntax pass. The five additional cases verify original 0.4 payload hashes, empty-concern citation rejection, run pairing, trace attribution and pre-dispatch budget refusal.
- Built the 0.4.1 wheel. Package, API and UI version metadata are synchronized; the previously stale Python `__version__` was corrected.
- Targeted real-model ablation: **32 runs / 59 calls / 84,555 reported tokens**. All final audits passed. No-repair completion: single 5/8→8/8, multi 3/8→7/8. Context-evidence verifier events: 9→0. One revised-contract triage required review-priority repair.
- All original run manifests verified. Public export aggregate checks reconcile per-run trace counts, tokens and audit decisions. See [methods, failures and raw data](docs/CITATION_ABLATION.md).
- The previous 0.4 panel is preserved below. This is a new controlled development ablation, not an independent accuracy benchmark. Implementation commit `74f6e4d8df0828959c0e9da5255663738a7e3598` passed all four Windows/Ubuntu x Python 3.11/3.12 jobs: [0.4.1 CI](https://github.com/CHOMINWOO1/BioSBOM-AgentKG/actions/runs/36537137487). Subsequent documentation-only updates do not alter the tested code. The local web server was restarted with all four existing records preserved and a healthy worker; UI metadata reports 0.4.1.

## Historical validation — 0.4

- Local Python 3.12: **128 tests passed**. Includes version boundaries, frozen 0.3 artifact verification, preview behavior, Responses strict-schema handling, usage accounting, evidence/orchestration/storage, web boundaries and durable queue behavior.
- Built the 0.4 wheel: all three UI assets, both example fixtures and the version matcher are included.
- Ruff passes; JavaScript syntax checked with `node --check`.
- Public-source corpus: **72/72 expected contracts**. Eight fixed-version boundaries now produce no candidate instead of an ambiguous candidate; unsupported versions remain reviewable.
- Core timing: **90 runs**, 30 per size; all retained eight expected findings and passed verification. HTTP, storage and LLM excluded.
- Real provider main panel: **24 runs / 48 calls / 72,052 reported tokens**. Single+repair 12/12 and multi+repair 11/12 final acceptance; one failed context-evidence contract blocked. All reported usage known. Pilot 4 runs is recorded separately.
- Scripted fault injection: historical **570 runs**, not a live-model experiment.
- Browser: direct SBOM+OSV upload, preview without a new persisted job, execution, evidence viewing and bundle download. Existing 0.3 browser checks cover review, restart persistence and a 390px viewport. New model retry uses an in-page dialog and preserves the original record. A synthetic web retry completed with two real model calls and 4,135 reported tokens, reaching human-review pending in 10.326 seconds; this manual run is excluded from the research panel.
- One third-party warning: Starlette TestClient deprecates its current httpx transport in favor of httpx2; tests still pass. Transport migration remains maintenance work.

```bash
python -m pip install -e ".[web,dev]"
python -m ruff check src tests benchmarks
python -m pytest -q
node --check src/biosbom_agentkg/web/static/app.js
python benchmarks/run_public_corpus.py --output runs/public-validation --repeats 30
```

The historical 0.3 implementation passed four Ubuntu/Windows × Python 3.11/3.12 jobs: [0.3 CI](https://github.com/CHOMINWOO1/BioSBOM-AgentKG/actions/runs/36531563702). The 0.4 implementation at `dea7ed0bfe3754777ff51170ace3484de3ef90f6` passed all four Ubuntu/Windows x Python 3.11/3.12 jobs, including tests, lint, JavaScript syntax and CLI run/verify/evaluation: [0.4 CI run](https://github.com/CHOMINWOO1/BioSBOM-AgentKG/actions/runs/36536134316). Later documentation-only changes do not alter this tested implementation. The staged publication also passed Gitleaks 8.30.1 and a private-path/credential/internal-address check. Published records were cross-checked against all 48 call traces and token totals.

See [methods and limitations](docs/RESEARCH_EVALUATION.md), [workbench](docs/WORKBENCH.md), and [remaining work](docs/STATUS.md). No independent expert-label accuracy or multi-user deployment claim is made.
