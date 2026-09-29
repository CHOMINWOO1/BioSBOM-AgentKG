"""Conservative offline OSV matching. Unsupported ranges remain review candidates."""

from __future__ import annotations

import hashlib
import json
from urllib.parse import unquote

from biosbom_agentkg.sbom import normalize_sbom_document

from .models import Case, Collection, Disposition, Evidence, Finding
from .versions import affected_match


def digest(value) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def evidence(kind: str, value, pointer: str) -> Evidence:
    sha = digest(value)
    return Evidence(evidence_id=f"{kind}:{sha}", kind=kind, sha256=sha, pointer=pointer)


def purl_parts(value: str | None) -> tuple[str, str | None] | None:
    if not value or not value.startswith("pkg:") or "/" not in value:
        return None
    # Qualifiers are part of identity: never merge distro/architecture variants.
    text = value.split("#", 1)[0]
    body, _, qualifiers = text.partition("?")
    version = None
    if body.rfind("@") > body.rfind("/"):
        body, version = body.rsplit("@", 1)
    identity = unquote(body) + ("?" + "&".join(sorted(qualifiers.split("&"))) if qualifiers else "")
    return identity, unquote(version) if version else None


ECOSYSTEM = {
    "PyPI": "pypi",
    "npm": "npm",
    "Go": "golang",
    "crates.io": "cargo",
    "Maven": "maven",
    "NuGet": "nuget",
    "Conda": "conda",
}


def package_matches(component, package: dict) -> bool:
    source = purl_parts(package.get("purl"))
    target = purl_parts(component.purl)
    if source and target:
        return source[0] == target[0]
    ecosystem = package.get("ecosystem")
    return bool(
        component.ecosystem
        and ecosystem
        and ECOSYSTEM.get(ecosystem, ecosystem) == component.ecosystem
        and package.get("name") == component.name
    )


def _raw_validation(case: Case):
    raw = case.sbom.get("sbom", case.sbom)
    if not isinstance(raw, dict):
        raise ValueError("SBOM must be an object")
    key = "components" if raw.get("bomFormat") == "CycloneDX" else "packages"
    rows = raw.get(key, [])
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("Malformed package rows; refusing to silently discard entries")
    # Nested CycloneDX components require flattening with preserved parentage first.
    if any(row.get("components") for row in rows):
        raise ValueError("Nested CycloneDX components are not supported; flatten explicitly")
    metadata = raw.get("metadata", {})
    if not isinstance(metadata, dict) or not isinstance(metadata.get("component", {}), dict):
        raise ValueError("Malformed SBOM metadata")
    root = metadata.get("component", {})
    if root.get("components"):
        raise ValueError("Nested root components are not supported")
    for row in [*rows, root]:
        for field in ["name", "version", "versionInfo", "purl", "bom-ref", "SPDXID"]:
            if row.get(field) is not None and not isinstance(row[field], str):
                raise ValueError("Component identity fields must be strings")
    dep_key = "dependencies" if key == "components" else "relationships"
    dependencies = raw.get(dep_key, [])
    if not isinstance(dependencies, list) or any(not isinstance(row, dict) for row in dependencies):
        raise ValueError("Malformed dependency rows")
    if key == "components" and any(
        not isinstance(row.get("dependsOn", []), list) for row in dependencies
    ):
        raise ValueError("Malformed dependency target list")
    ids = []
    for advisory in case.advisories:
        if not isinstance(advisory.get("id"), str) or not advisory["id"].strip():
            raise ValueError("Advisory ID missing")
        ids.append(advisory["id"])
        if not isinstance(advisory.get("affected", []), list):
            raise ValueError("Malformed advisory affected list")
        for affected in advisory.get("affected", []):
            if not isinstance(affected, dict) or not isinstance(affected.get("package"), dict):
                raise ValueError("Malformed advisory package")
            for field in ["purl", "ecosystem", "name"]:
                value = affected["package"].get(field)
                if value is not None and not isinstance(value, str):
                    raise ValueError("Advisory package identity fields must be strings")
            if not isinstance(affected.get("versions", []), list) or any(
                not isinstance(v, str) for v in affected.get("versions", [])
            ):
                raise ValueError("Malformed advisory versions")
        if not isinstance(advisory.get("aliases", []), list) or any(
            not isinstance(a, str) for a in advisory.get("aliases", [])
        ):
            raise ValueError("Malformed advisory aliases")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate advisory IDs")


class CollectorAgent:
    role = "collector"

    def __init__(self, *, legacy=False):
        self.legacy = legacy

    def run(self, case: Case) -> Collection:
        _raw_validation(case)
        normalized = normalize_sbom_document(case.sbom, asset_id=case.context.asset_id)
        if not normalized.components:
            raise ValueError("SBOM contains no components")
        refs = [
            c.bom_ref or c.purl or f"component-{i}" for i, c in enumerate(normalized.components)
        ]
        if len(set(refs)) != len(refs):
            raise ValueError("Duplicate component identities")
        normalized.components = [
            c.model_copy(update={"bom_ref": ref})
            for c, ref in zip(normalized.components, refs, strict=True)
        ]
        for c in normalized.components:
            parsed = purl_parts(c.purl)
            if parsed and parsed[1]:
                if c.version and c.version != parsed[1]:
                    raise ValueError("Conflicting SBOM version and PURL version")
                c.version = c.version or parsed[1]
        sbom_ev = evidence("sbom", case.sbom, "/sbom")
        ctx_ev = evidence("context", case.context, "/context")
        sources = [sbom_ev, ctx_ev]
        intelligence = {row.advisory_id: row for row in case.intelligence}
        intel_ev = {
            key: evidence("intelligence", row, f"/intelligence/{i}")
            for i, (key, row) in enumerate(intelligence.items())
        }
        sources.extend(intel_ev.values())
        findings, dispositions, warnings = [], [], []
        if not case.advisories:
            warnings.append("empty_advisory_snapshot")
        records = []
        for index, record in enumerate(case.advisories):
            ev = evidence("advisory", record, f"/advisories/{index}")
            sources.append(ev)
            if record.get("withdrawn"):
                warnings.append(f"withdrawn_advisory:{record['id']}")
                continue
            records.append((record, ev))
        for component in normalized.components:
            component_findings = []
            for record, ev in records:
                affected = [
                    a
                    for a in record.get("affected", [])
                    if package_matches(component, a["package"])
                ]
                if not affected:
                    continue
                if not component.version:
                    match, reason = "version_missing", "Installed version is unknown"
                elif not self.legacy:
                    matches = [affected_match(component.version, a) for a in affected]
                    selected = next(
                        (
                            pair
                            for kind in ("exact_version", "range_version", "ambiguous")
                            for pair in matches
                            if pair[0] == kind
                        ),
                        None,
                    )
                    if selected is None:
                        continue
                    match, reason = selected
                elif any(
                    component.version in a.get("versions", [])
                    or (purl_parts(a["package"].get("purl")) or (None, None))[1]
                    == component.version
                    for a in affected
                ):
                    match, reason = (
                        "exact_version",
                        "Installed version explicitly listed as affected",
                    )
                elif any(a.get("ranges") or not a.get("versions") for a in affected):
                    match, reason = (
                        "ambiguous",
                        "Range or incomplete version evidence requires review",
                    )
                else:
                    continue
                item = intelligence.get(record["id"])
                ids = [sbom_ev.evidence_id, ev.evidence_id, ctx_ev.evidence_id]
                if item:
                    ids.append(intel_ev[record["id"]].evidence_id)
                finding = Finding(
                    finding_id="finding:" + digest([component.bom_ref, record["id"]])[:24],
                    component_ref=component.bom_ref,
                    component_name=component.name,
                    component_version=component.version,
                    advisory_id=record["id"],
                    aliases=record.get("aliases", []),
                    match=match,
                    reason=reason,
                    evidence_ids=ids,
                    cvss=item.cvss if item else None,
                    epss=item.epss if item else None,
                    kev=item.kev if item else None,
                )
                component_findings.append(finding)
            findings.extend(component_findings)
            if not component.name or component.name == "unknown":
                status = "missing_identity"
            elif not component.version:
                status = "version_missing"
            elif any(f.match == "ambiguous" for f in component_findings):
                status = "ambiguous"
            else:
                status = "matched" if component_findings else "unmatched"
            dispositions.append(
                Disposition(
                    component_ref=component.bom_ref,
                    status=status,
                    finding_ids=[f.finding_id for f in component_findings],
                )
            )
        for parent, children in normalized.dependencies.items():
            if parent not in refs or any(child not in refs for child in children):
                warnings.append("unresolved_dependency_reference")
        return Collection(
            sbom=normalized,
            evidence=sources,
            findings=findings,
            dispositions=dispositions,
            warnings=sorted(set(warnings)),
        )
