"""Public-source compositions and synthetic edge contracts; not independent accuracy."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from time import perf_counter

from biosbom_agentkg.multiagent.engine import run_case
from biosbom_agentkg.multiagent.evidence import digest
from biosbom_agentkg.multiagent.models import Case
from biosbom_agentkg.multiagent.remediation import remediation_plan

ROOT = Path(__file__).resolve().parents[1]


def panels():
    folder = ROOT / "benchmarks/reviewed-reference-v1"
    originals = json.loads((folder / "cases.json").read_text())
    labels = {r["case"]: r for r in json.loads((folder / "reference-labels.json").read_text())}
    for repeat in (1, 3, 10):
        case = deepcopy(originals[0])
        case["name"] = f"public-composition-{40 * repeat}"
        case["sbom"]["components"] = []
        advisories, expected = {}, []
        for index, raw in enumerate(originals * repeat):
            component = deepcopy(raw["sbom"]["components"][0])
            component["bom-ref"] = f"c-{index}"
            case["sbom"]["components"].append(component)
            record = raw["advisories"][0]
            advisories[record["id"]] = record
            if labels[raw["name"]]["reference"] == "affected":
                expected.append([f"c-{index}", record["id"], "affected"])
        case["advisories"] = list(advisories.values())
        case["sbom"]["dependencies"] = [{"ref": f"c-{i}", "dependsOn": [f"c-{i+1}"]}
                                            for i in range(len(case["sbom"]["components"]) - 1)]
        yield {"case": case, "expected": expected, "group": "public_composition"}
        if repeat == 1:
            spdx = deepcopy(case)
            spdx["name"] = "public-composition-spdx"
            spdx["sbom"] = {"spdxVersion": "SPDX-2.3", "packages": [
                {"SPDXID": c["bom-ref"], "name": c["name"], "versionInfo": c["version"],
                 "externalRefs": [{"referenceType": "purl", "referenceLocator": c["purl"]}]}
                for c in case["sbom"]["components"]]}
            yield {"case": spdx, "expected": expected, "group": "public_composition"}
    base = {"name": "edge", "synthetic": True,
            "sbom": {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": [
                {"name": "demo-pkg", "bom-ref": "c", "version": "1.0", "purl": "pkg:pypi/demo-pkg"}]},
            "advisories": [{"id": "SYNTHETIC-EDGE", "affected": [{"package": {"name": "demo-pkg", "ecosystem": "PyPI"},
                "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2.0"}]}]}]}],
            "context": {"asset_id": "synthetic-edge", "criticality": 5, "data_sensitivity": 5,
                        "exposure": 5, "security_control_score": 5}, "intelligence": []}
    specifications = [("affected", "affected"), ("fixed", None), ("future", None),
        ("missing", "review"), ("local", "review"), ("malformed_version", "review"),
        ("git_only", "review"), ("unknown_ecosystem", "review"), ("invalid_events", "review"),
        ("withdrawn", None), ("empty_snapshot", None), ("alias_case", "affected"),
        ("alias_purl", "affected"), ("gap", None), ("reintroduced", "affected"),
        ("explicit", "affected"), ("prerelease", "affected"), ("last_affected", "affected"),
        ("after_last", None), ("unordered", "affected"), ("different_package", None),
        ("duplicate_component", "reject"), ("duplicate_advisory", "reject"), ("nested", "reject")]
    for name, label in specifications:
        case = deepcopy(base)
        case["name"] = "edge-" + name
        component = case["sbom"]["components"][0]
        record = case["advisories"][0]
        affected = record["affected"][0]
        span = affected["ranges"][0]
        if name in {"fixed", "future", "local", "malformed_version", "prerelease"}:
            component["version"] = {"fixed": "2.0", "future": "9.0", "local": "1.0+vendor",
                                    "malformed_version": "not-a-version", "prerelease": "1.1rc1"}[name]
        elif name == "missing":
            component.pop("version")
        elif name == "git_only":
            span["type"] = "GIT"
        elif name == "unknown_ecosystem":
            component["purl"] = "pkg:conda/demo-pkg"
            affected["package"]["ecosystem"] = "Conda"
        elif name == "invalid_events":
            span["events"] = [{"introduced": "0", "fixed": "2.0"}]
        elif name == "withdrawn":
            record["withdrawn"] = "2026-01-01T00:00:00Z"
        elif name == "empty_snapshot":
            case["advisories"] = []
        elif name.startswith("alias"):
            component["name"] = "Demo_Pkg"
            component["purl"] = "pkg:pypi/Demo_Pkg"
            if name == "alias_purl":
                affected["package"]["purl"] = "pkg:pypi/demo-pkg"
        elif name in {"gap", "reintroduced"}:
            component["version"] = "2.5" if name == "gap" else "3.5"
            span["events"] += [{"introduced": "3.0"}, {"fixed": "4.0"}]
        elif name == "explicit":
            affected["ranges"] = []
            affected["versions"] = ["1.0"]
        elif name in {"last_affected", "after_last"}:
            span["events"][-1] = {"last_affected": "1.0"}
            if name == "after_last":
                component["version"] = "1.1"
        elif name == "unordered":
            span["events"].reverse()
        elif name == "different_package":
            affected["package"]["name"] = "unrelated"
        elif name == "duplicate_component":
            case["sbom"]["components"].append(deepcopy(component))
        elif name == "duplicate_advisory":
            case["advisories"].append(deepcopy(record))
        elif name == "nested":
            component["components"] = [{"name": "hidden"}]
        yield {"case": case, "expected": [["c", "SYNTHETIC-EDGE", label]] if label and label != "reject" else [],
               "reject": label == "reject", "group": "synthetic_contract"}


def evaluate(output):
    output.mkdir(parents=True, exist_ok=False)
    inputs, results = list(panels()), []
    (output / "inputs-and-contracts.json").write_text(json.dumps(inputs, indent=2) + "\n", encoding="utf-8", newline="\n")
    for panel in inputs:
        start = perf_counter()
        row = {"case": panel["case"]["name"], "group": panel["group"], "input_sha256": digest(panel["case"])}
        try:
            case = Case.model_validate(panel["case"])
            result = run_case(case)
            observed = sorted([[f.component_ref, f.advisory_id, "affected" if f.match in {"range_version", "exact_version"} else "review"]
                               for f in result.collection.findings])
            plan = remediation_plan(case)
            row.update(observed=observed, expected=sorted(panel["expected"]),
                       passed=observed == sorted(panel["expected"]) and result.audit.passed and not panel.get("reject"),
                       audit_passed=result.audit.passed, components=len(result.collection.sbom.components),
                       plan_candidates=sum(i["candidate_version"] is not None for i in plan["items"]))
        except (ValueError, TypeError, KeyError) as exc:
            row.update(passed=panel.get("reject", False), rejected=type(exc).__name__)
        row["seconds"] = round(perf_counter() - start, 6)
        results.append(row)
    summary = {"panels": len(results), "passed": sum(r["passed"] for r in results),
               "model_calls": 0, "human_reviewers": 0,
               "interpretation": "Development regression contracts and reused public references, not new independent accuracy",
               "groups": {g: {"n": sum(r["group"] == g for r in results),
                              "passed": sum(r["group"] == g and r["passed"] for r in results)}
                          for g in sorted({r["group"] for r in results})}}
    for name, value in [("results", results), ("summary", summary)]:
        (output / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    result = evaluate(parser.parse_args().output)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] == result["panels"] else 1)
