import copy

import pytest

from biosbom_agentkg.multiagent.agents import VerificationAgent
from biosbom_agentkg.multiagent.engine import run_case
from biosbom_agentkg.multiagent.versions import affected_match, range_contains


@pytest.mark.parametrize(
    "kind,version,events,expected",
    [
        ("ECOSYSTEM", "1.9", [{"introduced": "0"}, {"fixed": "2.0"}], True),
        ("ECOSYSTEM", "2.0", [{"introduced": "0"}, {"fixed": "2.0"}], False),
        ("ECOSYSTEM", "2.0rc1", [{"introduced": "0"}, {"fixed": "2.0"}], True),
        ("ECOSYSTEM", "2.0.post1", [{"introduced": "0"}, {"fixed": "2.0"}], False),
        ("ECOSYSTEM", "1!1.0", [{"introduced": "0"}, {"fixed": "2.0"}], False),
        ("ECOSYSTEM", "1.0+patched", [{"introduced": "0"}, {"fixed": "2.0"}], None),
        ("ECOSYSTEM", "2.0", [{"introduced": "0"}, {"last_affected": "2.0"}], True),
        ("ECOSYSTEM", "2.0.1", [{"introduced": "0"}, {"last_affected": "2.0"}], False),
        ("ECOSYSTEM", "2.0", [{"introduced": "0"}, {"limit": "2.0"}], False),
        ("ECOSYSTEM", "2.0", [{"introduced": "0"}, {"limit": "*"}], True),
        ("ECOSYSTEM", "2.0", [{"introduced": "0"}, {"limit": "1"}, {"limit": "3"}], True),
        ("ECOSYSTEM", "2.0", [{"fixed": "2.0"}], None),
        ("ECOSYSTEM", "2.0", [{"introduced": "0", "fixed": "3"}], None),
        ("ECOSYSTEM", "bad", [{"introduced": "0"}], None),
        ("ECOSYSTEM", "1.0", [{"introduced": "0"}, {"fixed": "bad"}], None),
        ("ECOSYSTEM", "1.0", [{"introduced": "0"}, {"fixed": "2"}, {"last_affected": "3"}], None),
        ("ECOSYSTEM", "1.0", [{"introduced": "1"}, {"fixed": "1.0"}], None),
        ("SEMVER", "1.2.3-alpha.2", [{"introduced": "1.2.3-alpha.1"}, {"fixed": "1.2.3"}], True),
        ("SEMVER", "1.2.3+build.9", [{"introduced": "0"}, {"fixed": "1.2.3"}], False),
        ("SEMVER", "1.2", [{"introduced": "0"}], None),
        ("SEMVER", "1.02.3", [{"introduced": "0"}], None),
        ("SEMVER", "0.0.0-alpha", [{"introduced": "0"}], True),
        ("GIT", "abcdef", [{"introduced": "0"}], None),
    ],
)
def test_osv_boundary_semantics(kind, version, events, expected):
    assert range_contains(version, {"type": kind, "events": events}, "PyPI") is expected


def test_unsorted_disjoint_ranges_and_unknown_ecosystem():
    span = {
        "type": "ECOSYSTEM",
        "events": [{"fixed": "4"}, {"introduced": "3"}, {"fixed": "2"}, {"introduced": "1"}],
    }
    assert [range_contains(v, span, "PyPI") for v in ["0.9", "1", "2", "3", "4"]] == [
        False,
        True,
        False,
        True,
        False,
    ]
    assert range_contains("1", span, "Conda") is None


def test_union_and_git_only_uncertainty():
    row = {
        "package": {"ecosystem": "PyPI"},
        "ranges": [
            {"type": "GIT", "events": [{"introduced": "0"}]},
            {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2"}]},
        ],
    }
    assert affected_match("2", row)[0] is None
    assert affected_match("1", row)[0] == "range_version"
    row["ranges"].pop()
    assert affected_match("2", row)[0] == "ambiguous"
    row["versions"] = ["2"]
    assert affected_match("2", row)[0] == "exact_version"


def test_positive_and_unknown_union_never_silently_clears():
    row = {
        "package": {"ecosystem": "PyPI"},
        "ranges": [
            {"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "2"}]},
            {"type": "FUTURE", "events": [{"introduced": "0"}]},
        ],
    }
    assert affected_match("1", row)[0] == "range_version"
    assert affected_match("2", row)[0] == "ambiguous"
    row["ranges"] = "broken"
    assert affected_match("2", row)[0] == "ambiguous"


def test_range_finding_is_verified_and_cannot_be_downgraded(case):
    case.sbom["components"] = [
        {"bom-ref": "one", "name": "example", "version": "1.5", "purl": "pkg:pypi/example@1.5"}
    ]
    case.advisories = [
        {
            "id": "TEST",
            "affected": [
                {
                    "package": {"ecosystem": "PyPI", "name": "example"},
                    "ranges": [
                        {"type": "ECOSYSTEM", "events": [{"introduced": "1"}, {"fixed": "2"}]}
                    ],
                }
            ],
        }
    ]
    result = run_case(case)
    assert result.audit.passed
    assert result.collection.findings[0].match == "range_version"
    assert result.decisions.assessments[0].status == "affected"
    tampered = copy.deepcopy(result.decisions)
    tampered.assessments[0].status = "under_investigation"
    assert (
        not VerificationAgent().run(case, result.collection, result.context_packet, tampered).passed
    )
