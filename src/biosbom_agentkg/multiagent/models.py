from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from biosbom_agentkg.schemas import AssetContext, NormalizedSBOM


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Intelligence(Record):
    advisory_id: str = Field(min_length=1)
    cvss: float | None = Field(default=None, ge=0, le=10)
    epss: float | None = Field(default=None, ge=0, le=1)
    kev: bool | None = None
    source: str = Field(min_length=1)


class Case(Record):
    name: str = Field(min_length=1, max_length=100)
    synthetic: bool = False
    sbom: dict[str, Any]
    advisories: list[dict[str, Any]] = Field(max_length=10000)
    context: AssetContext
    intelligence: list[Intelligence] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_intelligence(self):
        ids = [item.advisory_id for item in self.intelligence]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate intelligence advisory IDs")
        for value in [
            self.context.criticality,
            self.context.data_sensitivity,
            self.context.exposure,
            self.context.security_control_score,
        ]:
            if not 0 <= value <= 10:
                raise ValueError("Invalid context value")
        return self


class Evidence(Record):
    evidence_id: str
    kind: Literal["sbom", "advisory", "context", "intelligence"]
    sha256: str
    pointer: str


class Finding(Record):
    finding_id: str
    component_ref: str
    component_name: str
    component_version: str | None
    advisory_id: str
    aliases: list[str]
    match: Literal["exact_version", "ambiguous", "version_missing"]
    reason: str
    evidence_ids: list[str]
    cvss: float | None = None
    epss: float | None = None
    kev: bool | None = None


class Disposition(Record):
    component_ref: str
    status: Literal["matched", "ambiguous", "version_missing", "unmatched", "missing_identity"]
    finding_ids: list[str]


class Collection(Record):
    sbom: NormalizedSBOM
    evidence: list[Evidence]
    findings: list[Finding]
    dispositions: list[Disposition]
    warnings: list[str]


Concern = Literal["sensitive_data", "external_exposure", "critical_asset", "weak_controls"]
Priority = Literal["urgent", "high", "normal", "review"]


class ContextPacket(Record):
    concerns: list[Concern]
    evidence_ids: list[str]


class Assessment(Record):
    finding_id: str
    status: Literal["affected", "under_investigation"]
    priority: Priority
    evidence_ids: list[str]


class DecisionPacket(Record):
    assessments: list[Assessment]


class JointPacket(Record):
    context: ContextPacket
    triage: DecisionPacket


class Issue(Record):
    code: str
    target: str
    message: str


class Audit(Record):
    passed: bool
    issues: list[Issue]


class Event(Record):
    sequence: int
    role: str
    attempt: int
    outcome: str
    input_sha256: str
    output_sha256: str | None = None
    issue_codes: list[str] = Field(default_factory=list)


class RunConfig(Record):
    mode: Literal["deterministic", "llm"] = "deterministic"
    architecture: Literal["multi_agent", "single_agent"] = "multi_agent"
    max_revisions: int = Field(default=2, ge=0, le=5)
    max_calls: int = Field(default=8, ge=0, le=30)
    max_completion_tokens: int = Field(default=16000, ge=1, le=100000)
    tokens_per_call: int = Field(default=2000, ge=128, le=8000)
    timeout_seconds: float = Field(default=30, gt=0, le=120)


class RunResult(Record):
    schema_version: str = "2.0"
    case_name: str
    input_sha256: str
    synthetic: bool
    mode: str
    status: Literal["awaiting_human", "blocked"]
    collection: Collection
    context_packet: ContextPacket | None
    decisions: DecisionPacket | None
    audit: Audit
    events: list[Event]
    config: RunConfig
    calls: int
    completion_tokens_reserved: int
    reported_total_tokens: int
    usage_complete: bool
    duration_seconds: float
    models: dict[str, str]
