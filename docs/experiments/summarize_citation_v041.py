"""Validate and summarize the immutable citation ablation export; no API calls."""
from pathlib import Path
import csv
import json
from statistics import median

ROOT = Path(__file__).resolve().parent / "citation-v041"
rows = json.loads((ROOT / "results.json").read_text(encoding="utf-8"))
calls = json.loads((ROOT / "calls.json").read_text(encoding="utf-8"))
records = json.loads((ROOT / "run-records.json").read_text(encoding="utf-8"))
protocol = json.loads((ROOT / "protocol.json").read_text(encoding="utf-8"))
assert len(rows) == len(records) == len(protocol["schedule"]) == 32
assert len({(r["case_index"], r["architecture"], r["contract"]) for r in rows}) == 32
for row, result in zip(rows, records, strict=True):
    trace = [c for c in calls if c["run"] == row["run"]]
    assert row["calls"] == result["calls"] == len(trace)
    assert row["verified"] == result["audit"]["passed"]
    assert row["reported_tokens"] == result["reported_total_tokens"]
    assert row["reported_tokens"] == sum(c["total_tokens"] or 0 for c in trace)
    assert all(c["contract"] == row["contract"] for c in trace)
groups = []
for architecture in ("single_agent", "multi_agent"):
    for contract in ("v04_original", "explicit_citations"):
        group = [r for r in rows if r["architecture"] == architecture and r["contract"] == contract]
        assert len(group) == 8
        groups.append({
            "architecture": architecture, "contract": contract, "runs": len(group),
            "verified": sum(r["verified"] for r in group),
            "no_repair_completion": sum(r["no_repair_completion"] for r in group),
            "context_evidence_events": sum(r["context_evidence_events"] for r in group),
            "calls": sum(r["calls"] for r in group),
            "reported_tokens": sum(r["reported_tokens"] for r in group),
            "median_seconds": median(r["seconds"] for r in group),
        })
pairs = []
for architecture in ("single_agent", "multi_agent"):
    for case_index in range(8):
        pair = {r["contract"]: r for r in rows
                if r["architecture"] == architecture and r["case_index"] == case_index}
        before, after = pair["v04_original"], pair["explicit_citations"]
        pairs.append({"case": before["case"], "architecture": architecture,
                      "before_no_repair": before["no_repair_completion"],
                      "after_no_repair": after["no_repair_completion"],
                      "before_verified": before["verified"], "after_verified": after["verified"],
                      "calls_delta": after["calls"] - before["calls"],
                      "tokens_delta": after["reported_tokens"] - before["reported_tokens"]})
summary = {"runs": len(rows), "calls": len(calls),
           "verified": sum(r["verified"] for r in rows),
           "reported_tokens": sum(r["reported_tokens"] for r in rows),
           "all_usage_known": all(r["usage_complete"] for r in rows), "groups": groups,
           "limits": ["Targeted development panel, not independent labels", "One repeat per cell",
                      "Requested model alias, no fixed backend revision", "No monetary cost estimate"]}
for filename, content in [("summary.json", summary), ("paired-results.json", pairs)]:
    (ROOT / filename).write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
with (ROOT / "results.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
print(json.dumps(summary, indent=2))
