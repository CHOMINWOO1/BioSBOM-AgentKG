import pytest
from test_research_protocol import load_script


def test_external_metrics_keep_abstentions_in_denominator():
    module = load_script("run_reviewed_reference")
    rows = [{"reference": truth, "prediction": prediction} for truth, prediction in [
        ("affected", "affected"), ("affected", "outside_this_advisory"), ("affected", "abstain"),
        ("outside_this_advisory", "outside_this_advisory"), ("outside_this_advisory", "affected"),
        ("outside_this_advisory", "abstain")]]
    actual = module.metrics(rows)
    assert actual["agreement_all"] == 2 / 6
    assert actual["coverage"] == 4 / 6
    assert actual["agreement_answered"] == 2 / 4
    assert actual["sensitivity_including_abstentions"] == 1 / 3
    assert actual["specificity_including_abstentions"] == 1 / 3


@pytest.mark.parametrize("labels", [[{"case": "wrong"}], [{"case": "one"}, {"case": "one"}]])
def test_external_labels_cannot_be_missing_or_duplicated(labels):
    with pytest.raises(ValueError, match="exactly once"):
        load_script("run_reviewed_reference").join_labels([{"case": "one"}], labels)


def test_all_abstentions_do_not_create_accuracy():
    result = load_script("run_reviewed_reference").metrics([
        {"reference": "affected", "prediction": "abstain"}])
    assert result["coverage"] == 0
    assert result["agreement_all"] == 0
    assert result["agreement_answered"] is None
    assert result["specificity_including_abstentions"] is None
