# Validation record · 2026-09-29

## Executed locally

- 69 pytest tests passed in the original development interpreter and in a newly created Python 3.12 virtual environment after `pip install -e ".[dev]"`.
- The clean environment installed Pydantic 2.13.5, pytest 9.1.1 and Ruff 0.16.9. No hidden original research package was required.
- Ruff checked the selected E4/E7/E9/F/B rules. Test coverage includes false citations, missing/duplicated findings, priority downgrades, unsupported status claims, provider errors, retry exhaustion, budgets, content tampering, blocked approval and immutable human decisions.
- HTTP transport tests use a real loopback HTTP server with scripted responses, including redirects, malformed JSON, truncated completions and error responses. This tests the transport contract, not any actual model.
- Installed CLI: offline `run`, `verify` and a separate public-advisory snapshot run completed. Outputs are synthetic assets and contain no private inventory.
- Controlled experiment: 570 scripted runs, 57 conditions, 10 seeds per condition. Full raw records and grouped CSV accompany the report.

## Not executed / not established

- No real local or paid remote LLM inference; provider behavior under an actual model remains unmeasured.
- No production asset scan, penetration test, clinical input, exploitation or automated remediation.
- No independent ranking gold labels, calibrated risk probabilities, real inference latency or monetary cost results.
- CI is configured for Linux/Windows and Python 3.11/3.12. Local results do not imply that remote CI already passed.

## Reproduce

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check src tests
biosbom-agentkg run --case examples/rnaseq-case.json --output runs/validation
biosbom-agentkg verify runs/validation
biosbom-agentkg evaluate --case examples/rnaseq-case.json --output runs/evaluation --seeds 10
```

Existing output directories are rejected. Use a fresh path for each independent run. Runtime seconds will vary by environment; deterministic decisions and controlled fault counts should remain stable.
