from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .schemas import Component, NormalizedSBOM


def normalize_sbom_document(
    document: Mapping[str, Any],
    *,
    asset_id: str | None = None,
) -> NormalizedSBOM:
    """Normalize a supported SBOM JSON document into the prototype model."""

    document = _unwrap_sbom_document(document)
    if document.get("bomFormat") == "CycloneDX":
        return normalize_cyclonedx_bom(document, asset_id=asset_id)
    if _string_or_none(document.get("spdxVersion")) is not None:
        return normalize_spdx_document(document, asset_id=asset_id)
    raise ValueError("Unsupported SBOM JSON document. Expected CycloneDX or SPDX JSON")


def normalize_cyclonedx_bom(
    bom: Mapping[str, Any],
    *,
    asset_id: str | None = None,
) -> NormalizedSBOM:
    """Normalize the CycloneDX subset needed for the first SBOM-KG prototype."""

    if bom.get("bomFormat") != "CycloneDX":
        raise ValueError("Only CycloneDX JSON SBOMs are supported by this normalizer")

    metadata_component = _as_mapping(_as_mapping(bom.get("metadata")).get("component"))
    root_component_ref = _string_or_none(metadata_component.get("bom-ref"))
    resolved_asset_id = asset_id or _asset_id_from_metadata(metadata_component, bom)

    components = [
        _normalize_component(component)
        for component in bom.get("components", [])
        if isinstance(component, Mapping)
    ]

    root_component = _normalize_root_component(metadata_component)
    if root_component is not None:
        components.insert(0, root_component)

    dependencies = _normalize_dependencies(bom.get("dependencies", []))
    depths = _calculate_dependency_depths(root_component_ref, dependencies)
    if depths:
        components = [
            component.model_copy(
                update={
                    "dependency_depth": depths.get(
                        _component_key(component),
                        component.dependency_depth,
                    )
                }
            )
            for component in components
        ]

    return NormalizedSBOM(
        asset_id=resolved_asset_id,
        source_format="cyclonedx-json",
        bom_serial_number=_string_or_none(bom.get("serialNumber")),
        root_component_ref=root_component_ref,
        components=components,
        dependencies=dependencies,
    )


def normalize_spdx_document(
    document: Mapping[str, Any],
    *,
    asset_id: str | None = None,
) -> NormalizedSBOM:
    """Normalize the SPDX JSON subset needed for the first SBOM-KG prototype."""

    if _string_or_none(document.get("spdxVersion")) is None:
        raise ValueError("Only SPDX JSON documents with spdxVersion are supported")

    packages = [
        _normalize_spdx_package(package)
        for package in document.get("packages", [])
        if isinstance(package, Mapping)
    ]
    root_component_ref = _spdx_root_component_ref(document)
    if root_component_ref is None and packages:
        root_component_ref = packages[0].bom_ref

    dependencies = _normalize_spdx_relationships(document.get("relationships", []))
    depths = _calculate_dependency_depths(root_component_ref, dependencies)
    if depths:
        packages = [
            package.model_copy(
                update={
                    "dependency_depth": depths.get(
                        _component_key(package),
                        package.dependency_depth,
                    )
                }
            )
            for package in packages
        ]

    return NormalizedSBOM(
        asset_id=asset_id or _spdx_asset_id(document),
        source_format="spdx-json",
        bom_serial_number=_string_or_none(document.get("documentNamespace")),
        root_component_ref=root_component_ref,
        components=packages,
        dependencies=dependencies,
    )


def _normalize_component(raw: Mapping[str, Any]) -> Component:
    return Component(
        name=str(raw.get("name", "unknown")),
        version=_string_or_none(raw.get("version")),
        purl=_string_or_none(raw.get("purl")),
        cpe=_first_cpe(raw),
        bom_ref=_string_or_none(raw.get("bom-ref")),
        component_type=_string_or_none(raw.get("type")),
        ecosystem=_ecosystem_from_purl(_string_or_none(raw.get("purl"))),
    )


def _unwrap_sbom_document(document: Mapping[str, Any]) -> Mapping[str, Any]:
    wrapped = document.get("sbom")
    if isinstance(wrapped, Mapping):
        return wrapped
    return document


def _normalize_spdx_package(raw: Mapping[str, Any]) -> Component:
    purl = _spdx_external_ref(raw, "purl")
    return Component(
        name=str(raw.get("name", "unknown")),
        version=_string_or_none(raw.get("versionInfo")),
        purl=purl,
        cpe=(_spdx_external_ref(raw, "cpe23Type") or _spdx_external_ref(raw, "cpe22Type")),
        bom_ref=_string_or_none(raw.get("SPDXID")),
        component_type="package",
        ecosystem=_ecosystem_from_purl(purl),
    )


def _normalize_root_component(raw: Mapping[str, Any]) -> Component | None:
    if not raw:
        return None
    return _normalize_component(raw)


def _normalize_dependencies(raw_dependencies: Any) -> dict[str, list[str]]:
    dependencies: dict[str, list[str]] = {}
    if not isinstance(raw_dependencies, list):
        return dependencies

    for dependency in raw_dependencies:
        if not isinstance(dependency, Mapping):
            continue
        ref = _string_or_none(dependency.get("ref"))
        if ref is None:
            continue
        depends_on = dependency.get("dependsOn", [])
        if not isinstance(depends_on, list):
            depends_on = []
        dependencies[ref] = [
            dep for dep in (_string_or_none(item) for item in depends_on) if dep is not None
        ]
    return dependencies


def _normalize_spdx_relationships(raw_relationships: Any) -> dict[str, list[str]]:
    dependencies: dict[str, list[str]] = {}
    if not isinstance(raw_relationships, list):
        return dependencies

    for relationship in raw_relationships:
        if not isinstance(relationship, Mapping):
            continue
        relationship_type = _string_or_none(relationship.get("relationshipType"))
        if relationship_type not in {"DEPENDS_ON", "CONTAINS"}:
            continue
        source_ref = _string_or_none(relationship.get("spdxElementId"))
        target_ref = _string_or_none(relationship.get("relatedSpdxElement"))
        if source_ref is None or target_ref is None:
            continue
        dependencies.setdefault(source_ref, []).append(target_ref)
    return dependencies


def _calculate_dependency_depths(
    root_component_ref: str | None,
    dependencies: Mapping[str, list[str]],
) -> dict[str, int]:
    if root_component_ref is None or root_component_ref not in dependencies:
        return {}

    depths = {root_component_ref: 0}
    queue = [root_component_ref]
    while queue:
        current = queue.pop(0)
        for child in dependencies.get(current, []):
            next_depth = depths[current] + 1
            if child not in depths or next_depth < depths[child]:
                depths[child] = next_depth
                queue.append(child)
    return depths


def _asset_id_from_metadata(metadata_component: Mapping[str, Any], bom: Mapping[str, Any]) -> str:
    for candidate in (
        metadata_component.get("bom-ref"),
        metadata_component.get("name"),
        bom.get("serialNumber"),
    ):
        value = _string_or_none(candidate)
        if value:
            return value
    return "unknown-asset"


def _spdx_asset_id(document: Mapping[str, Any]) -> str:
    for candidate in (
        document.get("name"),
        document.get("documentNamespace"),
        document.get("SPDXID"),
    ):
        value = _string_or_none(candidate)
        if value:
            return value
    return "unknown-asset"


def _spdx_root_component_ref(document: Mapping[str, Any]) -> str | None:
    relationships = document.get("relationships", [])
    if not isinstance(relationships, list):
        return None

    for relationship in relationships:
        if not isinstance(relationship, Mapping):
            continue
        relationship_type = _string_or_none(relationship.get("relationshipType"))
        source_ref = _string_or_none(relationship.get("spdxElementId"))
        target_ref = _string_or_none(relationship.get("relatedSpdxElement"))
        if relationship_type == "DESCRIBES" and source_ref == "SPDXRef-DOCUMENT":
            return target_ref
    return None


def _first_cpe(raw: Mapping[str, Any]) -> str | None:
    cpe = _string_or_none(raw.get("cpe")) or _string_or_none(raw.get("cpe23"))
    if cpe is not None:
        return cpe

    properties = raw.get("properties", [])
    if not isinstance(properties, list):
        return None

    for prop in properties:
        if not isinstance(prop, Mapping):
            continue
        name = _string_or_none(prop.get("name"))
        value = _string_or_none(prop.get("value"))
        if name and value and "cpe" in name.lower():
            return value
    return None


def _spdx_external_ref(raw: Mapping[str, Any], reference_type: str) -> str | None:
    external_refs = raw.get("externalRefs", [])
    if not isinstance(external_refs, list):
        return None

    for external_ref in external_refs:
        if not isinstance(external_ref, Mapping):
            continue
        if _string_or_none(external_ref.get("referenceType")) != reference_type:
            continue
        value = _string_or_none(external_ref.get("referenceLocator"))
        if value is not None:
            return value
    return None


def _ecosystem_from_purl(purl: str | None) -> str | None:
    if purl is None or not purl.startswith("pkg:"):
        return None
    without_prefix = purl[4:]
    if "/" not in without_prefix:
        return None
    return without_prefix.split("/", 1)[0]


def _component_key(component: Component) -> str | None:
    return component.bom_ref or component.purl or component.cpe or component.name


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
