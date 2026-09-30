from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import ValidationError

from .multiagent.engine import run_case
from .multiagent.evaluation import evaluate
from .multiagent.models import Case, RunConfig
from .multiagent.provider import ChatProvider
from .multiagent.storage import record_review, save_run, verify_run
from .multiagent.discovery import discover
from .multiagent.remediation import discovery_plan, remediation_plan


def main(argv=None):
    parser = argparse.ArgumentParser(description="BioSBOM evidence-checked multi-agent triage")
    commands = parser.add_subparsers(dest="command", required=True)
    lookup = commands.add_parser("discover", help="Query OSV and save source snapshot plus reviewable plan")
    lookup.add_argument("--case", type=Path, required=True)
    lookup.add_argument("--output", type=Path, required=True)
    lookup.add_argument("--allow-public-lookup", action="store_true", required=True,
                        help="Acknowledge sending package identities and versions to OSV")
    plan = commands.add_parser("plan", help="Generate an offline evidence-derived remediation plan")
    plan.add_argument("--case", type=Path, required=True)
    plan.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="Analyze an offline case and produce a reviewable run")
    run.add_argument("--case", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--mode", choices=["deterministic", "llm"], default="deterministic")
    run.add_argument(
        "--architecture", choices=["multi_agent", "single_agent"], default="multi_agent"
    )
    run.add_argument("--max-revisions", type=int, default=2)
    run.add_argument("--max-calls", type=int, default=8)
    run.add_argument("--completion-budget", type=int, default=16000)
    run.add_argument("--tokens-per-call", type=int, default=2000)
    run.add_argument("--timeout", type=float, default=30)
    check = commands.add_parser(
        "verify", help="Recompute input/evidence and verify saved file hashes"
    )
    check.add_argument("directory", type=Path)
    review = commands.add_parser("review", help="Record one immutable human review decision")
    review.add_argument("directory", type=Path)
    review.add_argument("--decision", choices=["approve", "hold", "reject"], required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--reason", required=True)
    bench = commands.add_parser(
        "evaluate", help="Run scripted fault-injection comparisons (no live model)"
    )
    bench.add_argument("--case", type=Path, required=True)
    bench.add_argument("--output", type=Path, required=True)
    bench.add_argument("--seeds", type=int, default=10)
    serve = commands.add_parser("serve", help="Start the local review workbench")
    serve.add_argument("--port", type=int, default=8876)
    serve.add_argument("--data-dir", type=Path, default=Path("runs/workbench"))
    args = parser.parse_args(argv)
    try:
        if args.command in {"discover", "plan"}:
            if args.output.exists():
                raise FileExistsError("Output already exists")
            case = Case.model_validate_json(args.case.read_text(encoding="utf-8"))
            if args.command == "discover":
                acquisition = discover(case)
                case = Case.model_validate(acquisition["case"])
                args.output.mkdir(parents=True)
                for name, value in {"case.json": acquisition["case"], "acquisition.json": acquisition,
                                    "remediation-plan.json": discovery_plan(acquisition)}.items():
                    (args.output / name).write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
                print(json.dumps({"status": acquisition["status"], "calls": acquisition["calls"],
                                  "queried_components": acquisition["queried_components"],
                                  "total_components": acquisition["total_components"]}))
                return 0 if acquisition["status"] == "complete" else 2
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(remediation_plan(case), handle, indent=2)
            print(json.dumps({"status": "requires_human_review"}))
            return 0
        if args.command == "serve":
            if not 1024 <= args.port <= 65535:
                raise ValueError("Port must be between 1024 and 65535")
            try:
                import uvicorn
                from .web.app import create_app
            except ImportError:
                print('Install the web extra: pip install -e ".[web]"')
                return 1
            uvicorn.run(
                create_app(args.data_dir, port=args.port),
                host="127.0.0.1",
                port=args.port,
                access_log=False,
            )
            return 0
        if args.command in {"run", "evaluate"}:
            case = Case.model_validate_json(args.case.read_text(encoding="utf-8"))
        if args.command == "run":
            if args.output.exists():
                raise FileExistsError("Output directory already exists")
            config = RunConfig(
                mode=args.mode,
                architecture=args.architecture,
                max_revisions=args.max_revisions,
                max_calls=args.max_calls,
                max_completion_tokens=args.completion_budget,
                tokens_per_call=args.tokens_per_call,
                timeout_seconds=args.timeout,
            )
            provider = ChatProvider.from_env() if config.mode == "llm" else None
            result = run_case(case, config, provider)
            save_run(case, result, args.output)
            print(
                json.dumps(
                    {
                        "status": result.status,
                        "calls": result.calls,
                        "report": str(args.output / "report.html"),
                    }
                )
            )
            return 0 if result.status == "awaiting_human" else 2
        if args.command == "verify":
            _, result = verify_run(args.directory)
            print(json.dumps({"verified": True, "status": result.status}))
        elif args.command == "review":
            record_review(args.directory, args.decision, args.reviewer, args.reason)
            print(json.dumps({"decision_recorded": args.decision}))
        else:
            print(json.dumps(evaluate(case, args.output, args.seeds)))
        return 0
    except (ValidationError, ValueError, OSError, KeyError) as exc:
        # Do not echo raw input values, URLs, provider responses or credentials.
        print(
            json.dumps(
                {
                    "error": type(exc).__name__,
                    "message": "Check input schema, required settings, output path and artifact integrity.",
                }
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
