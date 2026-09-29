# Triage contract evaluation — 0.4.2

## Fixed protocol

The previous citation experiment retained one `review_required` correction. The new payload makes `review` a separate required state and lists allowed priorities/statuses for each finding. It does not change the independent verifier, thresholds, evidence, schema or add automatic output repair.

- [Twelve fully synthetic cases](../benchmarks/triage-panel-v042.json): missing CVSS with low/high context, KEV or EPSS; missing/unsupported versions; zero CVSS; CVSS 6.9/7 and exposure 6/7 boundaries; sensitive critical context.
- [Explicit expected contracts](../benchmarks/triage-expectations-v042.json) are written from the existing policy. These are controlled policy labels, not independent expert judgements. Tests check all four possible priorities against each expectation.
- Twelve cases × two architectures × two payloads × one repeat = **48 runs**, shuffled seed 1741. The original payload is verified against hashes from public commit `cd3c5e6756a72dce71956c25ff854a6ed716fe9b`.
- All roles use the same model. The sole ablation removes `triage_contract` for `v041_original`; context citation guidance is kept in both conditions.
- Six calls/run, two revisions/stage, 2,000 output tokens/call, 12,000 output-token reservation/run; worst-case ceiling 288 calls, not a fee cap.
- Primary outcome: no-repair verified completion, separately by architecture. Also retain final acceptance, review-required verifier events, calls, tokens, elapsed time and every failed attempt. No selective repeats or prompt tuning after this panel starts.

The policy intentionally requires manual review for missing CVSS even if another risk signal exists. This is the application's disclosed policy, not a universal vulnerability-management standard. No measured clinical, exploitability or independent accuracy claim is made. Targeted development cases and one repeat per cell cannot establish statistical significance or eliminate model variability. Rule-based execution remains a relevant zero-model-call baseline.

Engine events hash the pre-adapter payload. The per-call trace identifies the actual transmitted payload digest and the run/condition. No keys, headers or provider URLs are exported. Past panels remain separate.

```bash
python benchmarks/run_citation_ablation.py --comparison triage --cases benchmarks/triage-panel-v042.json --output runs/triage-ablation --max-total-calls 288 --confirm-live
```

Results are appended after all scheduled runs finish.
