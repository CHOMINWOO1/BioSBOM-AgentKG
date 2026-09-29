import json
from pathlib import Path

import pytest

from biosbom_agentkg.cli import main
from biosbom_agentkg.multiagent.engine import run_case
from biosbom_agentkg.multiagent.evaluation import FaultProvider, evaluate
from biosbom_agentkg.multiagent.models import RunConfig
from biosbom_agentkg.multiagent.reporting import render_html
from biosbom_agentkg.multiagent.storage import record_review, save_run, verify_run


def test_frozen_v03_artifacts_keep_original_matching_and_review_hash():
    from biosbom_agentkg.multiagent.evidence import digest

    target = Path(__file__).parent / "fixtures/legacy-v03"
    case, result = verify_run(target)
    assert result.schema_version == "2.0"
    assert len(result.collection.findings) == 5
    assert len(run_case(case).collection.findings) == 3
    review = json.loads((target / "human-review.json").read_text())
    assert review["reviewed_result_sha256"] == digest(result)


def test_saved_run_verifies_and_review_is_immutable(case, tmp_path):
    path = tmp_path / "run"
    result = run_case(case)
    save_run(case, result, path)
    assert verify_run(path)[1] == result
    record = record_review(path, "approve", "synthetic-reviewer", "Reviewed fixture evidence")
    assert record["decision"] == "approve"
    with pytest.raises(FileExistsError):
        record_review(path, "reject", "another", "Overwrite prohibited")
    with pytest.raises(FileExistsError):
        save_run(case, result, path)


def test_tampered_result_cannot_be_approved(case, tmp_path):
    path = tmp_path / "run"
    save_run(case, run_case(case), path)
    (path / "report.md").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity"):
        record_review(path, "approve", "reviewer", "Cannot approve")


def test_blocked_run_cannot_be_approved(case, tmp_path):
    result = run_case(case, RunConfig(mode="llm", max_revisions=0), FaultProvider("schema"))
    path = tmp_path / "run"
    save_run(case, result, path)
    with pytest.raises(ValueError, match="Blocked"):
        record_review(path, "approve", "reviewer", "Should fail")
    assert record_review(path, "hold", "reviewer", "Fix model output")["decision"] == "hold"


def test_html_escapes_input(case):
    case.name = "<script>alert(1)</script>"
    report = render_html(run_case(case))
    assert "<script>" not in report
    assert "&lt;script&gt;" in report
    assert "Content-Security-Policy" in report


def test_cli_round_trip(case, tmp_path, capsys):
    casefile = tmp_path / "case.json"
    casefile.write_text(case.model_dump_json(), encoding="utf-8")
    out = tmp_path / "run"
    assert main(["run", "--case", str(casefile), "--output", str(out)]) == 0
    assert main(["verify", str(out)]) == 0
    assert (
        main(["review", str(out), "--decision", "hold", "--reviewer", "tester", "--reason", "demo"])
        == 0
    )
    assert main(["run", "--case", str(casefile), "--output", str(out)]) == 1
    assert "error" in capsys.readouterr().out


def test_small_experiment_reports_controlled_conditions(case, tmp_path):
    out = tmp_path / "eval"
    summary = evaluate(case, out, seeds=1)
    assert summary["runs"] == 57
    data = json.loads((out / "summary.json").read_text())
    assert "not live LLM" in data["boundary"]
    assert len(data["groups"]) == 57
    with pytest.raises(FileExistsError):
        evaluate(case, out, seeds=1)
