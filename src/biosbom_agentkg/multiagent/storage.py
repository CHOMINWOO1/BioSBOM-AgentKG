"""Atomic run publication, content checks, and append-only human decision records."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .agents import VerificationAgent
from .evidence import CollectorAgent, digest
from .models import Case, RunResult
from .reporting import render_html, render_markdown


def write_json(path, value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    Path(path).write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def graph_export(result):
    sbom = result.collection.sbom
    asset = "asset:" + digest(sbom.asset_id)[:20]
    nodes = [{"id": asset, "type": "asset", "name": sbom.asset_id}]
    edges = []
    refs = {}
    for component in sbom.components:
        node = "component:" + digest(component.bom_ref)[:20]
        refs[component.bom_ref] = node
        nodes.append(
            {"id": node, "type": "component", "name": component.name, "version": component.version}
        )
        edges.append({"source": asset, "relation": "CONTAINS", "target": node})
    for parent, children in sbom.dependencies.items():
        for child in children:
            if parent in refs and child in refs:
                edges.append(
                    {"source": refs[parent], "relation": "DEPENDS_ON", "target": refs[child]}
                )
    for finding in result.collection.findings:
        nodes.append(
            {
                "id": finding.finding_id,
                "type": "finding",
                "advisory": finding.advisory_id,
                "match": finding.match,
                "evidence_ids": finding.evidence_ids,
            }
        )
        edges.append(
            {
                "source": refs[finding.component_ref],
                "relation": "HAS_CANDIDATE",
                "target": finding.finding_id,
            }
        )
    return {"nodes": nodes, "edges": edges}


def save_run(case: Case, result: RunResult, target: Path):
    target = Path(target)
    if target.exists():
        raise FileExistsError("Output directory already exists; choose a new run directory")
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix=".biosbom-", dir=target.parent))
    try:
        write_json(scratch / "input.json", case)
        write_json(scratch / "result.json", result)
        write_json(scratch / "normalized-sbom.json", result.collection.sbom)
        write_json(scratch / "evidence.json", [e.model_dump() for e in result.collection.evidence])
        write_json(scratch / "audit.json", result.audit)
        write_json(scratch / "graph.json", graph_export(result))
        (scratch / "events.jsonl").write_text(
            "".join(e.model_dump_json() + "\n" for e in result.events), encoding="utf-8"
        )
        with (scratch / "package-dispositions.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(["component_ref", "status", "finding_ids"])
            for row in result.collection.dispositions:
                # Guard spreadsheet formula injection in input-controlled cells.
                ref = row.component_ref
                if ref.startswith(("=", "+", "-", "@", "\t", "\r")):
                    ref = "'" + ref
                writer.writerow([ref, row.status, ";".join(row.finding_ids)])
        (scratch / "report.md").write_text(render_markdown(result), encoding="utf-8")
        (scratch / "report.html").write_text(render_html(result), encoding="utf-8")
        manifest = {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(scratch.iterdir())
        }
        write_json(scratch / "manifest.json", {"schema_version": "1", "files": manifest})
        # Reserve the target exclusively so concurrent writers cannot replace a run.
        target.mkdir()
        for child in sorted(scratch.iterdir(), key=lambda p: p.name == "manifest.json"):
            os.replace(child, target / child.name)
    finally:
        shutil.rmtree(scratch)


def verify_run(target: Path) -> tuple[Case, RunResult]:
    target = Path(target)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    required = {
        "input.json",
        "result.json",
        "normalized-sbom.json",
        "evidence.json",
        "audit.json",
        "graph.json",
        "events.jsonl",
        "package-dispositions.csv",
        "report.md",
        "report.html",
    }
    if set(manifest["files"]) != required:
        raise ValueError("Unexpected run manifest")
    for name, expected in manifest["files"].items():
        path = target / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Artifact integrity check failed")
    case = Case.model_validate_json((target / "input.json").read_text(encoding="utf-8"))
    result = RunResult.model_validate_json((target / "result.json").read_text(encoding="utf-8"))
    if digest(case) != result.input_sha256 or digest(CollectorAgent(
        legacy=result.schema_version == "2.0", canonical_names=result.schema_version == "2.2"
    ).run(case)) != digest(
        result.collection
    ):
        raise ValueError("Input/evidence mismatch")
    if result.status == "awaiting_human":
        if result.context_packet is None or result.decisions is None:
            raise ValueError("Verified decisions missing")
        audit = VerificationAgent().run(
            case, result.collection, result.context_packet, result.decisions
        )
        if not audit.passed or not result.audit.passed:
            raise ValueError("Independent evidence recheck failed")
    return case, result


def record_review(target: Path, decision: str, reviewer: str, reason: str):
    _, result = verify_run(target)
    if decision not in {"approve", "hold", "reject"}:
        raise ValueError("Invalid review decision")
    if not reviewer.strip() or not reason.strip():
        raise ValueError("Reviewer and reason are required")
    if decision == "approve" and result.status != "awaiting_human":
        raise ValueError("Blocked runs cannot be approved; create and verify a corrected run")
    record = {
        "decision": decision,
        "reviewer": reviewer,
        "reason": reason,
        "reviewed_result_sha256": digest(result),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = Path(target) / "human-review.json"
    # A final decision is immutable; further work must have a new run ID.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return record
