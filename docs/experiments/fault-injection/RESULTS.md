# Controlled orchestration experiment

**All model outputs are scripted fault fixtures. No live LLM was called.**

570 runs; 10 seeds per condition. Deterministic reference: awaiting_human, 0 calls.

The single-pass baseline uses one combined context/triage call and no repair. A single-agent repair baseline uses up to two revisions to control for the effect of feedback. The multi-agent condition uses separate specialists and at most two revisions per stage. Both use the same verifier. This design measures recovery with additional calls, not a causal advantage of role separation.

| Architecture | Fault | Persistent | Runs | Accepted | Detected | Repaired | Mean calls |
|---|---|---|---:|---:|---:|---:|---:|
| single_pass | none | False | 10 | 10 | 0 | 0 | 1 |
| single_with_repair | none | False | 10 | 10 | 0 | 0 | 1 |
| multi_agent | none | False | 10 | 10 | 0 | 0 | 2 |
| single_pass | missing_citation | False | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | missing_citation | False | 10 | 10 | 10 | 10 | 2 |
| multi_agent | missing_citation | False | 10 | 10 | 10 | 10 | 3 |
| single_pass | missing_citation | True | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | missing_citation | True | 10 | 0 | 10 | 0 | 3 |
| multi_agent | missing_citation | True | 10 | 0 | 10 | 0 | 4 |
| single_pass | unknown_citation | False | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | unknown_citation | False | 10 | 10 | 10 | 10 | 2 |
| multi_agent | unknown_citation | False | 10 | 10 | 10 | 10 | 3 |
| single_pass | unknown_citation | True | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | unknown_citation | True | 10 | 0 | 10 | 0 | 3 |
| multi_agent | unknown_citation | True | 10 | 0 | 10 | 0 | 4 |
| single_pass | omitted_finding | False | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | omitted_finding | False | 10 | 10 | 10 | 10 | 2 |
| multi_agent | omitted_finding | False | 10 | 10 | 10 | 10 | 3 |
| single_pass | omitted_finding | True | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | omitted_finding | True | 10 | 0 | 10 | 0 | 3 |
| multi_agent | omitted_finding | True | 10 | 0 | 10 | 0 | 4 |
| single_pass | duplicate_finding | False | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | duplicate_finding | False | 10 | 10 | 10 | 10 | 2 |
| multi_agent | duplicate_finding | False | 10 | 10 | 10 | 10 | 3 |
| single_pass | duplicate_finding | True | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | duplicate_finding | True | 10 | 0 | 10 | 0 | 3 |
| multi_agent | duplicate_finding | True | 10 | 0 | 10 | 0 | 4 |
| single_pass | unsupported_status | False | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | unsupported_status | False | 10 | 10 | 10 | 10 | 2 |
| multi_agent | unsupported_status | False | 10 | 10 | 10 | 10 | 3 |
| single_pass | unsupported_status | True | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | unsupported_status | True | 10 | 0 | 10 | 0 | 3 |
| multi_agent | unsupported_status | True | 10 | 0 | 10 | 0 | 4 |
| single_pass | priority_downgrade | False | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | priority_downgrade | False | 10 | 10 | 10 | 10 | 2 |
| multi_agent | priority_downgrade | False | 10 | 10 | 10 | 10 | 3 |
| single_pass | priority_downgrade | True | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | priority_downgrade | True | 10 | 0 | 10 | 0 | 3 |
| multi_agent | priority_downgrade | True | 10 | 0 | 10 | 0 | 4 |
| single_pass | context_omission | False | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | context_omission | False | 10 | 10 | 10 | 10 | 2 |
| multi_agent | context_omission | False | 10 | 10 | 10 | 10 | 3 |
| single_pass | context_omission | True | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | context_omission | True | 10 | 0 | 10 | 0 | 3 |
| multi_agent | context_omission | True | 10 | 0 | 10 | 0 | 3 |
| single_pass | schema | False | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | schema | False | 10 | 10 | 10 | 10 | 2 |
| multi_agent | schema | False | 10 | 10 | 10 | 10 | 3 |
| single_pass | schema | True | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | schema | True | 10 | 0 | 10 | 0 | 3 |
| multi_agent | schema | True | 10 | 0 | 10 | 0 | 4 |
| single_pass | transport | False | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | transport | False | 10 | 10 | 10 | 10 | 2 |
| multi_agent | transport | False | 10 | 10 | 10 | 10 | 3 |
| single_pass | transport | True | 10 | 0 | 10 | 0 | 1 |
| single_with_repair | transport | True | 10 | 0 | 10 | 0 | 3 |
| multi_agent | transport | True | 10 | 0 | 10 | 0 | 4 |

## Limits

Fault fixtures deliberately return corrected output after feedback in transient conditions. That is a controlled recovery assumption, not evidence that an actual model repairs itself. Seeds choose fault targets, not independent datasets. Calls count transport attempts. Local durations exclude model inference and network latency. Token reservation is not measured token usage or monetary cost. No ranking accuracy or clinical/security effectiveness claim follows from these results.
