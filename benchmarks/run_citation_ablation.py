"""Opt-in 0.4 citation-contract ablation; preserves all attempts and blocked results."""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from biosbom_agentkg.multiagent.engine import run_case
from biosbom_agentkg.multiagent.evidence import digest
from biosbom_agentkg.multiagent.models import Case, RunConfig
from biosbom_agentkg.multiagent.provider import ChatProvider, ProviderError
from biosbom_agentkg.multiagent.storage import save_run, write_json


def transmitted_payload(payload, contract):
    if contract not in {"v04_original", "explicit_citations", "v041_original", "explicit_triage"}:
        raise ValueError("Unknown citation contract")
    result = dict(payload)
    # Keep archived citation experiments on their original 0.4/0.4.1 contracts.
    if contract != "explicit_triage":
        result.pop("triage_contract", None)
    if contract == "v04_original":
        result.pop("context_citations", None)
    return result


def evaluate(cases, output, provider, *, max_total_calls, seed=1741, comparison="citation"):
    if comparison not in {"citation", "triage"}:
        raise ValueError("Unknown comparison")
    contracts = ("v04_original", "explicit_citations") if comparison == "citation" else (
        "v041_original", "explicit_triage"
    )
    required = len(cases) * 4 * 6
    if not cases or required > max_total_calls:
        raise ValueError("Experiment exceeds explicit worst-case call authorization")
    if len(set(provider.models.values())) != 1:
        raise ValueError("Comparison requires the same model for every role")
    schedule = [(i, a, c) for i in range(len(cases))
                for a in ("single_agent", "multi_agent")
                for c in contracts]
    random.Random(seed).shuffle(schedule)
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "protocol.json", {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "models": provider.models, "api_style": getattr(provider, "api_style", "test-adapter"),
        "case_hashes": [digest(c) for c in cases], "schedule": schedule,
        "shuffle_seed": seed, "repeats": 1, "worst_case_calls": required,
        "max_total_calls": max_total_calls, "tokens_per_call": 2000,
        "max_calls_per_run": 6, "max_revisions_per_stage": 2,
        "comparison": comparison,
        "difference": (
            "Only context_citations differs; triage_contract excluded; verifier unchanged"
            if comparison == "citation" else
            "Only triage_contract is removed for v041_original; verifier unchanged"
        ),
        "measurement": "Contract acceptance and resource use, not independent accuracy",
    })
    rows, traces = [], []

    class Adapter:
        models = provider.models

        def __init__(self, index, contract):
            self.index, self.contract = index, contract

        def complete(self, role, payload, schema, **kwargs):
            actual = transmitted_payload(payload, self.contract)
            trace = {"run": self.index, "contract": self.contract, "role": role,
                     "request_sha256": digest([role, actual, schema, kwargs])}
            try:
                reply = provider.complete(role, actual, schema, **kwargs)
                trace.update(output=reply.payload, total_tokens=reply.total_tokens)
                return reply
            except ProviderError as exc:
                trace.update(error=str(exc), total_tokens=exc.total_tokens)
                raise
            finally:
                traces.append(trace)
                write_json(output / "calls.json", traces)

    for index, (case_index, architecture, contract) in enumerate(schedule):
        case = cases[case_index]
        config = RunConfig(mode="llm", architecture=architecture, max_calls=6,
                           max_completion_tokens=12000, tokens_per_call=2000, max_revisions=2)
        result = run_case(case, config, Adapter(index, contract))
        save_run(case, result, output / f"run-{index:04d}")
        proposals = [e for e in result.events if e.role == "verifier"]
        first_stage = proposals[0] if proposals else None
        rows.append({
            "run": index, "case_index": case_index, "case": case.name,
            "architecture": architecture, "contract": contract,
            "verified": result.audit.passed, "status": result.status,
            "first_stage_passed": bool(first_stage and first_stage.outcome == "passed"),
            "no_repair_completion": result.audit.passed and not any(
                e.outcome in {"retry_requested", "revision_requested"} for e in result.events),
            "context_evidence_events": sum("context_evidence" in e.issue_codes for e in proposals),
            "review_required_events": sum("review_required" in e.issue_codes for e in proposals),
            "calls": result.calls, "reported_tokens": result.reported_total_tokens,
            "usage_complete": result.usage_complete, "seconds": result.duration_seconds,
        })
        write_json(output / "results.json", rows)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-total-calls", type=int, required=True)
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--comparison", choices=["citation", "triage"], default="citation")
    args = parser.parse_args()
    if not args.confirm_live:
        parser.error("--confirm-live is required: model calls may transmit data and incur charges")
    cases = [Case.model_validate(c) for c in json.loads(args.cases.read_text(encoding="utf-8"))]
    evaluate(cases, args.output, ChatProvider.from_env(), max_total_calls=args.max_total_calls,
             comparison=args.comparison)
