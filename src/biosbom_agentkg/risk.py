from __future__ import annotations

from dataclasses import dataclass

from .schemas import AssetContext, Component, VEXState, VEXStatus, Vulnerability


@dataclass(frozen=True)
class RiskWeights:
    cvss: float = 1.0
    epss: float = 10.0
    kev: float = 2.0
    asset_criticality: float = 0.8
    data_sensitivity: float = 0.7
    exposure: float = 0.8
    dependency_depth: float = 0.3
    vex_mitigation: float = 2.0
    security_control: float = 0.4


VEX_MITIGATION_SCORE = {
    VEXState.AFFECTED: 0.0,
    VEXState.UNDER_INVESTIGATION: 0.5,
    VEXState.FIXED: 1.0,
    VEXState.NOT_AFFECTED: 2.0,
}


def calculate_risk_score(
    component: Component,
    vulnerability: Vulnerability,
    asset_context: AssetContext,
    vex_status: VEXStatus,
    weights: RiskWeights | None = None,
) -> float:
    weights = weights or RiskWeights()
    kev_flag = 1.0 if vulnerability.kev else 0.0
    mitigation = VEX_MITIGATION_SCORE[vex_status.state]

    score = (
        weights.cvss * vulnerability.cvss
        + weights.epss * vulnerability.epss
        + weights.kev * kev_flag
        + weights.asset_criticality * asset_context.criticality
        + weights.data_sensitivity * asset_context.data_sensitivity
        + weights.exposure * asset_context.exposure
        + weights.dependency_depth * component.dependency_depth
        - weights.vex_mitigation * mitigation
        - weights.security_control * asset_context.security_control_score
    )
    return round(max(score, 0.0), 3)
