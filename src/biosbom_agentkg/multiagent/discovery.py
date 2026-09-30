"""Bounded OSV acquisition. Sends only package identities/versions, never asset context."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .evidence import CollectorAgent, digest, purl_parts

ENDPOINT = "https://api.osv.dev/v1/query"
ECOSYSTEMS = {"pypi": "PyPI", "npm": "npm"}


class DiscoveryError(ValueError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DiscoveryError("redirect_refused")


def request_osv(payload, timeout):
    request = Request(ENDPOINT, data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", "Accept": "application/json",
                               "User-Agent": "BioSBOM/0.5"}, method="POST")
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise DiscoveryError("response_too_large")
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise DiscoveryError("invalid_response")
        return value
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DiscoveryError("source_unavailable") from exc


def discover(case, *, request=request_osv, max_requests=60, deadline_seconds=45):
    """Return a new snapshot plus explicit coverage; partial queries never mean no findings."""
    empty = case.model_copy(update={"advisories": [], "intelligence": []})
    components = CollectorAgent().run(empty).sbom.components
    if len(components) > 50 or not 1 <= max_requests <= 100 or not 0 < deadline_seconds <= 60:
        raise ValueError("discovery_limit")
    start = time.monotonic()
    records, queries, pages, cache = {}, [], [], {}
    conflicts = set()
    calls = total_bytes = 0
    for component in components:
        row = {"component_ref": component.bom_ref, "status": "unresolved", "advisory_ids": []}
        queries.append(row)
        identity = purl_parts(component.purl)
        if not component.version:
            row["reason"] = "version_missing"
            continue
        if component.ecosystem not in ECOSYSTEMS or (identity and "?" in identity[0]):
            row["reason"] = "unsupported_identity"
            continue
        payload = {"package": {"purl": identity[0]} if identity else
                   {"name": component.name, "ecosystem": ECOSYSTEMS[component.ecosystem]},
                   "version": component.version}
        cache_key = digest(payload)
        if cache_key in cache:
            row.update(cache[cache_key])
            continue
        token, seen, found = None, set(), set()
        while True:
            remaining = deadline_seconds - (time.monotonic() - start)
            if calls >= max_requests or remaining <= 0:
                row["reason"] = "query_budget_exhausted"
                break
            calls += 1
            query = {**payload, **({"page_token": token} if token else {})}
            try:
                answer = request(query, min(8, remaining))
                total_bytes += len(json.dumps(answer).encode())
                if total_bytes > 8_000_000:
                    raise DiscoveryError("snapshot_size_limit")
                if not isinstance(answer, dict) or not isinstance(answer.get("vulns", []), list):
                    raise DiscoveryError("invalid_response")
                if "vulns" not in answer and answer and not answer.get("next_page_token"):
                    raise DiscoveryError("invalid_response")
                next_token = answer.get("next_page_token")
                if next_token is not None and not isinstance(next_token, str):
                    raise DiscoveryError("invalid_pagination")
                rows = answer.get("vulns", [])
                if len(records) + len(rows) > 1000:
                    raise DiscoveryError("advisory_limit")
                # Validate each response before trusting it as a complete negative query.
                candidate = empty.model_copy(update={"advisories": rows})
                CollectorAgent().run(candidate)
                pages.append({"query": query, "source": ENDPOINT,
                              "retrieved_at": datetime.now(timezone.utc).isoformat(),
                              "response_sha256": digest(answer), "response": answer})
                for advisory in rows:
                    identifier = advisory["id"]
                    if identifier in records and digest(records[identifier]) != digest(advisory):
                        conflicts.add(identifier)
                    records[identifier] = advisory
                    found.add(identifier)
                if not next_token:
                    row["status"] = "queried"
                    break
                if next_token in seen:
                    raise DiscoveryError("pagination_cycle")
                seen.add(next_token)
                token = next_token
            except (ValueError, TypeError, AttributeError, KeyError) as exc:
                row["reason"] = str(exc) if isinstance(exc, DiscoveryError) else "invalid_source_record"
                break
        row["advisory_ids"] = sorted(found)
        cache[cache_key] = {k: v for k, v in row.items() if k != "component_ref"}
    for row in queries:
        if conflicts.intersection(row["advisory_ids"]):
            row.update(status="unresolved", reason="conflicting_source_snapshots")
    snapshot = empty.model_copy(update={"advisories": [records[k] for k in sorted(records)]})
    complete = all(row["status"] == "queried" for row in queries)
    analysis_ready = complete and len(components) * max(1, len(records)) <= 20000 and len(
        snapshot.model_dump_json().encode()) <= 1_900_000
    return {"schema_version": "1.0", "status": "complete" if complete else "partial",
            "analysis_ready": analysis_ready,
            "input_sha256": digest(case), "case": snapshot.model_dump(mode="json"),
            "case_sha256": digest(snapshot), "queries": queries, "pages": pages,
            "calls": calls, "queried_components": sum(r["status"] == "queried" for r in queries),
            "total_components": len(queries), "conflicting_advisories": sorted(conflicts),
            "notice": "No matches is not a safety verdict. OSV lookup is not exploitability analysis."}
