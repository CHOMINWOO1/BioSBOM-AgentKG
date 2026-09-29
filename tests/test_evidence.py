import copy
import json
from pathlib import Path

import pytest

from biosbom_agentkg.multiagent.evidence import CollectorAgent, digest, purl_parts


def test_collection_preserves_every_package_and_provenance(case):
    result = CollectorAgent().run(case)
    assert len(result.dispositions) == 5
    assert [f.match for f in result.findings].count("exact_version") == 2
    assert [f.match for f in result.findings].count("version_missing") == 1
    evidence = {e.evidence_id for e in result.evidence}
    assert all(set(f.evidence_ids) <= evidence for f in result.findings)
    assert len([r for r in result.dispositions if r.status == "unmatched"]) == 2
    assert digest(CollectorAgent().run(case)) == digest(result)


def test_spdx_supported_without_advisories(case):
    path = Path(__file__).resolve().parents[1] / "examples/synthetic-spdx-bioimage.json"
    case.sbom = json.loads(path.read_text())
    case.advisories = []
    result = CollectorAgent().run(case)
    assert result.sbom.source_format == "spdx-json"
    assert len(result.sbom.components) == len(case.sbom["packages"])
    assert "empty_advisory_snapshot" in result.warnings


@pytest.mark.parametrize(
    "purl,identity,version",
    [
        ("pkg:npm/@scope/package", "pkg:npm/@scope/package", None),
        ("pkg:npm/%40scope/package@1.2.3", "pkg:npm/@scope/package", "1.2.3"),
        (
            "pkg:deb/debian/openssl@3.0?distro=bookworm&arch=amd64",
            "pkg:deb/debian/openssl?arch=amd64&distro=bookworm",
            "3.0",
        ),
    ],
)
def test_purl_identity(purl, identity, version):
    assert purl_parts(purl) == (identity, version)


def test_supported_ranges_are_matched(case):
    case.sbom["components"][-1]["version"] = "1.0"
    result = CollectorAgent().run(case)
    assert result.findings[-1].match == "range_version"


def test_exact_version_absent_is_unmatched(case):
    case.advisories[0]["affected"][0]["versions"] = ["0.0.0"]
    result = CollectorAgent().run(case)
    assert not any(f.advisory_id == "SYNTHETIC-OPENSSL-001" for f in result.findings)


def test_withdrawn_advisory_not_a_finding(case):
    case.advisories[0]["withdrawn"] = "2026-01-01T00:00:00Z"
    result = CollectorAgent().run(case)
    assert not any(f.advisory_id == "SYNTHETIC-OPENSSL-001" for f in result.findings)
    assert any("withdrawn_advisory" in warning for warning in result.warnings)


def test_qualifiers_not_conflated(case):
    case.advisories[0]["affected"][0]["package"]["purl"] = "pkg:deb/debian/openssl?distro=another"
    assert not any(
        f.advisory_id == "SYNTHETIC-OPENSSL-001" for f in CollectorAgent().run(case).findings
    )


@pytest.mark.parametrize(
    "fault",
    ["duplicate_component", "duplicate_advisory", "bad_row", "nested", "version_conflict", "empty"],
)
def test_invalid_input_fails_without_dropping_packages(case, fault):
    if fault == "duplicate_component":
        case.sbom["components"].append(copy.deepcopy(case.sbom["components"][0]))
    elif fault == "duplicate_advisory":
        case.advisories.append(copy.deepcopy(case.advisories[0]))
    elif fault == "bad_row":
        case.sbom["components"].append("invalid")
    elif fault == "nested":
        case.sbom["components"][0]["components"] = [{"name": "hidden"}]
    elif fault == "version_conflict":
        case.sbom["components"][0]["version"] = "99.0"
    elif fault == "empty":
        case.sbom = {"bomFormat": "CycloneDX", "components": []}
    with pytest.raises(ValueError):
        CollectorAgent().run(case)


def test_missing_names_are_retained(case):
    case.sbom["components"].append({"bom-ref": "missing-name", "version": "1.0"})
    result = CollectorAgent().run(case)
    assert any(
        d.component_ref == "missing-name" and d.status == "missing_identity"
        for d in result.dispositions
    )


@pytest.mark.parametrize("bad_value", [None, [], "not an object"])
def test_malformed_metadata_has_clear_failure(case, bad_value):
    case.sbom["metadata"] = bad_value
    with pytest.raises(ValueError, match="metadata"):
        CollectorAgent().run(case)


def test_public_snapshot_preserves_uncertain_versions(case):
    from biosbom_agentkg.multiagent.models import Case

    path = Path(__file__).resolve().parents[1] / "examples/public-snapshot-case.json"
    public_case = Case.model_validate_json(path.read_text())
    result = CollectorAgent().run(public_case)
    assert {d.component_ref: d.status for d in result.dispositions} == {
        "requests-affected": "matched",
        "requests-newer": "unmatched",
        "requests-unknown": "version_missing",
        "werkzeug-affected": "matched",
        "werkzeug-newer": "unmatched",
        "unrelated": "unmatched",
    }
