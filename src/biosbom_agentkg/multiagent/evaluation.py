"""Controlled fault-injection experiments; no results here represent real model accuracy."""

from __future__ import annotations

import copy
import csv
import random
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

from .engine import run_case
from .models import Case, RunConfig
from .provider import ProviderError, Reply
from .storage import write_json


class FaultProvider:
    """Scripted specialist used only to exercise orchestration and verification."""

    models = {role: "scripted-fault-fixture" for role in ("single", "context", "triage")}

    def __init__(self, fault="none", seed=0, persistent=False):
        self.fault, self.persistent = fault, persistent
        self.rng = random.Random(seed)
        self.injected = False

    def complete(self, role, payload, schema, *, max_tokens, timeout):
        ctx = payload["asset"]
        concerns = [
            code
            for enabled, code in [
                (ctx["data_sensitivity"] >= 7, "sensitive_data"),
                (ctx["exposure"] >= 7, "external_exposure"),
                (ctx["criticality"] >= 7, "critical_asset"),
                (ctx["security_control_score"] <= 3, "weak_controls"),
            ]
            if enabled
        ]
        context = {
            "concerns": concerns,
            "evidence_ids": [
                e["evidence_id"] for e in payload["evidence"] if e["kind"] == "context"
            ],
        }
        triage = {
            "assessments": [
                {
                    "finding_id": f["finding_id"],
                    "status": "affected"
                    if f["match"] in {"exact_version", "range_version"}
                    else "under_investigation",
                    "priority": payload["policy"]["minimum_priorities"][f["finding_id"]],
                    "evidence_ids": list(f["evidence_ids"]),
                }
                for f in payload.get("findings", [])
            ]
        }
        result = (
            context
            if role == "context"
            else triage
            if role == "triage"
            else {"context": context, "triage": triage}
        )
        eligible = role in {"single", "triage"}
        if self.fault == "context_omission":
            eligible = role in {"single", "context"}
        if eligible and self.fault != "none" and (self.persistent or not self.injected):
            self.injected = True
            if self.fault == "transport":
                raise ProviderError("connection_failed")
            if self.fault == "schema":
                return Reply({"unstructured": "invalid response"})
            if self.fault == "context_omission":
                context["concerns"] = []
            else:
                row = self.rng.choice(triage["assessments"])
                if self.fault == "missing_citation":
                    row["evidence_ids"] = []
                elif self.fault == "unknown_citation":
                    row["evidence_ids"].append("advisory:invented")
                elif self.fault == "omitted_finding":
                    triage["assessments"].remove(row)
                elif self.fault == "duplicate_finding":
                    triage["assessments"].append(copy.deepcopy(row))
                elif self.fault == "unsupported_status":
                    row["status"] = (
                        "under_investigation" if row["status"] == "affected" else "affected"
                    )
                elif self.fault == "priority_downgrade":
                    row["priority"] = "normal" if row["priority"] != "normal" else "review"
        return Reply(result)


FAULTS = [
    "none",
    "missing_citation",
    "unknown_citation",
    "omitted_finding",
    "duplicate_finding",
    "unsupported_status",
    "priority_downgrade",
    "context_omission",
    "schema",
    "transport",
]


def evaluate(case: Case, output: Path, seeds: int = 10):
    if not 1 <= seeds <= 100:
        raise ValueError("Seeds must be between 1 and 100")
    if not case.synthetic:
        raise ValueError("Fault-injection evaluation requires an explicitly synthetic case")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    raw = []
    for fault in FAULTS:
        for persistent in [False, True] if fault != "none" else [False]:
            for seed in range(seeds):
                for condition, architecture, revisions in [
                    ("single_pass", "single_agent", 0),
                    ("single_with_repair", "single_agent", 2),
                    ("multi_agent", "multi_agent", 2),
                ]:
                    config = RunConfig(
                        mode="llm", architecture=architecture, max_revisions=revisions
                    )
                    result = run_case(case, config, FaultProvider(fault, seed, persistent))
                    detected = any(
                        e.outcome in {"revision_required", "failed"} for e in result.events
                    )
                    raw.append(
                        {
                            "architecture": condition,
                            "fault": fault,
                            "persistent": persistent,
                            "seed": seed,
                            "status": result.status,
                            "detected": detected,
                            "accepted_after_repair": bool(
                                detected and result.status == "awaiting_human"
                            ),
                            "calls": result.calls,
                            "duration_seconds": result.duration_seconds,
                            "completion_tokens_reserved": result.completion_tokens_reserved,
                            "issue_codes": sorted(
                                {code for e in result.events for code in e.issue_codes}
                            ),
                        }
                    )
    deterministic = run_case(case)
    groups = defaultdict(list)
    for row in raw:
        groups[row["architecture"], row["fault"], row["persistent"]].append(row)
    summary = []
    for (architecture, fault, persistent), items in groups.items():
        values = [r["duration_seconds"] for r in items]
        summary.append(
            {
                "architecture": architecture,
                "fault": fault,
                "persistent": persistent,
                "runs": len(items),
                "accepted": sum(r["status"] == "awaiting_human" for r in items),
                "detected": sum(r["detected"] for r in items),
                "repaired": sum(r["accepted_after_repair"] for r in items),
                "mean_calls": mean(r["calls"] for r in items),
                "mean_seconds": mean(values),
                "sd_seconds": stdev(values) if len(values) > 1 else 0,
            }
        )
    write_json(output / "raw-results.json", raw)
    write_json(
        output / "summary.json",
        {
            "boundary": "Scripted fault injection, not live LLM accuracy or cost.",
            "deterministic_status": deterministic.status,
            "deterministic_calls": deterministic.calls,
            "groups": summary,
        },
    )
    with (output / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]))
        writer.writeheader()
        writer.writerows(summary)
    lines = [
        "# Controlled orchestration experiment",
        "",
        "**All model outputs are scripted fault fixtures. No live LLM was called.**",
        "",
        f"{len(raw)} runs; {seeds} seeds per condition. Deterministic reference: {deterministic.status}, 0 calls.",
        "",
        "The single-pass baseline uses one combined context/triage call and no repair. A single-agent "
        "repair baseline uses up to two revisions to control for the effect of feedback. The multi-agent "
        "condition uses separate specialists and at most two revisions per stage. Both use the same "
        "verifier. This design measures recovery with additional calls, not a causal advantage of role separation.",
        "",
        "| Architecture | Fault | Persistent | Runs | Accepted | Detected | Repaired | Mean calls |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            "| "
            + " | ".join(
                str(row[k])
                for k in [
                    "architecture",
                    "fault",
                    "persistent",
                    "runs",
                    "accepted",
                    "detected",
                    "repaired",
                    "mean_calls",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Limits",
            "",
            "Fault fixtures deliberately return corrected output after feedback in transient conditions. "
            "That is a controlled recovery assumption, not evidence that an actual model repairs itself. "
            "Seeds choose fault targets, not independent datasets. Calls count transport attempts. "
            "Local durations exclude model inference and network latency. "
            "Token reservation is not measured token usage or monetary cost. "
            "No ranking accuracy or clinical/security effectiveness claim follows from these results.",
        ]
    )
    (output / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"runs": len(raw), "conditions": len(summary), "output": str(output)}
