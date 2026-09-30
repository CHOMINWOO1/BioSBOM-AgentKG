from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from biosbom_agentkg.multiagent.discovery import DiscoveryError, NoRedirect, discover
from biosbom_agentkg.multiagent.models import Case
from biosbom_agentkg.multiagent.remediation import remediation_plan
from biosbom_agentkg.web.app import create_app


def sample(version="1.0", name="demo", ecosystem="pypi"):
    return Case.model_validate({"name": "test", "synthetic": True,
        "sbom": {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": [
            {"bom-ref": "pkg", "type": "library", "name": name, "version": version,
             "purl": f"pkg:{ecosystem}/{name}"}]}, "advisories": [], "intelligence": [],
        "context": {"asset_id": "private-asset", "criticality": 5, "data_sensitivity": 5,
                    "exposure": 5, "security_control_score": 5}})


def advisory(identifier="TEST-1", fixed="2.0", **extra):
    return {"id": identifier, "affected": [{"package": {"ecosystem": "PyPI", "name": "demo"},
            "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": fixed}]}]}], **extra}


def test_query_minimizes_data_and_handles_pages():
    sent = []
    def request(payload, timeout):
        sent.append(payload)
        return {"vulns": [advisory()], "next_page_token": "next"} if len(sent) == 1 else {}
    result = discover(sample(), request=request)
    assert sent[0] == {"package": {"purl": "pkg:pypi/demo"}, "version": "1.0"}
    assert sent[1]["page_token"] == "next"
    assert result["status"] == "complete"
    assert result["analysis_ready"] is True
    assert len(result["pages"]) == 2
    assert len(result["case"]["advisories"]) == 1
    assert "private-asset" not in str(sent)


@pytest.mark.parametrize("answer", [{"error": "bad"}, {"vulns": None}, {"vulns": [{}]},
                                    {"next_page_token": 12}])
def test_bad_source_is_partial_not_clean(answer):
    result = discover(sample(), request=lambda *args: answer)
    assert result["status"] == "partial"
    assert result["queried_components"] == 0


def test_network_failure_and_budget_are_not_clean():
    def failed(*args):
        raise DiscoveryError("source_unavailable")
    assert discover(sample(), request=failed)["queries"][0]["reason"] == "source_unavailable"
    result = discover(sample(), request=lambda *args: {"next_page_token": "page"}, max_requests=1)
    assert result["status"] == "partial"
    assert result["calls"] == 1
    assert result["queries"][0]["reason"] == "query_budget_exhausted"


def test_pagination_cycle_and_conflicting_snapshots():
    result = discover(sample(), request=lambda *args: {"next_page_token": "same"})
    assert result["queries"][0]["reason"] == "pagination_cycle"
    responses = iter([{"vulns": [advisory()], "next_page_token": "next"}, {"vulns": [advisory(fixed="3.0")]}])
    result = discover(sample(), request=lambda *args: next(responses))
    assert result["status"] == "partial"
    assert result["conflicting_advisories"] == ["TEST-1"]


@pytest.mark.parametrize("case", [sample(None), sample(ecosystem="conda")])
def test_unknown_identity_not_sent(case):
    def unexpected(*args):
        pytest.fail("Must not send incomplete or unsupported identity")
    assert discover(case, request=unexpected)["calls"] == 0


def test_duplicate_queries_are_deduplicated():
    case = sample()
    second = deepcopy(case.sbom["components"][0])
    second["bom-ref"] = "second"
    case.sbom["components"].append(second)
    result = discover(case, request=lambda *args: {})
    assert result["calls"] == 1
    assert result["queried_components"] == 2


def test_redirect_refused():
    with pytest.raises(DiscoveryError, match="redirect_refused"):
        NoRedirect().redirect_request(None, None, 302, "", {}, "http://localhost/")


def test_candidate_checks_all_advisories_and_dependency_parents():
    case = sample()
    case.advisories = [advisory(), advisory("TEST-2", "3.0")]
    case.sbom["dependencies"] = [{"ref": "pipeline", "dependsOn": ["pkg"]}]
    plan = remediation_plan(case)
    assert plan["items"][0]["candidate_version"] == "3.0"
    assert plan["items"][0]["parent_components"] == ["pipeline"]
    assert plan["status"] == "requires_human_review"
    assert plan["items"][0]["evidence_ids"]


def test_reintroduction_cannot_be_recommended_as_fix():
    case = sample()
    record = advisory()
    record["affected"][0]["ranges"][0]["events"] += [{"introduced": "2.0"}, {"fixed": "4.0"}]
    case.advisories = [record]
    # Contradictory duplicate transition boundaries are deliberately uncertain.
    assert remediation_plan(case)["items"][0]["candidate_version"] is None


@pytest.mark.parametrize("change", ["missing", "local", "git", "no_fix", "bad_events"])
def test_uncertain_cases_require_manual_investigation(change):
    case = sample()
    record = advisory()
    if change == "missing":
        case.sbom["components"][0]["version"] = None
    elif change == "local":
        case.sbom["components"][0]["version"] = "1.0+vendor"
    elif change == "git":
        record["affected"][0]["ranges"][0]["type"] = "GIT"
    elif change == "no_fix":
        record["affected"][0]["ranges"][0]["events"] = [{"introduced": "0"}]
    else:
        record["affected"][0]["ranges"][0]["events"] = None
    case.advisories = [record]
    assert remediation_plan(case)["items"][0]["candidate_version"] is None


def test_discovery_web_requires_consent_and_does_not_queue(tmp_path):
    calls = []
    def source(case):
        calls.append(case)
        return discover(case, request=lambda *args: {"vulns": [advisory()]})
    with TestClient(create_app(tmp_path / "web", discoverer=source), base_url="http://localhost:8876") as client:
        client.get("/")
        client.headers["x-biosbom-csrf"] = client.get("/api/session").json()["csrf"]
        body = {"case": sample().model_dump(mode="json")}
        assert client.post("/api/discover", json=body).status_code == 409
        assert not calls
        body["public_lookup_acknowledged"] = True
        response = client.post("/api/discover", json=body)
        assert response.status_code == 200
        assert response.json()["plan"]["items"][0]["candidate_version"] == "2.0"
        assert client.get("/api/jobs").json()["total"] == 0
        client.headers.pop("x-biosbom-csrf")
        assert client.post("/api/discover", json=body).status_code == 403


def test_partial_lookup_suppresses_upgrade_candidates():
    from biosbom_agentkg.multiagent.remediation import discovery_plan
    acquisition = discover(sample(), request=lambda *args: {"vulns": [advisory()], "next_page_token": "next"}, max_requests=1)
    assert discovery_plan(acquisition)["items"][0]["candidate_version"] is None
    acquisition["case"]["name"] = "tampered"
    with pytest.raises(ValueError, match="hash"):
        discovery_plan(acquisition)


def test_schema_21_records_keep_original_name_matching(tmp_path, monkeypatch):
    from biosbom_agentkg.multiagent import engine
    from biosbom_agentkg.multiagent.evidence import CollectorAgent
    from biosbom_agentkg.multiagent.storage import save_run, verify_run
    case = sample(name="Demo_Pkg")
    record = advisory()
    record["affected"][0]["package"]["name"] = "demo-pkg"
    case.advisories = [record]
    assert len(CollectorAgent().run(case).findings) == 1
    monkeypatch.setattr(engine, "CollectorAgent", lambda: CollectorAgent(canonical_names=False))
    old = engine.run_case(case).model_copy(update={"schema_version": "2.1"})
    assert not old.collection.findings
    save_run(case, old, tmp_path / "old")
    assert verify_run(tmp_path / "old")[1].schema_version == "2.1"


def test_npm_candidate_uses_semver_and_rechecks_other_ranges():
    case = sample(version="1.0.0", ecosystem="npm")
    record = advisory(fixed="2.0.0")
    record["affected"][0]["package"]["ecosystem"] = "npm"
    record["affected"][0]["ranges"][0]["type"] = "SEMVER"
    case.advisories = [record]
    assert remediation_plan(case)["items"][0]["candidate_version"] == "2.0.0"
