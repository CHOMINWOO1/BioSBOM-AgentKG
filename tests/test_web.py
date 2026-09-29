import io
import json
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from biosbom_agentkg.multiagent.engine import RunCancelled, run_case
from biosbom_agentkg.multiagent.models import RunConfig
from biosbom_agentkg.multiagent.storage import save_run
from biosbom_agentkg.web.app import create_app
from biosbom_agentkg.web.jobs import Conflict, JobService


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "workbench")
    with TestClient(app, base_url="http://localhost:8876") as client:
        client.get("/")
        session = client.get("/api/session").json()
        client.headers["x-biosbom-csrf"] = session["csrf"]
        yield client


def submission(case, **kwargs):
    return {"case": case.model_dump(mode="json"), "request_key": str(uuid.uuid4()), **kwargs}


def test_preview_does_not_queue_or_call_provider(client, case):
    before = client.get("/api/jobs").json()["total"]
    result = client.post("/api/preview", json=case.model_dump(mode="json"))
    assert result.status_code == 200
    assert result.json()["components"] == 5
    assert result.json()["findings"] == 3
    assert len(result.json()["dispositions"]) == 5
    assert client.get("/api/jobs").json()["total"] == before
    case.advisories = []
    empty = client.post("/api/preview", json=case.model_dump(mode="json")).json()
    assert empty["findings"] == 0
    assert "empty_advisory_snapshot" in empty["warnings"]


def test_preview_enforces_same_workload_and_csrf_limits(client, case):
    body = case.model_dump(mode="json")
    body["sbom"]["components"] *= 1000
    response = client.post("/api/preview", json=body)
    assert response.status_code == 422
    assert response.json()["reason"] == "workload_limit"
    client.headers.pop("x-biosbom-csrf")
    assert client.post("/api/preview", json=case.model_dump(mode="json")).status_code == 403


def finished(client, job_id):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200, response.text
        job = response.json()
        if job["state"] not in {"queued", "running"}:
            return job
        time.sleep(0.02)
    pytest.fail("worker did not finish")


def test_full_browser_api_workflow(client, case):
    response = client.post("/api/jobs", json=submission(case))
    assert response.status_code == 202
    job_id = response.json()["id"]
    job = finished(client, job_id)
    assert job["state"] == "awaiting_human"
    assert len(job["result"]["collection"]["findings"]) == 3
    events = client.get(f"/api/jobs/{job_id}/events").json()
    assert events[-1]["role"] == "human_gate"
    assert len(client.get(f"/api/jobs/{job_id}/events?after={events[-2]['id']}").json()) == 1
    evidence_id = job["result"]["collection"]["findings"][0]["evidence_ids"][1]
    evidence = client.get(f"/api/jobs/{job_id}/evidence/{evidence_id}")
    assert evidence.status_code == 200
    assert evidence.json()["record"]["kind"] == "advisory"
    assert "case_json" not in job
    review = {"decision": "approve", "reviewer": "Test Reviewer", "reason": "Evidence inspected"}
    assert client.post(f"/api/jobs/{job_id}/review", json=review).status_code == 200
    assert client.post(f"/api/jobs/{job_id}/review", json=review).status_code == 409
    bundle = client.get(f"/api/jobs/{job_id}/download/bundle")
    with zipfile.ZipFile(io.BytesIO(bundle.content)) as archive:
        assert "manifest.json" in archive.namelist()
        assert json.loads(archive.read("human-review.json"))["decision"] == "approve"
    assert (
        client.get(f"/api/jobs/{job_id}/download/html")
        .headers["content-disposition"]
        .startswith("attachment")
    )
    assert client.get(f"/api/jobs/{job_id}/download/jobs.sqlite3").status_code == 422


@pytest.mark.parametrize(
    "headers,code",
    [
        ({"host": "attacker.test:8876"}, "host_refused"),
        ({"origin": "https://attacker.test"}, "origin_refused"),
        ({"sec-fetch-site": "cross-site"}, "origin_refused"),
        ({"x-biosbom-csrf": "invalid"}, "csrf_refused"),
    ],
)
def test_browser_boundaries(client, case, headers, code):
    response = client.post("/api/jobs", json=submission(case), headers=headers)
    assert response.status_code == 403
    assert response.json()["error"] == code


def test_no_session_no_data(client):
    client.cookies.clear()
    assert client.get("/api/jobs").status_code == 403


def test_cookie_and_content_security(client):
    client.cookies.clear()
    response = client.get("/")
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=Strict" in response.headers["set-cookie"]
    assert "unsafe-inline" not in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/health").json()["worker_alive"]


def test_bounded_workload_and_malformed_nested_values(client, case):
    oversized = case.model_copy(deep=True)
    oversized.sbom["components"] *= 1000
    response = client.post("/api/jobs", json=submission(oversized))
    assert response.status_code == 422
    assert response.json()["reason"] == "workload_limit"
    malformed = case.model_copy(deep=True)
    malformed.sbom["components"][0]["externalReferences"] = [None]
    # Unsupported fields may be ignored; malformed recognized identity cannot be accepted.
    malformed.sbom["components"][0]["purl"] = {"private": "SECRET"}
    response = client.post("/api/jobs", json=submission(malformed))
    assert response.status_code == 422
    assert "SECRET" not in response.text


def test_input_limit_and_private_errors(client, case):
    assert (
        client.post(
            "/api/jobs", content=b"a" * 2000001, headers={"content-type": "application/json"}
        ).status_code
        == 413
    )
    assert (
        client.post("/api/jobs", content="{}", headers={"content-type": "text/plain"}).status_code
        == 415
    )
    body = submission(case)
    body["case"]["context"]["criticality"] = "SECRET_INPUT_VALUE"
    bad = client.post("/api/jobs", json=body)
    assert bad.status_code == 422
    assert "SECRET_INPUT_VALUE" not in bad.text
    assert client.get("/api/jobs?limit=999").status_code == 422


def test_duplicate_requests_and_conflict(client, case):
    body = submission(case)
    first = client.post("/api/jobs", json=body).json()
    assert client.post("/api/jobs", json=body).json()["id"] == first["id"]
    body["case"]["name"] = "different"
    assert client.post("/api/jobs", json=body).status_code == 409
    assert client.get("/api/jobs").json()["total"] == 1


def test_public_fixture_and_unknown_job(client):
    case = client.get("/api/examples/public-snapshot-case").json()
    job = client.post("/api/jobs", json={"case": case, "request_key": str(uuid.uuid4())}).json()
    result = finished(client, job["id"])["result"]
    assert len(result["collection"]["findings"]) == 3
    assert client.get("/api/jobs/not-real").status_code == 404
    assert client.get("/api/examples/private").status_code == 422


def test_llm_requires_explicit_consent(client, case):
    assert (
        client.post("/api/jobs", json=submission(case, config={"mode": "llm"})).status_code == 409
    )


def test_corrupt_artifact_refuses_read_download_review(client, case):
    job_id = client.post("/api/jobs", json=submission(case)).json()["id"]
    finished(client, job_id)
    root = client.app.state.jobs.artifacts(job_id)
    (root / "report.html").write_text("tampered", encoding="utf-8")
    assert client.get(f"/api/jobs/{job_id}").status_code == 422
    assert client.get(f"/api/jobs/{job_id}/download/bundle").status_code == 422
    assert (
        client.post(
            f"/api/jobs/{job_id}/review",
            json={"decision": "approve", "reviewer": "Test", "reason": "test"},
        ).status_code
        == 422
    )


def test_directory_ownership(tmp_path):
    first = JobService(tmp_path)
    second = JobService(tmp_path)
    first.start()
    try:
        with pytest.raises(Conflict, match="data_directory_in_use"):
            second.start()
    finally:
        first.close()
    second.start()
    second.close()


def test_restart_recovers_published_result_and_interrupts_partial(tmp_path, case):
    service = JobService(tmp_path)
    one = service.submit(case, RunConfig(), "request_one")
    two = service.submit(case, RunConfig(), "request_two")
    service.set_state(one["id"], "running")
    service.set_state(two["id"], "running")
    save_run(case, run_case(case), service.artifacts(one["id"]))
    service.start()
    try:
        assert service.get(one["id"])["state"] == "awaiting_human"
        assert service.get(two["id"])["state"] == "interrupted"
    finally:
        service.close()


def test_cancel_queued_and_retry_new_id(tmp_path, case):
    service = JobService(tmp_path)
    old = service.submit(case, RunConfig(), "request_original")
    service.cancel(old["id"])
    assert service.get(old["id"])["state"] == "cancelled"
    new = service.retry(old["id"], "request_retry")
    assert new["id"] != old["id"]
    assert new["parent_id"] == old["id"]
    assert service.retry(old["id"], "request_retry")["id"] == new["id"]


def test_concurrent_duplicate_submission(tmp_path, case):
    service = JobService(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = list(
            pool.map(lambda _: service.submit(case, RunConfig(), "same_request"), range(20))
        )
    assert len({j["id"] for j in jobs}) == 1


def test_queue_limit(tmp_path, case):
    service = JobService(tmp_path)
    for i in range(20):
        service.submit(case, RunConfig(), f"request_{i}")
    with pytest.raises(Conflict, match="queue_full"):
        service.submit(case, RunConfig(), "one_too_many")


def test_cancel_checkpoint_does_not_call_provider(case):
    with pytest.raises(RunCancelled):
        run_case(case, cancelled=lambda: True)


def test_cancel_running_provider_after_inflight_reply(tmp_path, case):
    from biosbom_agentkg.multiagent.evaluation import FaultProvider

    entered, release = threading.Event(), threading.Event()

    class SlowProvider(FaultProvider):
        def complete(self, *args, **kwargs):
            entered.set()
            release.wait(3)
            return super().complete(*args, **kwargs)

    service = JobService(tmp_path, provider_factory=lambda: SlowProvider("none", False, 0))
    service.start()
    try:
        job = service.submit(case, RunConfig(mode="llm"), "slow_request")
        assert entered.wait(2)
        service.cancel(job["id"])
        assert service.get(job["id"])["state"] == "running"
        release.set()
        deadline = time.monotonic() + 4
        while service.get(job["id"])["state"] == "running" and time.monotonic() < deadline:
            time.sleep(0.02)
        assert service.get(job["id"])["state"] == "cancelled"
        assert not service.artifacts(job["id"]).exists()
    finally:
        release.set()
        service.close()
