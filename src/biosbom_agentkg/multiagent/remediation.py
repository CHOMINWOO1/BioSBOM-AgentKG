"""Evidence-derived upgrade candidates. No package manager, shell, patch or deployment execution."""
from __future__ import annotations

from packaging.version import InvalidVersion, Version
from semver import Version as SemVersion

from .evidence import CollectorAgent, digest, package_matches
from .versions import affected_match
from .models import Case


def discovery_plan(acquisition):
    case = Case.model_validate(acquisition["case"])
    if digest(case) != acquisition["case_sha256"]:
        raise ValueError("acquisition_hash_mismatch")
    plan = remediation_plan(case)
    plan["acquisition_status"] = acquisition["status"]
    if acquisition["status"] != "complete":
        for item in plan["items"]:
            item.update(candidate_version=None, status="manual_investigation_incomplete_lookup")
        plan["notice"] = "Lookup is incomplete. No upgrade candidate is endorsed; resolve uncovered queries first. No changes executed."
    plan.pop("plan_sha256")
    return {**plan, "plan_sha256": digest(plan)}


def remediation_plan(case):
    collection = CollectorAgent().run(case)
    items = []
    for component in collection.sbom.components:
        findings = [f for f in collection.findings if f.component_ref == component.bom_ref]
        if not findings:
            continue
        records = [r for r in case.advisories if not r.get("withdrawn") and
                   any(package_matches(component, a["package"]) for a in r.get("affected", []))]
        affected = [a for r in records for a in r.get("affected", []) if package_matches(component, a["package"])]
        candidates = {}
        parser = Version if component.ecosystem == "pypi" else SemVersion.parse if component.ecosystem == "npm" else None
        if parser and component.version and all(f.match in {"exact_version", "range_version"} for f in findings):
            for a in affected:
                spans = a.get("ranges", [])
                if not isinstance(spans, list):
                    continue
                for span in spans:
                    if not isinstance(span, dict) or span.get("type") not in {"ECOSYSTEM", "SEMVER"}:
                        continue
                    events = span.get("events", [])
                    if not isinstance(events, list):
                        continue
                    for event in events:
                        fixed = event.get("fixed") if isinstance(event, dict) else None
                        if not isinstance(fixed, str):
                            continue
                        try:
                            parsed = parser(fixed)
                            prerelease = parsed.is_prerelease or parsed.is_devrelease or parsed.local is not None if isinstance(parsed, Version) else bool(parsed.prerelease or parsed.build)
                            if prerelease or parsed <= parser(component.version):
                                continue
                            if all(affected_match(fixed, record)[0] is None for record in affected):
                                candidates[fixed] = parsed
                        except (ValueError, InvalidVersion, TypeError):
                            continue
        fixes = sorted(candidates, key=lambda v: candidates[v])
        parents = sorted(parent for parent, deps in collection.sbom.dependencies.items()
                         if component.bom_ref in deps)
        items.append({"component_ref": component.bom_ref, "package": component.name,
                      "installed_version": component.version,
                      "status": "candidate_requires_review" if fixes else "manual_investigation",
                      "candidate_version": fixes[0] if fixes else None,
                      "advisories": [f.advisory_id for f in findings],
                      "evidence_ids": sorted({e for f in findings for e in f.evidence_ids}),
                      "parent_components": parents,
                      "checks": ["Confirm release availability and provenance",
                                 "Resolve all dependency and lockfile constraints",
                                 "Run pipeline and scientific-result regression checks",
                                 "Review fresh advisories; capture rollback before any change"]})
    body = {"schema_version": "1.0", "case_sha256": digest(case),
            "status": "requires_human_review", "items": items,
            "notice": "Candidates are outside supplied advisory ranges only. Availability, compatibility and safety are unverified. No changes executed."}
    return {**body, "plan_sha256": digest(body)}
