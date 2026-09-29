from __future__ import annotations

from time import perf_counter

from pydantic import ValidationError

from .agents import ContextAgent, TriageAgent, VerificationAgent, specialist_payload
from .evidence import CollectorAgent, digest
from .models import (
    Audit,
    Case,
    ContextPacket,
    DecisionPacket,
    Event,
    Issue,
    JointPacket,
    RunConfig,
    RunResult,
)
from .provider import Provider, ProviderError


def run_case(case: Case, config: RunConfig | None = None, provider: Provider | None = None):
    config = config or RunConfig()
    if config.mode == "llm" and provider is None:
        raise ValueError("LLM mode requires an explicit provider; there is no silent fallback")
    start = perf_counter()
    collection = CollectorAgent().run(case)
    events = []
    calls = reserved = total = 0
    usage_complete = True

    def event(role, attempt, outcome, source, output=None, codes=None):
        events.append(
            Event(
                sequence=len(events) + 1,
                role=role,
                attempt=attempt,
                outcome=outcome,
                input_sha256=digest(source),
                output_sha256=digest(output) if output is not None else None,
                issue_codes=codes or [],
            )
        )

    event("collector", 0, "completed", case, collection)
    verifier = VerificationAgent()
    context = decisions = None
    audit = Audit(passed=False, issues=[])
    stages = (
        [("single", JointPacket)]
        if config.architecture == "single_agent"
        else [("context", ContextPacket), ("triage", DecisionPacket)]
    )
    for role, schema in stages:
        feedback = []
        succeeded = False
        for attempt in range(config.max_revisions + 1):
            payload = specialist_payload(role, case, collection, context, feedback)
            if config.mode == "deterministic":
                if role == "single":
                    context_candidate = ContextAgent().run(case, collection)
                    candidate = JointPacket(
                        context=context_candidate,
                        triage=TriageAgent().run(case, collection, context_candidate),
                    )
                else:
                    candidate = (
                        ContextAgent().run(case, collection)
                        if role == "context"
                        else TriageAgent().run(case, collection, context)
                    )
            else:
                if (
                    calls >= config.max_calls
                    or reserved + config.tokens_per_call > config.max_completion_tokens
                ):
                    audit = Audit(
                        passed=False,
                        issues=[
                            Issue(
                                code="budget_exhausted",
                                target=role,
                                message="Call or completion-token reservation budget exhausted",
                            )
                        ],
                    )
                    event(role, attempt, "blocked", payload, codes=["budget_exhausted"])
                    break
                calls += 1
                reserved += config.tokens_per_call
                try:
                    reply = provider.complete(
                        role,
                        payload,
                        schema.model_json_schema(),
                        max_tokens=config.tokens_per_call,
                        timeout=config.timeout_seconds,
                    )
                    if reply.total_tokens is None:
                        usage_complete = False
                    else:
                        total += reply.total_tokens
                    candidate = schema.model_validate(reply.payload)
                except (ProviderError, ValidationError) as exc:
                    code = str(exc) if isinstance(exc, ProviderError) else "schema_invalid"
                    # ProviderError codes originate from the transport; never log response bodies.
                    code = (
                        code
                        if code
                        in {
                            "redirect_refused",
                            "request_too_large",
                            "response_too_large",
                            "incomplete_response",
                            "invalid_response",
                            "invalid_usage",
                            "connection_failed",
                            "schema_invalid",
                        }
                        or (code.startswith("http_") and code[5:].isdigit())
                        else "provider_error"
                    )
                    audit = Audit(
                        passed=False,
                        issues=[
                            Issue(
                                code=code,
                                target=role,
                                message="Specialist output unavailable or invalid",
                            )
                        ],
                    )
                    feedback = audit.issues
                    event(role, attempt, "failed", payload, codes=[code])
                    if attempt < config.max_revisions:
                        event("orchestrator", attempt, "retry_requested", audit)
                    continue
            event(role, attempt, "proposed", payload, candidate)
            if role == "single":
                audit = verifier.run(case, collection, candidate.context, candidate.triage)
            else:
                audit = (
                    verifier.check_context(case, collection, candidate)
                    if role == "context"
                    else verifier.run(case, collection, context, candidate)
                )
            event(
                "verifier",
                attempt,
                "passed" if audit.passed else "revision_required",
                candidate,
                audit,
                [i.code for i in audit.issues],
            )
            if audit.passed:
                if role == "single":
                    context, decisions = candidate.context, candidate.triage
                elif role == "context":
                    context = candidate
                else:
                    decisions = candidate
                succeeded = True
                break
            feedback = audit.issues
            if attempt < config.max_revisions:
                event("orchestrator", attempt, "revision_requested", audit)
        if not succeeded:
            break
    accepted = decisions is not None and audit.passed
    if accepted:
        event("reporter", 0, "ready", decisions)
        event("human_gate", 0, "awaiting_human", decisions)
    else:
        event("orchestrator", 0, "blocked", audit)
    return RunResult(
        case_name=case.name,
        input_sha256=digest(case),
        synthetic=case.synthetic,
        mode=config.mode,
        status="awaiting_human" if accepted else "blocked",
        collection=collection,
        context_packet=context,
        decisions=decisions,
        audit=audit,
        events=events,
        config=config,
        calls=calls,
        completion_tokens_reserved=reserved,
        reported_total_tokens=total,
        usage_complete=usage_complete,
        duration_seconds=round(perf_counter() - start, 6),
        models=dict(provider.models) if config.mode == "llm" else {},
    )
