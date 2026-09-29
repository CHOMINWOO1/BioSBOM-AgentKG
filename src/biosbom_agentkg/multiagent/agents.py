"""Independent specialist contracts and an authoritative evidence verifier."""

from __future__ import annotations

from .models import Assessment, Audit, Case, Collection, ContextPacket, DecisionPacket, Issue


class ContextAgent:
    role = "context"

    def run(self, case: Case, collection: Collection) -> ContextPacket:
        ctx = case.context
        concerns = []
        for value, code in [
            (ctx.data_sensitivity >= 7, "sensitive_data"),
            (ctx.exposure >= 7, "external_exposure"),
            (ctx.criticality >= 7, "critical_asset"),
            (ctx.security_control_score <= 3, "weak_controls"),
        ]:
            if value:
                concerns.append(code)
        return ContextPacket(
            concerns=concerns,
            evidence_ids=[e.evidence_id for e in collection.evidence if e.kind == "context"],
        )


def minimum_priority(finding, context):
    if finding.match != "exact_version" or finding.cvss is None:
        return "review"
    if finding.kev is True or (finding.cvss >= 9 and context.exposure >= 7):
        return "urgent"
    if (
        finding.cvss >= 7
        or (finding.epss is not None and finding.epss >= 0.5)
        or (context.data_sensitivity >= 7 and context.criticality >= 7)
    ):
        return "high"
    return "normal"


class TriageAgent:
    role = "triage"

    def run(self, case: Case, collection: Collection, context: ContextPacket) -> DecisionPacket:
        return DecisionPacket(
            assessments=[
                Assessment(
                    finding_id=f.finding_id,
                    status="affected" if f.match == "exact_version" else "under_investigation",
                    priority=minimum_priority(f, case.context),
                    evidence_ids=f.evidence_ids,
                )
                for f in collection.findings
            ]
        )


class VerificationAgent:
    """Checks evidence and conservative policy; an LLM cannot waive these checks."""

    role = "verifier"

    def check_context(self, case: Case, collection: Collection, packet: ContextPacket) -> Audit:
        expected = ContextAgent().run(case, collection)
        issues = []
        if sorted(packet.concerns) != sorted(expected.concerns):
            issues.append(
                Issue(
                    code="context_mismatch",
                    target="context",
                    message="Use only concerns supported by context thresholds",
                )
            )
        if sorted(packet.evidence_ids) != sorted(expected.evidence_ids):
            issues.append(
                Issue(
                    code="context_evidence",
                    target="context",
                    message="Context citations must identify the context snapshot",
                )
            )
        return Audit(passed=not issues, issues=issues)

    def run(
        self, case: Case, collection: Collection, context: ContextPacket, packet: DecisionPacket
    ) -> Audit:
        issues = self.check_context(case, collection, context).issues
        by_id = {f.finding_id: f for f in collection.findings}
        observed = [row.finding_id for row in packet.assessments]
        if set(observed) != set(by_id) or len(observed) != len(set(observed)):
            issues.append(
                Issue(
                    code="coverage",
                    target="triage",
                    message="Every finding must occur once; unknown IDs are forbidden",
                )
            )
        ranks = {"urgent": 0, "high": 1, "normal": 2}
        for row in packet.assessments:
            finding = by_id.get(row.finding_id)
            if not finding:
                continue

            def add(code, message, target=row.finding_id):
                issues.append(Issue(code=code, target=target, message=message))

            expected_status = (
                "affected" if finding.match == "exact_version" else "under_investigation"
            )
            if row.status != expected_status:
                add(
                    "unsupported_status",
                    "Status must follow version evidence; no exploitability claim",
                )
            if sorted(row.evidence_ids) != sorted(finding.evidence_ids):
                add(
                    "evidence_mismatch",
                    "Citations must cover this finding's SBOM, advisory and context",
                )
            floor = minimum_priority(finding, case.context)
            if floor == "review":
                if row.priority != "review":
                    add(
                        "review_required",
                        "Uncertain version or missing severity needs manual review",
                    )
            elif row.priority == "review" or ranks[row.priority] > ranks[floor]:
                add("priority_downgrade", "Priority cannot be below the configured policy floor")
        return Audit(passed=not issues, issues=issues)


def specialist_payload(role, case, collection, context=None, feedback=None):
    # Advisory descriptions cannot enter the prompt; only typed, normalized fields are shared.
    payload = {
        "asset": case.context.model_dump(),
        "evidence": [e.model_dump() for e in collection.evidence],
        "feedback": [i.model_dump() for i in (feedback or [])],
    }
    if role == "context":
        payload["policy"] = {
            "concern_threshold": 7,
            "weak_controls_at_most": 3,
            "required_concerns": "all and only threshold-supported concerns",
        }
    else:
        payload["findings"] = [f.model_dump() for f in collection.findings]
        payload["context_analysis"] = context.model_dump() if context else None
        payload["policy"] = {
            "minimum_priorities": {
                f.finding_id: minimum_priority(f, case.context) for f in collection.findings
            },
            "affected": "exact_version only; not proof of exploitation",
            "uncertainty": "retain review priority; never invent not_affected",
            "coverage": "every finding exactly once with all its evidence IDs",
            "escalation": "urgent > high > normal; cannot downgrade",
        }
        if role == "single":
            payload["context_policy"] = {
                "concern_threshold": 7,
                "weak_controls_at_most": 3,
                "required_concerns": "all threshold-supported concerns",
            }
    return payload
