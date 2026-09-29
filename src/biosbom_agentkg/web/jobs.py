"""Durable FIFO queue. One process and worker own each data directory."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from ..multiagent.engine import RunCancelled, run_case
from ..multiagent.evidence import digest
from ..multiagent.models import Case, RunConfig
from ..multiagent.provider import ChatProvider
from ..multiagent.storage import record_review, save_run, verify_run


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class DirectoryLease:
    """OS-managed lock; released on crash, unlike stale PID files."""

    def __init__(self, root):
        self.path = root / "worker.lock"
        self.handle = None

    def acquire(self):
        self.handle = self.path.open("a+b")
        try:
            self.handle.seek(0)
            if not self.handle.read(1):
                self.handle.write(b"0")
                self.handle.flush()
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            raise Conflict("data_directory_in_use") from None

    def release(self):
        if self.handle:
            self.handle.close()
            self.handle = None


class JobService:
    def __init__(self, root: Path, provider_factory=ChatProvider.from_env):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "jobs.sqlite3"
        self.provider_factory = provider_factory
        self.lease = DirectoryLease(self.root)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, state TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    request_key TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL,
                    case_json TEXT NOT NULL, config_json TEXT NOT NULL,
                    parent_id TEXT, error_code TEXT, cancel_requested INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL,
                    created_at TEXT NOT NULL, event_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS events_job ON events(job_id, id);
            """)

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def start(self):
        self.lease.acquire()
        try:
            with self.db() as db:
                stale = db.execute("SELECT id FROM jobs WHERE state='running'").fetchall()
            for row in stale:
                # A crash after artifact publication must not trigger another paid call.
                try:
                    _, result = verify_run(self.artifacts(row["id"]))
                    self.set_state(row["id"], result.status)
                except (OSError, ValueError, KeyError, TypeError):
                    self.set_state(row["id"], "interrupted", "server_restarted")
            self.thread = threading.Thread(target=self.work, name="biosbom-worker", daemon=True)
            self.thread.start()
        except Exception:
            self.lease.release()
            raise

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            # Provider timeout is at most 120s. Keep ownership until it actually exits.
            self.thread.join(timeout=125)
            if self.thread.is_alive():
                raise RuntimeError("worker_shutdown_incomplete")
        self.lease.release()

    def artifacts(self, job_id):
        if str(uuid.UUID(job_id)) != job_id:
            raise KeyError("job_not_found")
        return self.root / "artifacts" / job_id

    def get(self, job_id, *, private=False):
        with self.db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError("job_not_found")
        result = dict(row)
        result["mode"] = json.loads(result["config_json"])["mode"]
        if result["state"] in {"awaiting_human", "blocked"}:
            review_path = self.artifacts(job_id) / "human-review.json"
            if review_path.exists() and not review_path.is_symlink():
                review = json.loads(review_path.read_text(encoding="utf-8"))
                result["review_decision"] = review.get("decision")
        if not private:
            for key in ("case_json", "config_json", "request_key", "request_hash"):
                result.pop(key)
        return result

    def list(self, offset=0, limit=50):
        with self.db() as db:
            rows = db.execute(
                "SELECT id FROM jobs ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total = db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        return {"items": [self.get(row["id"]) for row in rows], "total": total}

    def submit(self, case, config, request_key, parent_id=None):
        fingerprint = digest(
            {"case": case.model_dump(), "config": config.model_dump(), "parent_id": parent_id}
        )
        with self.lock, self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT id, request_hash FROM jobs WHERE request_key=?", (request_key,)
            ).fetchone()
            if existing:
                if existing["request_hash"] != fingerprint:
                    raise Conflict("idempotency_key_reused")
                return self.get(existing["id"])
            active = db.execute(
                "SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')"
            ).fetchone()[0]
            if active >= 20:
                raise Conflict("queue_full")
            job_id = str(uuid.uuid4())
            stamp = now()
            db.execute(
                """INSERT INTO jobs
                (id,name,state,created_at,updated_at,request_key,request_hash,
                 case_json,config_json,parent_id) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id,
                    case.name,
                    "queued",
                    stamp,
                    stamp,
                    request_key,
                    fingerprint,
                    case.model_dump_json(),
                    config.model_dump_json(),
                    parent_id,
                ),
            )
        self.wake.set()
        return self.get(job_id)

    def add_event(self, job_id, event):
        with self.db() as db:
            db.execute(
                "INSERT INTO events(job_id,created_at,event_json) VALUES (?,?,?)",
                (job_id, now(), event.model_dump_json()),
            )

    def events(self, job_id, after=0):
        self.get(job_id)
        with self.db() as db:
            rows = db.execute(
                "SELECT * FROM events WHERE job_id=? AND id>? ORDER BY id LIMIT 500",
                (job_id, after),
            ).fetchall()
        return [
            {"id": r["id"], "created_at": r["created_at"], **json.loads(r["event_json"])}
            for r in rows
        ]

    def set_state(self, job_id, state, error=None):
        with self.db() as db:
            db.execute(
                "UPDATE jobs SET state=?,error_code=?,updated_at=? WHERE id=?",
                (state, error, now(), job_id),
            )

    def cancel(self, job_id):
        with self.lock:
            job = self.get(job_id)
            if job["state"] not in {"queued", "running"}:
                raise Conflict("run_already_finished")
            with self.db() as db:
                db.execute(
                    "UPDATE jobs SET cancel_requested=1,updated_at=? WHERE id=?", (now(), job_id)
                )
            if job["state"] == "queued":
                self.set_state(job_id, "cancelled")
        return self.get(job_id)

    def retry(self, job_id, request_key, llm_acknowledged=False):
        job = self.get(job_id, private=True)
        if job["state"] not in {"blocked", "failed", "cancelled", "interrupted"}:
            raise Conflict("run_not_retryable")
        config = RunConfig.model_validate_json(job["config_json"])
        if config.mode == "llm" and not llm_acknowledged:
            raise Conflict("llm_consent_required")
        return self.submit(
            Case.model_validate_json(job["case_json"]), config, request_key, parent_id=job_id
        )

    def review(self, job_id, decision, reviewer, reason):
        with self.lock:
            job = self.get(job_id)
            if job["state"] not in {"awaiting_human", "blocked"}:
                raise Conflict("run_not_reviewable")
            return record_review(self.artifacts(job_id), decision, reviewer, reason)

    def work(self):
        while not self.stop.is_set():
            with self.lock, self.db() as db:
                row = db.execute(
                    "SELECT id FROM jobs WHERE state='queued' ORDER BY created_at,id LIMIT 1"
                ).fetchone()
                if row:
                    db.execute(
                        "UPDATE jobs SET state='running',updated_at=? WHERE id=?",
                        (now(), row["id"]),
                    )
            if not row:
                self.wake.wait(0.25)
                self.wake.clear()
                continue
            self.execute(row["id"])

    def execute(self, job_id):
        try:
            job = self.get(job_id, private=True)
            case = Case.model_validate_json(job["case_json"])
            config = RunConfig.model_validate_json(job["config_json"])
            provider = self.provider_factory() if config.mode == "llm" else None

            def cancelled():
                return self.stop.is_set() or bool(self.get(job_id)["cancel_requested"])

            result = run_case(
                case,
                config,
                provider,
                on_event=lambda event: self.add_event(job_id, event),
                cancelled=cancelled,
            )
            with self.lock:
                if cancelled():
                    raise RunCancelled()
                save_run(case, result, self.artifacts(job_id))
                self.set_state(job_id, result.status)
        except RunCancelled:
            self.set_state(
                job_id,
                "interrupted" if self.stop.is_set() else "cancelled",
                "server_stopped" if self.stop.is_set() else None,
            )
        except Exception:
            # Never persist raw exceptions, provider URLs, source values or credentials.
            self.set_state(job_id, "failed", "execution_failed")
