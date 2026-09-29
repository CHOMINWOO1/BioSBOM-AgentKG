# Context citation ablation — protocol

The 0.4 development panel exposed missing context citations when concerns were empty. An empty concern list still requires the input snapshot as evidence. Version 0.4.1 makes that contract explicit in the model payload; the schema, policy thresholds and independent verifier are unchanged. No output is silently repaired by inserting citations.

## Fixed design

- Eight synthetic deployment cases in [the panel](../benchmarks/citation-panel-v041.json), fixed before calls: range-only, missing version, GIT-only, empty advisory lists and mixed public/synthetic findings; context thresholds cover empty, boundary and nonempty concerns.
- Two architectures × two citation contracts × eight cases × one repeat = **32 runs**. Shuffle seed 1741 interleaves all conditions. Every role requests the same configured model.
- `v04_original` removes only the new `context_citations` field. Initial payload hashes are tested against payloads generated from published commit `466806925ff004e4a9b2d5bb87ebdf7a1d27424d`. `explicit_citations` uses the current payload.
- Same schema, verifier, transport and budgets: six calls/run, two revisions/stage, 2,000 output tokens/call, 12,000 output-token reservation/run. Worst-case authorization: 192 calls; not a monetary cap.
- Primary measurement: verified completion without repair, reported separately by architecture and contract. Secondary measurements: final acceptance, context-evidence verifier events, total calls, reported tokens and elapsed time. A first-stage pass compares different stage content across architectures and is not a common accuracy metric.
- Retain every failure and intermediate attempt. No extra repeats selected after observing results. Calls may incur charges; no live calls in CI.

## Interpretation limits

This is a targeted development ablation informed by an observed failure, not independent held-out evaluation or a preregistered scientific study. Contexts are controlled mutations, not measured biological deployments. One repeat per cell and a requested model alias cannot establish statistical significance or generalize to other models. The deterministic verifier defines contract acceptance, not exploitability or scientific correctness.

The engine's event input hashes identify its payload before the ablation adapter. `calls.json` records the digest of the **actual transmitted** payload, role, schema and call settings, and attributes each call to its run and contract. No provider URL, key or header is published.

```bash
# Configure BIOSBOM_MODEL, BIOSBOM_BASE_URL, BIOSBOM_API_KEY locally.
# The recorded model experiment uses BIOSBOM_API_STYLE=responses.
python benchmarks/run_citation_ablation.py --cases benchmarks/citation-panel-v041.json --output runs/citation-ablation --max-total-calls 192 --confirm-live
```

Results will be appended after the fixed run finishes; the previous [0.4 results](RESEARCH_EVALUATION.md) remain separately identifiable.
