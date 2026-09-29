"""Synthetic tool tests only: these fixtures are not human expert responses."""
import csv
import json
import zipfile

import pytest
from test_research_protocol import load_script


def completed(folder, reviewer, labels, **declarations):
    folder.mkdir()
    metadata = {"reviewer_id": reviewer, "qualifications": "SYNTHETIC TEST ONLY",
                "conflicts": "test fixture", "independent_review": True,
                "prior_system_output_exposure": False, **declarations}
    (folder / "reviewer.json").write_text(json.dumps(metadata), encoding="utf-8")
    with (folder / "review.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=load_script("human_review").FIELDS)
        writer.writeheader()
        writer.writerows({"case_id": str(i), "label": label, "confidence": "medium",
                          "rationale": "Synthetic test only", "source_urls": "https://example.org/test"}
                         for i, label in enumerate(labels))
    return folder


def fixtures(tmp_path, left, right, **declarations):
    reviews = [completed(tmp_path / "a", "test-a", left),
               completed(tmp_path / "b", "test-b", right, **declarations)]
    mapping = {str(i): {"case": f"case-{i}", "input_sha256": f"digest-{i}"} for i in range(len(left))}
    predictions = [{**row, "prediction": "affected"} for row in mapping.values()]
    return mapping, reviews, predictions


def test_packet_contains_no_system_answers_and_blank_reviews(tmp_path):
    module = load_script("human_review")
    result = module.prepare(module.ROOT / "benchmarks/reviewed-reference-v1", tmp_path / "packet")
    assert result["human_reviewers"] == 0
    with zipfile.ZipFile(tmp_path / "packet/reviewer-packet.zip") as archive:
        assert set(archive.namelist()) == {"cases.json", "review.csv", "reviewer.json", "README.md"}
        cases = json.loads(archive.read("cases.json"))
        assert len(cases) == 40
        assert all(set(row) == {"case_id", "input", "sources"} for row in cases)
        assert all(row["input"]["name"] == row["case_id"] for row in cases)
        rows = list(csv.DictReader(archive.read("review.csv").decode().splitlines()))
        assert all(not row["label"] and not row["rationale"] for row in rows)
    with pytest.raises(ValueError, match="metadata missing"):
        module.load_review(tmp_path / "packet/reviewer-packet", {r["case_id"] for r in cases})


def test_disagreement_and_uncertainty_stay_in_coverage(tmp_path):
    module = load_script("human_review")
    args = fixtures(tmp_path, ["affected", "outside_this_advisory", "uncertain", "affected"],
                    ["affected", "outside_this_advisory", "uncertain", "uncertain"])
    args[2][0]["prediction"] = "abstain"
    result = module.score(*args)
    assert result["consensus_coverage"] == .5
    assert result["disagreements"] == ["3"]
    assert result["both_uncertain"] == 1
    assert result["system_agreement_on_consensus"] == 0
    assert result["system_abstentions_on_consensus"] == 1
    assert result["cohens_kappa_three_labels"] == pytest.approx(7 / 11)


def test_no_determinate_consensus_is_not_perfect_accuracy(tmp_path):
    result = load_script("human_review").score(*fixtures(tmp_path, ["uncertain"], ["uncertain"]))
    assert result["system_agreement_on_consensus"] is None
    assert result["cohens_kappa_three_labels"] is None
    assert result["consensus_coverage"] == 0


@pytest.mark.parametrize("declarations", [{"independent_review": False},
                                         {"prior_system_output_exposure": True},
                                         {"qualifications": ""}, {"reviewer_id": "test-a"}])
def test_invalid_participation_cannot_be_scored(tmp_path, declarations):
    with pytest.raises(ValueError):
        load_script("human_review").score(*fixtures(tmp_path, ["affected"], ["affected"], **declarations))


@pytest.mark.parametrize("right", [["affected", "affected"], [""], ["safe"]])
def test_invalid_or_incomplete_labels_rejected(tmp_path, right):
    with pytest.raises(ValueError):
        load_script("human_review").score(*fixtures(tmp_path, ["affected"], right))


def test_predictions_must_belong_to_packet(tmp_path):
    args = fixtures(tmp_path, ["affected"], ["affected"])
    args[2][0]["input_sha256"] = "other-input"
    with pytest.raises(ValueError, match="digest"):
        load_script("human_review").score(*args)
