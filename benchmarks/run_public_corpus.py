"""Offline snapshot consistency + core latency; no live model or hidden labels."""

from __future__ import annotations

import argparse
import copy
import csv
import json
import math
import platform
import random
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from biosbom_agentkg.multiagent.engine import run_case
from biosbom_agentkg.multiagent.evidence import digest
from biosbom_agentkg.multiagent.models import Case
from biosbom_agentkg.multiagent.storage import write_json

ROOT = Path(__file__).parent


def fixture(record, variant):
    advisory = copy.deepcopy(record["advisory"])
    package = record["package"]
    version = record["fixed_version"] if variant == "fixed_boundary" else record["affected_version"]
    comp = {
        "bom-ref": "fixture-component",
        "name": package,
        "version": version,
        "purl": f"pkg:pypi/{package}@{version}",
        "type": "library",
    }
    expected = "exact_version"
    if variant == "missing_version":
        comp.pop("version")
        comp["purl"] = f"pkg:pypi/{package}"
        expected = "version_missing"
    elif variant == "fixed_boundary":
        expected = "ambiguous"  # Range evaluation remains explicitly unsupported.
    elif variant == "other_ecosystem":
        comp["purl"] = f"pkg:npm/{package}@{version}"
        expected = "no_candidate"
    elif variant == "withdrawn":
        advisory["withdrawn"] = "2026-01-01T00:00:00Z"  # Controlled perturbation.
        expected = "no_candidate"
    case = Case.model_validate(
        {
            "name": f"{package}-{variant}",
            "synthetic": True,
            "sbom": {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": [comp]},
            "advisories": [advisory],
            "context": {
                "asset_id": "benchmark-synthetic",
                "criticality": 5,
                "data_sensitivity": 5,
                "exposure": 5,
                "security_control_score": 5,
            },
        }
    )
    return case, expected


def run(output, repeats=30):
    if not 1 <= repeats <= 1000:
        raise ValueError("repeats must be 1..1000")
    output.mkdir(parents=True, exist_ok=False)
    records = json.loads((ROOT / "public-corpus/advisories.json").read_text(encoding="utf-8"))
    variants = [
        "affected_enumerated",
        "fixed_boundary",
        "missing_version",
        "other_ecosystem",
        "withdrawn",
    ]
    rows, cases = [], []
    for record in records:
        for variant in variants:
            case, expected = fixture(record, variant)
            result = run_case(case)
            observed = (
                result.collection.findings[0].match
                if result.collection.findings
                else "no_candidate"
            )
            rows.append(
                {
                    "package": record["package"],
                    "advisory": record["advisory"]["id"],
                    "variant": variant,
                    "expected": expected,
                    "observed": observed,
                    "passed": observed == expected and result.audit.passed,
                    "case_sha256": digest(case),
                    "candidates": len(result.collection.findings),
                }
            )
            cases.append(case.model_dump(mode="json"))
    write_json(output / "case-results.json", rows)
    write_json(output / "cases.json", cases)
    latencies = []
    workloads = {}
    for size in (10, 100, 1000):
        base, _ = fixture(records[0], "affected_enumerated")
        base.name = f"synthetic-scale-{size}"
        components = []
        for record in records:
            item, _ = fixture(record, "affected_enumerated")
            comp = item.sbom["components"][0]
            comp["bom-ref"] = comp["purl"]
            components.append(comp)
        for i in range(size - len(components)):
            components.append(
                {
                    "bom-ref": f"unmatched-{i}",
                    "name": f"synthetic-unmatched-{i}",
                    "version": "1.0.0",
                    "purl": f"pkg:pypi/synthetic-unmatched-{i}@1.0.0",
                }
            )
        base.sbom["components"] = components
        base.advisories = [r["advisory"] for r in records]
        workloads[size] = base
        run_case(base)  # One unmeasured warm-up per size.
    schedule = [(size, repeat) for repeat in range(repeats) for size in workloads]
    random.Random(20260929).shuffle(schedule)
    for size, repeat in schedule:
        start = perf_counter()
        result = run_case(workloads[size])
        elapsed = (perf_counter() - start) * 1000
        latencies.append(
            {
                "components": size,
                "repeat": repeat,
                "milliseconds": elapsed,
                "findings": len(result.collection.findings),
                "passed": result.audit.passed and len(result.collection.findings) == len(records),
            }
        )
    with (output / "latency.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(latencies[0]))
        writer.writeheader()
        writer.writerows(latencies)
    aggregate = []
    for size in workloads:
        values = sorted(x["milliseconds"] for x in latencies if x["components"] == size)
        aggregate.append(
            {
                "components": size,
                "n": len(values),
                "median_ms": statistics.median(values),
                "p95_ms": values[math.ceil(0.95 * len(values)) - 1],
                "min_ms": min(values),
                "max_ms": max(values),
            }
        )
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "os": platform.system(),
        "processor_architecture": platform.machine(),
        "corpus_sha256": digest(records),
        "advisories": len(records),
        "cases": len(rows),
        "passed": sum(r["passed"] for r in rows),
        "observed": dict(Counter(r["observed"] for r in rows)),
        "latency": aggregate,
        "latency_all_passed": all(r["passed"] for r in latencies),
        "limitations": [
            "Source-derived labels, not an independent clinical or exploitability benchmark",
            "Fixed versions deliberately stay ambiguous: range handling is not implemented",
            "Latency excludes HTTP, SQLite, artifact writing and LLM calls",
            "Eight PyPI advisories; not representative of all bioinformatics environments",
        ],
    }
    write_json(output / "summary.json", summary)
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=30)
    args = parser.parse_args()
    result = run(args.output, args.repeats)
    raise SystemExit(
        0 if result["passed"] == result["cases"] and result["latency_all_passed"] else 1
    )
