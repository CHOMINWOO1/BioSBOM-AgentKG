from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class VEXState(StrEnum):
    AFFECTED = "affected"
    NOT_AFFECTED = "not_affected"
    FIXED = "fixed"
    UNDER_INVESTIGATION = "under_investigation"


class Component(BaseModel):
    name: str
    version: str | None = None
    purl: str | None = None
    cpe: str | None = None
    bom_ref: str | None = None
    component_type: str | None = None
    ecosystem: str | None = None
    dependency_depth: int = Field(default=0, ge=0)


class Vulnerability(BaseModel):
    cve_id: str
    cvss: float = Field(ge=0, le=10)
    epss: float = Field(default=0.0, ge=0, le=1)
    kev: bool = False
    fixed_version: str | None = None
    aliases: list[str] = Field(default_factory=list)
    summary: str | None = None
    source: str | None = None


class VEXStatus(BaseModel):
    state: VEXState
    justification: str | None = None


class AssetContext(BaseModel):
    asset_id: str
    criticality: float = Field(ge=0, le=10)
    data_sensitivity: float = Field(ge=0, le=10)
    exposure: float = Field(ge=0, le=10)
    security_control_score: float = Field(default=0.0, ge=0, le=10)


class NormalizedSBOM(BaseModel):
    asset_id: str
    source_format: str
    bom_serial_number: str | None = None
    root_component_ref: str | None = None
    components: list[Component] = Field(default_factory=list)
    dependencies: dict[str, list[str]] = Field(default_factory=dict)


class EvidenceSource(BaseModel):
    evidence_id: str
    source_type: str
    source_url: str | None = None
    retrieved_at: str | None = None
    content_hash: str | None = None


class VulnerabilityFinding(BaseModel):
    component_ref: str
    vulnerability: Vulnerability
    vex_status: VEXStatus | None = None
    evidence_ids: list[str] = Field(default_factory=list)
