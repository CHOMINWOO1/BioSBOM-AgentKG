"""Opt-in paired live-provider evaluation. Never run implicitly from CI or the UI."""

from __future__ import annotations

import argparse
import csv
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from biosbom_agentkg.multiagent.engine import run_case
from biosbom_agentkg.multiagent.evidence import digest
from biosbom_agentkg.multiagent.models import Case, RunConfig
from biosbom_agentkg.multiagent.provider import ChatProvider, ProviderError
from biosbom_agentkg.multiagent.storage import save_run, write_json


def evaluate_live(cases, output, provider, *, repeats=1, max_total_calls=48, seed=42):
    if not 1 <= repeats <= 20 or not cases:
        raise ValueError("Invalid experiment size")
    # Same per-run call/completion reservation budgets for both architectures.
    per_run_calls = 6
    required = len(cases) * repeats * 2 * per_run_calls
    if required > max_total_calls:
        raise ValueError("Experiment exceeds explicit worst-case call authorization")
    if len(set(provider.models.values())) != 1:
        raise ValueError("Paired comparison requires the same model for every role")
    output.mkdir(parents=True, exist_ok=False)
    calls = []

    class AuditedProvider:
        models = provider.models

        def complete(self, role, payload, schema, **kwargs):
            record = {"role": role, "request_sha256": digest([role, payload, schema, kwargs])}
            try:
                reply = provider.complete(role, payload, schema, **kwargs)
                record.update(output=reply.payload, total_tokens=reply.total_tokens)
                return reply
            except ProviderError as error:
                record.update(error=str(error), total_tokens=error.total_tokens)
                raise
            finally:
                calls.append(record)
                write_json(output / "calls.json", calls)

    schedule = [
        (i, r, architecture)
        for i in range(len(cases))
        for r in range(repeats)
        for architecture in ("single_agent", "multi_agent")
    ]
    random.Random(seed).shuffle(schedule)
    write_json(
        output / "protocol.json",
        {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "models": provider.models,
            "api_style": getattr(provider, "api_style", "test-adapter"),
            "tokens_per_call": 2000,
            "max_revisions": 2,
            "case_hashes": [digest(c) for c in cases],
            "repeats": repeats,
            "schedule": schedule,
            "shuffle_seed": seed,
            "max_total_calls": max_total_calls,
            "worst_case_calls": required,
            "measurement": "Verified completion, repairs, reported tokens and elapsed time; not scientific accuracy",
        },
    )
    rows = []
    for index, (case_index, repeat, architecture) in enumerate(schedule):
        config = RunConfig(
            mode="llm",
            architecture=architecture,
            max_calls=per_run_calls,
            max_completion_tokens=12000,
            tokens_per_call=2000,
            max_revisions=2,
        )
        case = cases[case_index]
        result = run_case(case, config, AuditedProvider())
        save_run(case, result, output / f"run-{index:04d}")
        rows.append(
            {
                "run": index,
                "case_index": case_index,
                "repeat": repeat,
                "architecture": architecture,
                "verified": result.audit.passed,
                "status": result.status,
                "calls": result.calls,
                "seconds": result.duration_seconds,
                "reported_tokens": result.reported_total_tokens,
                "usage_complete": result.usage_complete,
                "repairs": sum(
                    e.outcome in {"revision_requested", "retry_requested"} for e in result.events
                ),
            }
        )
        # Incremental publication keeps completed evidence after an interrupted experiment.
        write_json(output / "results.json", rows)
    with (output / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True, help="JSON list of Case objects")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-total-calls", type=int, required=True)
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="Authorize transmission to the configured provider and possible charges",
    )
    args = parser.parse_args()
    if not args.confirm_live:
        parser.error("--confirm-live is required; review the cases and provider settings first")
    cases = [Case.model_validate(c) for c in json.loads(args.cases.read_text(encoding="utf-8"))]
    evaluate_live(
        cases,
        args.output,
        ChatProvider.from_env(),
        repeats=args.repeats,
        max_total_calls=args.max_total_calls,
    )
