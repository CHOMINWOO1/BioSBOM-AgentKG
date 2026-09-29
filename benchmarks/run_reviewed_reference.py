"""Frozen external-reference agreement, with labels loaded only after predictions."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from biosbom_agentkg.multiagent.engine import run_case
from biosbom_agentkg.multiagent.evidence import digest
from biosbom_agentkg.multiagent.models import Case

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def metrics(rows):
    allowed_reference = {"affected", "outside_this_advisory"}
    allowed_prediction = allowed_reference | {"abstain"}
    if not rows or any(r["reference"] not in allowed_reference or
                       r["prediction"] not in allowed_prediction for r in rows):
        raise ValueError("Invalid or empty scored rows")
    counts = Counter((r["reference"], r["prediction"]) for r in rows)
    tp = counts["affected", "affected"]
    fn = counts["affected", "outside_this_advisory"]
    fp = counts["outside_this_advisory", "affected"]
    tn = counts["outside_this_advisory", "outside_this_advisory"]
    ap = counts["affected", "abstain"]
    an = counts["outside_this_advisory", "abstain"]
    ratio = lambda a, b: a / b if b else None  # noqa: E731
    return {"n": len(rows), "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "abstain_affected": ap, "abstain_outside": an,
            "agreement_all": (tp + tn) / len(rows),
            "coverage": (len(rows) - ap - an) / len(rows),
            "agreement_answered": ratio(tp + tn, len(rows) - ap - an),
            "sensitivity_including_abstentions": ratio(tp, tp + fn + ap),
            "specificity_including_abstentions": ratio(tn, tn + fp + an)}


def join_labels(predictions, labels):
    by_name = {r["case"]: r for r in labels}
    names = [r["case"] for r in predictions]
    if len(by_name) != len(labels) or len(set(names)) != len(names) or set(names) != set(by_name):
        raise ValueError("Label/prediction IDs must match exactly once")
    return [{**row, **{k: v for k, v in by_name[row["case"]].items() if k != "source"}}
            for row in predictions]


def evaluate(inputs, output):
    for name, expected in read(inputs / "frozen-inputs.json").items():
        actual = hashlib.sha256((inputs / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if actual != expected:
            raise ValueError("Frozen input hash mismatch: " + name)
    for name, expected in read(inputs / "application-source-hashes.json").items():
        actual = hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if actual != expected:
            raise ValueError("Application differs from the fixed baseline: " + name)
    output.mkdir(parents=True, exist_ok=False)
    predictions = []
    for raw in read(inputs / "cases.json"):
        case = Case.model_validate(raw)
        result = run_case(case)
        findings = result.collection.findings
        prediction = (
            "abstain" if not result.audit.passed else
            "affected" if any(f.match in {"exact_version", "range_version"} for f in findings) else
            "abstain" if findings else "outside_this_advisory"
        )
        predictions.append({"case": case.name, "prediction": prediction,
                            "audit_passed": result.audit.passed, "input_sha256": digest(case),
                            "calls": result.calls,
                            "matches": [f.match for f in findings],
                            "reasons": [f.reason for f in findings],
                            "warnings": result.collection.warnings})
    # Persist predictions before reading reference answers.
    write(output / "predictions.json", predictions)
    rows = join_labels(predictions, read(inputs / "reference-labels.json"))
    summary = metrics(rows)
    summary.update({"human_reviewers": 0, "model_calls": sum(r["calls"] for r in rows),
                    "reference_type": "github_reviewed_query_shared_curation_with_osv",
                    "by_package": {p: metrics([r for r in rows if r["package"] == p])
                                   for p in sorted({r["package"] for r in rows})}})
    write(output / "case-results.json", rows)
    write(output / "summary.json", summary)
    write(output / "errors.json", [r for r in rows if r["prediction"] != r["reference"]])
    with (output / "case-results.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = ["case", "package", "version", "advisory", "reference", "prediction", "audit_passed"]
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, default=ROOT / "benchmarks/reviewed-reference-v1")
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(evaluate(**vars(parser.parse_args())), indent=2))
