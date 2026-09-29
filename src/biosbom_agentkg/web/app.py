from __future__ import annotations

import io
import json
import secrets
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import Field

from ..multiagent.evidence import CollectorAgent
from ..multiagent.models import Case, Record, RunConfig
from ..multiagent.provider import ChatProvider
from ..multiagent.storage import verify_run
from .jobs import Conflict, JobService
from .security import BrowserBoundary

ASSETS = Path(__file__).parent


class Submission(Record):
    case: Case
    config: RunConfig = Field(default_factory=RunConfig)
    request_key: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    llm_acknowledged: bool = False


class Retry(Record):
    request_key: str = Field(min_length=8, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    llm_acknowledged: bool = False


class Review(Record):
    decision: Literal["approve", "hold", "reject"]
    reviewer: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=2000)


def validate_workload(case):
    raw = case.sbom.get("sbom", case.sbom)
    rows = raw.get("components", raw.get("packages", [])) if isinstance(raw, dict) else []
    if (
        not isinstance(rows, list)
        or len(rows) > 2000
        or ((len(rows) + 1) * max(1, len(case.advisories)) > 20000)
    ):
        raise ValueError("workload_limit")
    try:
        return CollectorAgent().run(case)
    except (TypeError, AttributeError, KeyError) as exc:
        raise ValueError("invalid_nested_input") from exc


def create_app(
    data_dir=Path("runs/workbench"), *, port=8876, provider_factory=ChatProvider.from_env
):
    service = JobService(Path(data_dir), provider_factory)

    @asynccontextmanager
    async def lifespan(app):
        service.start()
        try:
            yield
        finally:
            service.close()

    app = FastAPI(
        title="BioSBOM Workbench",
        version="0.4.2",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.jobs = service
    app.add_middleware(BrowserBoundary, port=port, secret=secrets.token_bytes(32))
    app.mount("/static", StaticFiles(directory=ASSETS / "static"), name="static")

    @app.exception_handler(RequestValidationError)
    async def bad_schema(request, exc):
        # FastAPI's default includes rejected input values. Keep them private.
        return JSONResponse(
            {
                "error": "invalid_request",
                "fields": [".".join(str(x) for x in e["loc"]) for e in exc.errors()][:12],
            },
            status_code=422,
        )

    @app.exception_handler(Conflict)
    @app.exception_handler(FileExistsError)
    async def conflict(request, exc):
        code = str(exc) if isinstance(exc, Conflict) else "review_already_recorded"
        return JSONResponse({"error": code}, status_code=409)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({"error": "not_found"}, status_code=404)

    @app.exception_handler(ValueError)
    @app.exception_handler(OSError)
    async def invalid(request, exc):
        known = {
            "workload_limit": "workload_limit",
            "Artifact integrity check failed": "artifact_hash_mismatch",
            "Input/evidence mismatch": "evidence_mismatch",
            "Independent evidence recheck failed": "audit_mismatch",
            "Unexpected run manifest": "manifest_invalid",
        }
        return JSONResponse(
            {
                "error": "invalid_input_or_artifact",
                "reason": known.get(str(exc), type(exc).__name__),
            },
            status_code=422,
        )

    @app.get("/")
    def index():
        return FileResponse(ASSETS / "static" / "index.html")

    @app.get("/api/session")
    def session(request: Request):
        try:
            provider = provider_factory()
            ready = bool(provider.models)
        except (ValueError, OSError):
            ready = False
        return {
            "csrf": request.scope["biosbom_csrf"],
            "llm_configured": ready,
            "version": "0.4.2",
            "local_only": True,
            "limits": {
                "request_bytes": 2000000,
                "components": 2000,
                "candidate_pairs": 20000,
                "active_jobs": 20,
            },
            "examples": ["rnaseq-case", "public-snapshot-case"],
        }

    @app.get("/api/health")
    def health():
        alive = bool(service.thread and service.thread.is_alive())
        return JSONResponse({"worker_alive": alive}, status_code=200 if alive else 503)

    @app.get("/api/examples/{name}")
    def example(name: Literal["rnaseq-case", "public-snapshot-case"]):
        return json.loads((ASSETS / "fixtures" / f"{name}.json").read_text(encoding="utf-8"))

    @app.get("/api/jobs")
    def jobs(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100)):
        return service.list(offset, limit)

    @app.post("/api/jobs", status_code=202)
    def submit(body: Submission):
        validate_workload(body.case)
        if body.config.mode == "llm":
            if not body.llm_acknowledged:
                raise Conflict("llm_consent_required")
            provider_factory()  # fail before queuing if configuration is incomplete
        return service.submit(body.case, body.config, body.request_key)

    @app.post("/api/preview")
    def preview(case: Case):
        """Read-only offline preflight: no jobs, artifacts, model or network calls."""
        collection = validate_workload(case)
        return {
            "components": len(collection.sbom.components),
            "advisories": len(case.advisories),
            "findings": len(collection.findings),
            "dispositions": [row.model_dump() for row in collection.dispositions],
            "matches": [row.match for row in collection.findings],
            "warnings": collection.warnings,
            "source_format": collection.sbom.source_format,
            "synthetic": case.synthetic,
        }

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        data = service.get(job_id)
        if data["state"] in {"awaiting_human", "blocked"}:
            _, result = verify_run(service.artifacts(job_id))
            data["result"] = result.model_dump(mode="json")
            review = service.artifacts(job_id) / "human-review.json"
            if review.exists():
                if review.is_symlink():
                    raise ValueError("symlink_refused")
                data["review"] = json.loads(review.read_text(encoding="utf-8"))
        return data

    @app.get("/api/jobs/{job_id}/events")
    def events(job_id: str, after: int = Query(0, ge=0)):
        return service.events(job_id, after)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        return service.cancel(job_id)

    @app.post("/api/jobs/{job_id}/retry", status_code=202)
    def retry(job_id: str, body: Retry):
        return service.retry(job_id, body.request_key, body.llm_acknowledged)

    @app.post("/api/jobs/{job_id}/review")
    def review(job_id: str, body: Review):
        return service.review(job_id, body.decision, body.reviewer, body.reason)

    @app.get("/api/jobs/{job_id}/evidence/{evidence_id}")
    def evidence(job_id: str, evidence_id: str):
        service.get(job_id)
        case, result = verify_run(service.artifacts(job_id))
        record = next((e for e in result.collection.evidence if e.evidence_id == evidence_id), None)
        if record is None:
            raise KeyError()
        value = case.model_dump(mode="json")
        for part in record.pointer.strip("/").split("/"):
            value = value[int(part)] if isinstance(value, list) else value[part]
        return {"record": record.model_dump(), "source": value}

    @app.get("/api/jobs/{job_id}/download/{kind}")
    def download(job_id: str, kind: Literal["bundle", "html", "json", "csv"]):
        service.get(job_id)
        root = service.artifacts(job_id)
        verify_run(root)
        if kind != "bundle":
            name = {
                "html": "report.html",
                "json": "result.json",
                "csv": "package-dispositions.csv",
            }[kind]
            return FileResponse(
                root / name,
                filename=f"biosbom-{job_id}.{kind}",
                media_type="application/octet-stream",
            )
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        names = [*manifest["files"], "manifest.json"]
        if (root / "human-review.json").is_file():
            names.append("human-review.json")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in names:
                path = root / name
                if path.is_symlink():
                    raise ValueError("symlink_refused")
                archive.writestr(name, path.read_bytes())
        return Response(
            buf.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="biosbom-{job_id}.zip"'},
        )

    return app
