import json
from pathlib import Path

import pytest

from biosbom_agentkg.multiagent.agents import ContextAgent, VerificationAgent, specialist_payload
from biosbom_agentkg.multiagent.evidence import CollectorAgent, digest
from biosbom_agentkg.multiagent.models import Case, ContextPacket
from biosbom_agentkg.multiagent.evaluation import FaultProvider
from test_research_protocol import load_script


def test_original_payloads_match_published_v04_before_ablation():
    root = Path(__file__).resolve().parents[1] / "benchmarks"
    cases = json.loads((root / "citation-panel-v041.json").read_text())
    hashes = json.loads((root / "citation-original-payload-hashes.json").read_text())["hashes"]
    adapt = load_script("run_citation_ablation").transmitted_payload
    for raw, expected in zip(cases, hashes, strict=True):
        case = Case.model_validate(raw)
        collection = CollectorAgent().run(case)
        context = ContextAgent().run(case, collection)
        for role in ("context", "single", "triage"):
            payload = specialist_payload(role, case, collection, context if role == "triage" else None)
            assert digest(adapt(payload, "v04_original")) == expected[role]


@pytest.mark.parametrize("ids", [[], ["context:invented"], ["duplicate", "duplicate"]])
def test_empty_concerns_still_require_authentic_snapshot(case, ids):
    case.context.data_sensitivity = case.context.exposure = case.context.criticality = 0
    case.context.security_control_score = 10
    case.advisories = []
    collection = CollectorAgent().run(case)
    audit = VerificationAgent().check_context(
        case, collection, ContextPacket(concerns=[], evidence_ids=ids)
    )
    assert [issue.code for issue in audit.issues] == ["context_evidence"]
    assert VerificationAgent().check_context(case, collection, ContextAgent().run(case, collection)).passed


def test_ablation_preserves_pairing_and_trace_attribution(tmp_path, case):
    module = load_script("run_citation_ablation")
    provider = FaultProvider()
    with pytest.raises(ValueError, match="authorization"):
        module.evaluate([case], tmp_path / "bad", provider, max_total_calls=23)
    assert not (tmp_path / "bad").exists()
    rows = module.evaluate([case], tmp_path / "ok", provider, max_total_calls=24)
    assert len(rows) == 4 and all(r["verified"] for r in rows)
    assert len({(r["architecture"], r["contract"]) for r in rows}) == 4
    traces = json.loads((tmp_path / "ok/calls.json").read_text())
    assert len(traces) == sum(row["calls"] for row in rows) == 6
    for row in rows:
        selected = [trace for trace in traces if trace["run"] == row["run"]]
        assert len(selected) == row["calls"]
        assert all(trace["contract"] == row["contract"] for trace in selected)
