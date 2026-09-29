"""Prepare blinded packets and score two completed human reviews; never generate reviewer labels."""
from __future__ import annotations

import argparse
import csv
import json
import secrets
import uuid
import zipfile
from collections import Counter
from pathlib import Path

from biosbom_agentkg.multiagent.evidence import digest
from biosbom_agentkg.multiagent.models import Case

ROOT = Path(__file__).resolve().parents[1]
LABELS = {"affected", "outside_this_advisory", "uncertain"}
FIELDS = ["case_id", "label", "confidence", "rationale", "source_urls"]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def prepare(inputs, output):
    output.mkdir(parents=True, exist_ok=False)
    packet = output / "reviewer-packet"
    packet.mkdir()
    cases = read(inputs / "cases.json")
    secrets.SystemRandom().shuffle(cases)
    mapping, blinded = {}, []
    for case in cases:
        identifier = "R-" + uuid.uuid4().hex[:16]
        mapping[identifier] = {"case": case["name"],
                               "input_sha256": digest(Case.model_validate(case))}
        copy = {**case, "name": identifier}
        blinded.append({"case_id": identifier, "input": copy,
                        "sources": ["https://github.com/advisories/" + a["id"]
                                    for a in case["advisories"]]})
    write(packet / "cases.json", blinded)
    with (packet / "review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({"case_id": row["case_id"]} for row in blinded)
    write(packet / "reviewer.json", {"reviewer_id": "", "qualifications": "",
                                     "conflicts": "", "independent_review": None,
                                     "prior_system_output_exposure": None})
    (packet / "README.md").write_text(
        "# BioSBOM independent review packet\n\n"
        "No human reviews have been collected. This is a blank evaluation packet.\n\n"
        "Work independently, before discussing cases with the other reviewer. Review only this packet "
        "and cited advisory sources; do not inspect published BioSBOM results or the coordinator map. "
        "Public results exist, so disclose prior exposure honestly.\n\n"
        "For each case, determine whether the component version is affected by the specified advisory. "
        "Use affected, outside_this_advisory, or uncertain. Outside does not mean generally safe. "
        "Do not assess clinical safety, exploitation or operational priority from this synthetic context.\n\n"
        "Fill every CSV row: confidence low/medium/high, an evidence-based rationale, and source URLs. "
        "Use uncertain when evidence is insufficient. Never copy system predictions.\n\n"
        "In reviewer.json, use a pseudonymous reviewer ID, describe relevant qualifications and conflicts "
        "(write none if none), and set the independence/exposure declarations truthfully. "
        "The scorer accepts two complete, independently reviewed, unexposed forms. Declared conflicts "
        "need coordinator review; the tool does not authenticate expertise or identity.\n\n"
        "Return review.csv and reviewer.json privately. Do not commit participant identities or raw responses. "
        "A disagreement is not automatically adjudicated.\n\n"
        "Advisory facts: GitHub Advisory Database contributors, CC BY 4.0, "
        "https://github.com/github/advisory-database/blob/main/LICENSE.md ; OSV projections: https://osv.dev/.\n",
        encoding="utf-8", newline="\n")
    write(output / "coordinator-map.json", mapping)
    with zipfile.ZipFile(output / "reviewer-packet.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(packet.iterdir()):
            archive.write(path, path.name)
    return {"cases": len(mapping), "human_reviewers": 0, "status": "awaiting_human_responses"}


def load_review(folder, expected):
    metadata = read(folder / "reviewer.json")
    for field in ("reviewer_id", "qualifications", "conflicts"):
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise ValueError("Reviewer metadata missing: " + field)
    if metadata.get("independent_review") is not True or metadata.get("prior_system_output_exposure") is not False:
        raise ValueError("Review must declare independence and no prior system-output exposure")
    with (folder / "review.csv").open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != FIELDS:
            raise ValueError("Unexpected review columns")
        rows = list(reader)
    ids = [r["case_id"] for r in rows]
    if len(set(ids)) != len(ids) or set(ids) != set(expected):
        raise ValueError("Review must contain every case exactly once")
    for row in rows:
        if (row["label"] not in LABELS or row["confidence"] not in {"low", "medium", "high"}
                or not (row.get("rationale") or "").strip() or not (row.get("source_urls") or "").strip()):
            raise ValueError("Incomplete or invalid review row: " + row["case_id"])
    return metadata, {r["case_id"]: r["label"] for r in rows}


def score(mapping, reviews, predictions):
    if not mapping or len(reviews) != 2:
        raise ValueError("Exactly two complete human reviews are required")
    loaded = [load_review(folder, mapping) for folder in reviews]
    if loaded[0][0]["reviewer_id"].strip().casefold() == loaded[1][0]["reviewer_id"].strip().casefold():
        raise ValueError("Two distinct reviewer IDs are required")
    by_case = {row["case"]: row for row in predictions}
    if len(by_case) != len(predictions) or set(by_case) != {v["case"] for v in mapping.values()}:
        raise ValueError("Predictions must match packet cases exactly once")
    for value in mapping.values():
        row = by_case[value["case"]]
        if row.get("input_sha256") != value["input_sha256"]:
            raise ValueError("Prediction input digest does not match packet")
        if row.get("prediction") not in {"affected", "outside_this_advisory", "abstain"}:
            raise ValueError("Invalid system prediction")
    left, right = loaded[0][1], loaded[1][1]
    n = len(mapping)
    agreed = sum(left[i] == right[i] for i in mapping)
    marginals = [Counter(labels.values()) for labels in (left, right)]
    expected_agreement = sum(marginals[0][label] * marginals[1][label] for label in LABELS) / n**2
    kappa = (agreed / n - expected_agreement) / (1 - expected_agreement) if expected_agreement < 1 else None
    consensus = {i: left[i] for i in mapping if left[i] == right[i] and left[i] != "uncertain"}
    correct = sum(by_case[mapping[i]["case"]]["prediction"] == label for i, label in consensus.items())
    abstained = sum(by_case[mapping[i]["case"]]["prediction"] == "abstain" for i in consensus)
    return {"status": "provisional_consensus_not_adjudicated", "n": n, "human_reviewers": 2,
            "reviewer_credentials_verified_by_tool": False,
            "reviewer_declarations": [item[0] for item in loaded],
            "inter_rater_agreement": agreed / n, "cohens_kappa_three_labels": kappa,
            "disagreements": [i for i in mapping if left[i] != right[i]],
            "both_uncertain": sum(left[i] == right[i] == "uncertain" for i in mapping),
            "consensus_cases": len(consensus), "consensus_coverage": len(consensus) / n,
            "system_correct_on_consensus": correct, "system_abstentions_on_consensus": abstained,
            "system_agreement_on_consensus": correct / len(consensus) if consensus else None,
            "correct_consensus_fraction_of_all_cases": correct / n,
            "warning": "Selected boundary cases; no final expert gold standard until disagreements are adjudicated."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--inputs", type=Path, default=ROOT / "benchmarks/reviewed-reference-v1")
    prep.add_argument("--output", type=Path, default=ROOT / "private/human-review-v1")
    scoring = sub.add_parser("score")
    scoring.add_argument("--mapping", type=Path, required=True)
    scoring.add_argument("--reviews", type=Path, nargs=2, required=True)
    scoring.add_argument("--predictions", type=Path, required=True)
    scoring.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        print(json.dumps(prepare(args.inputs, args.output)))
    else:
        result = score(read(args.mapping), args.reviews, read(args.predictions))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(result, indent=2) + "\n")
        print(json.dumps({"status": result["status"], "cases": result["n"]}))


if __name__ == "__main__":
    main()
