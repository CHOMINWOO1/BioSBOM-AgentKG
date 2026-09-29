import json
from pathlib import Path

import pytest

from biosbom_agentkg.multiagent.agents import ContextAgent, TriageAgent, VerificationAgent, specialist_payload
from biosbom_agentkg.multiagent.evidence import CollectorAgent, digest
from biosbom_agentkg.multiagent.models import Case
from test_research_protocol import load_script

ROOT = Path(__file__).resolve().parents[1] / "benchmarks"
CASES = json.loads((ROOT / "triage-panel-v042.json").read_text())
EXPECTATIONS = json.loads((ROOT / "triage-expectations-v042.json").read_text())


@pytest.mark.parametrize("raw,expected", list(zip(CASES, EXPECTATIONS, strict=True)),
                         ids=[c["name"] for c in CASES])
def test_policy_boundaries_and_forbidden_priorities(raw, expected):
    case = Case.model_validate(raw)
    collection = CollectorAgent().run(case)
    context = ContextAgent().run(case, collection)
    packet = TriageAgent().run(case, collection, context)
    assert len(packet.assessments) == 1
    row = packet.assessments[0]
    assert row.status == expected["status"]
    constraints = specialist_payload("triage", case, collection, context)["triage_contract"]["constraints"]
    assert constraints[0]["allowed_priorities"] == expected["allowed_priorities"]
    for priority in ["normal", "high", "urgent", "review"]:
        row.priority = priority
        assert VerificationAgent().run(case, collection, context, packet).passed == (
            priority in expected["allowed_priorities"]
        )


def test_original_triage_comparison_transmits_exact_v041_payloads():
    hashes = json.loads((ROOT / "triage-original-payload-hashes.json").read_text())["hashes"]
    adapt = load_script("run_citation_ablation").transmitted_payload
    for raw, expected in zip(CASES, hashes, strict=True):
        case = Case.model_validate(raw)
        collection = CollectorAgent().run(case)
        context = ContextAgent().run(case, collection)
        for role in ["context", "single", "triage"]:
            payload = specialist_payload(role, case, collection, context if role == "triage" else None)
            assert digest(adapt(payload, "v041_original")) == expected[role]
