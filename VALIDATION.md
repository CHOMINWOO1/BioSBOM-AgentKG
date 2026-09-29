# Validation record — 0.3

- Local Python 3.12: **93 tests passed**. Existing evidence/orchestration/provider/storage tests plus durable queue, cross-origin/CSRF, body limits, safe errors, duplicate submissions, restart recovery, directory ownership, cancellation, immutable review, tamper rejection and research budget guards.
- Ruff checks pass; JavaScript syntax checked with `node --check`.
- Built the 0.3 wheel and confirmed all three UI assets and both example fixtures are included.
- Browser: synthetic RNA-seq submit → three findings → advisory evidence → dependency graph → demo review. Restarted server and verified the preserved review. Tested a 390px responsive viewport; document width remained inside the viewport. Screenshots are synthetic demo records, not a real reviewer decision.
- Public-source corpus: **40/40 expected outcomes**, with eight intentionally unresolved fixed-version boundary cases disclosed. Core timing: **90 measured runs**, 30 per size; all retained eight expected findings and passed verification.
- Existing scripted fault injection: **570 runs**. It is not a live-model quality evaluation.
- Live comparison runner: same-model and worst-case total-call constraints tested with mock transport. **No live-provider experiment has been run.**
- One third-party deprecation warning: Starlette's current TestClient supports but deprecates the httpx transport in favor of httpx2. This does not fail these tests; transport migration remains a maintenance task.

```bash
python -m pip install -e ".[web,dev]"
python -m ruff check src tests benchmarks
python -m pytest -q
node --check src/biosbom_agentkg/web/static/app.js
python benchmarks/run_public_corpus.py --output runs/public-validation --repeats 30
```

The GitHub workflow tests Ubuntu and Windows on Python 3.11 and 3.12. The preceding 0.2 implementation passed all four matrix jobs: [recorded CI run](https://github.com/CHOMINWOO1/BioSBOM-AgentKG/actions/runs/36529146656). The 0.3 push has a separate current check; do not use that prior run as proof of newer commits.

See [research methods and limitations](docs/RESEARCH_EVALUATION.md), [workbench behavior](docs/WORKBENCH.md), and [remaining acceptance criteria](docs/STATUS.md).
