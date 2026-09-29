"""Acquire public reviewed references before predictions; requires gh authentication or public quota."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version

PACKAGES = ["joblib", "scikit-learn", "scipy", "torch", "transformers",
            "tensorflow", "onnx", "mlflow", "gradio", "fastapi"]
ROOT = Path(__file__).resolve().parents[1]


def fetch(url, github=False):
    if github:
        raw = subprocess.check_output(["gh", "api", url.removeprefix("https://api.github.com/")],
                                      timeout=45)
    else:
        with urlopen(Request(url, headers={"User-Agent": "BioSBOM-reference-evaluation"}), timeout=45) as response:
            raw = response.read(8_000_001)
        if len(raw) > 8_000_000:
            raise ValueError("Public response exceeds acquisition limit")
    return json.loads(raw), {"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat(),
                             "raw_sha256": hashlib.sha256(raw).hexdigest()}


def development_ids():
    ids = set()
    for folder in ("benchmarks", "examples", "docs/experiments"):
        for path in (ROOT / folder).rglob("*.json"):
            if "reviewed-reference" in str(path):
                continue
            ids.update(re.findall(r"(?:GHSA-[23456789cfghjmpqrvwx-]+|CVE-\d{4}-\d+)",
                                  path.read_text(encoding="utf-8")))
    return ids


def acquire_package(package, excluded):
    query = urlencode({"ecosystem": "pip", "type": "reviewed", "affects": package,
                       "per_page": 100, "sort": "published", "direction": "asc",
                       "published": "<=2025-12-31"})
    candidates, query_source = fetch("https://api.github.com/advisories?" + query, True)
    metadata, release_source = fetch(f"https://pypi.org/pypi/{package}/json")
    versions = []
    for name, files in metadata["releases"].items():
        try:
            version = Version(name)
        except InvalidVersion:
            continue
        if files and not version.is_prerelease and not version.is_devrelease and version.local is None:
            if any(not f.get("yanked", False) for f in files):
                versions.append((version, name))
    versions.sort()
    exclusions = []
    for advisory in candidates:
        identifier = advisory["ghsa_id"]
        aliases = {x["value"] for x in advisory["identifiers"]}
        reason = None
        if advisory.get("withdrawn_at") or not advisory.get("github_reviewed_at"):
            reason = "withdrawn_or_not_reviewed"
        elif (aliases | {identifier}) & excluded:
            reason = "overlap_with_development_advisory"
        rows = [r for r in advisory["vulnerabilities"]
                if r["package"] == {"ecosystem": "pip", "name": package}
                and r.get("first_patched_version")]
        selected = None
        for row in rows:
            try:
                patch = Version(row["first_patched_version"])
            except InvalidVersion:
                continue
            indices = [i for i, (v, _) in enumerate(versions) if v == patch]
            if indices and 2 <= indices[0] < len(versions) - 1:
                selected = (row, indices[0])
                break
        if reason is None and selected is None:
            reason = "no_patch_with_two_prior_and_one_next_stable_release"
        if reason:
            exclusions.append({"advisory": identifier, "reason": reason})
            continue
        row, index = selected
        osv, osv_source = fetch(f"https://api.osv.dev/v1/vulns/{identifier}")
        if osv.get("withdrawn"):
            exclusions.append({"advisory": identifier, "reason": "osv_withdrawn"})
            continue
        projection = {key: osv[key] for key in ("id", "aliases", "modified", "affected") if key in osv}
        # Retain only fields consumed by the matcher, excluding prose and unneeded database metadata.
        projection["affected"] = [{k: a[k] for k in ("package", "versions", "ranges") if k in a}
                                  for a in osv.get("affected", [])]
        versions_selected = [name for _, name in versions[index - 2:index + 2]]
        cases, labels = [], []
        for position, version in enumerate(versions_selected):
            label_query = urlencode({"ghsa_id": identifier, "ecosystem": "pip", "type": "reviewed",
                                     "affects": f"{package}@{version}", "per_page": 100})
            answer, answer_source = fetch("https://api.github.com/advisories?" + label_query, True)
            if not isinstance(answer, list) or any(r["ghsa_id"] != identifier for r in answer):
                raise ValueError("Unexpected reference response; refusing a negative label")
            name = f"external-{package}-{position}"
            case = {"name": name, "synthetic": True,
                    "sbom": {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": [
                        {"bom-ref": "evaluated-component", "type": "library", "name": package,
                         "version": version, "purl": f"pkg:pypi/{package}@{version}"}]},
                    "advisories": [projection], "context": {"asset_id": "synthetic-external-evaluation",
                    "criticality": 5, "data_sensitivity": 5, "exposure": 5, "security_control_score": 5},
                    "intelligence": []}
            cases.append(case)
            labels.append({"case": name, "package": package, "version": version,
                           "advisory": identifier,
                           "reference": "affected" if answer else "outside_this_advisory",
                           "source": answer_source,
                           "returned_ids": [r["ghsa_id"] for r in answer]})
        return {"package": package, "cases": cases, "labels": labels, "exclusions": exclusions,
                "source": {"advisory": identifier, "aliases": sorted(aliases),
                           "github_reviewed_at": advisory["github_reviewed_at"],
                           "published_at": advisory["published_at"], "html_url": advisory["html_url"],
                           "vulnerable_version_range": row["vulnerable_version_range"],
                           "first_patched_version": row["first_patched_version"],
                           "query": query_source, "pypi": release_source, "osv": osv_source}}
    return {"package": package, "cases": [], "labels": [], "source": None,
            "exclusions": exclusions, "reason": "no_eligible_record_in_first_100"}


def acquire(output):
    output.mkdir(parents=True, exist_ok=False)
    excluded = development_ids()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda package: acquire_package(package, excluded), PACKAGES))
    datasets = {"cases.json": [c for r in results for c in r.pop("cases")],
                "reference-labels.json": [c for r in results for c in r.pop("labels")],
                "provenance.json": results,
                "protocol.json": {"application_commit": "29f15ec795e92e4ed1da827d03a801d568e9a28b",
                                  "packages": PACKAGES, "prior_advisory_ids_excluded": sorted(excluded),
                                  "created_at": datetime.now(timezone.utc).isoformat(),
                                  "label_type": "external_reviewed_service_reference_not_new_human_review"}}
    for name, data in datasets.items():
        (output / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    hashes = {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in datasets}
    (output / "frozen-inputs.json").write_text(json.dumps(hashes, indent=2) + "\n")
    print(json.dumps({"cases": len(datasets["cases.json"]),
                      "packages": sum(r["source"] is not None for r in results)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    acquire(parser.parse_args().output)
