from biosbom_agentkg import (
    AssetContext,
    Component,
    VEXStatus,
    Vulnerability,
    calculate_risk_score,
)
from biosbom_agentkg.schemas import VEXState


def test_risk_score_increases_for_kev_and_sensitive_assets() -> None:
    component = Component(name="openssl", version="3.0.0", dependency_depth=1)
    vulnerability = Vulnerability(cve_id="CVE-2099-0001", cvss=8.8, epss=0.7, kev=True)
    asset = AssetContext(
        asset_id="wgbs-prod",
        criticality=9,
        data_sensitivity=10,
        exposure=7,
        security_control_score=2,
    )
    vex = VEXStatus(state=VEXState.UNDER_INVESTIGATION)

    assert calculate_risk_score(component, vulnerability, asset, vex) > 25


def test_not_affected_vex_reduces_score() -> None:
    component = Component(name="example-lib", dependency_depth=4)
    vulnerability = Vulnerability(cve_id="CVE-2099-0002", cvss=7.0, epss=0.3)
    asset = AssetContext(
        asset_id="test-pipeline",
        criticality=3,
        data_sensitivity=2,
        exposure=1,
        security_control_score=8,
    )

    affected = calculate_risk_score(
        component,
        vulnerability,
        asset,
        VEXStatus(state=VEXState.AFFECTED),
    )
    not_affected = calculate_risk_score(
        component,
        vulnerability,
        asset,
        VEXStatus(state=VEXState.NOT_AFFECTED),
    )

    assert not_affected < affected
