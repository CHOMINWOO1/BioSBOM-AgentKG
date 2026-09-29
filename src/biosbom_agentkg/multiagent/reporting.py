from __future__ import annotations

import html

from .models import RunResult


def rows(result: RunResult):
    decisions = {a.finding_id: a for a in result.decisions.assessments} if result.decisions else {}
    priority = {"urgent": 0, "high": 1, "review": 2, "normal": 3, "blocked": 4}
    output = []
    for finding in result.collection.findings:
        decision = decisions.get(finding.finding_id)
        output.append(
            {
                "component": finding.component_name,
                "version": finding.component_version or "unknown",
                "advisory": finding.advisory_id,
                "match": finding.match,
                "status": decision.status if decision else "unverified",
                "priority": decision.priority if decision else "blocked",
                "cvss": finding.cvss,
                "evidence": finding.evidence_ids,
            }
        )
    return sorted(
        output, key=lambda row: (priority[row["priority"]], row["component"], row["advisory"])
    )


def _cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def render_markdown(result: RunResult) -> str:
    lines = [
        f"# BioSBOM analysis: {_cell(result.case_name)}",
        "",
        f"State: **{result.status}** · Mode: `{result.mode}` · Synthetic: `{result.synthetic}`",
        "",
        "`affected` means the installed version is explicitly listed in the input advisory. "
        "It does not establish reachability or exploitation. A report is not permission to remediate.",
        "",
        "Unmatched packages are not certified safe; advisory coverage is limited to the supplied snapshot.",
        "",
        "| Package | Version | Advisory | Match | Status | Priority | CVSS |",
        "|---|---|---|---|---|---|---:|",
    ]
    for row in rows(result):
        lines.append(
            "| "
            + " | ".join(
                _cell(row[key])
                for key in [
                    "component",
                    "version",
                    "advisory",
                    "match",
                    "status",
                    "priority",
                    "cvss",
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Evidence and coverage",
            "",
            f"Components: {len(result.collection.dispositions)}; findings: {len(result.collection.findings)}.",
        ]
    )
    for disposition in result.collection.dispositions:
        lines.append(f"- `{_cell(disposition.component_ref)}`: {disposition.status}")
    lines.extend(["", "## Audit", "", f"Passed: {result.audit.passed}"])
    for issue in result.audit.issues:
        lines.append(f"- {issue.code}: {_cell(issue.message)}")
    for warning in result.collection.warnings:
        lines.append(f"- Input warning: {_cell(warning)}")
    lines.extend(
        [
            "",
            "## Runtime",
            "",
            f"Calls: {result.calls}; reserved completion tokens: "
            f"{result.completion_tokens_reserved}; reported total tokens: {result.reported_total_tokens}; "
            f"usage complete: {result.usage_complete}; elapsed seconds: {result.duration_seconds}.",
            "",
            "Reservation is a completion-token ceiling, not a dollar budget. Reported total tokens "
            "include prompt usage when provided by the backend.",
            "",
            "Full citations, input hashes, the dependency graph, and agent transitions accompany this report.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_html(result: RunResult) -> str:
    def esc(value):
        return html.escape(str(value), quote=True)

    table = "".join(
        "<tr>"
        + "".join(
            f"<td>{esc(row[key])}</td>"
            for key in ["component", "version", "advisory", "match", "priority", "cvss"]
        )
        + "</tr>"
        for row in rows(result)
    )
    timeline = "".join(
        f"<li><strong>{esc(e.role)}</strong><span>{esc(e.outcome)} · attempt {e.attempt}</span></li>"
        for e in result.events
    )
    issues = "".join(f"<li>{esc(i.code)}: {esc(i.message)}</li>" for i in result.audit.issues)
    evidence = "".join(
        f"<tr><td>{esc(e.kind)}</td><td>{esc(e.pointer)}</td><td class='hash'>{esc(e.sha256)}</td></tr>"
        for e in result.collection.evidence
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>BioSBOM · {esc(result.case_name)}</title><style>
:root{{color-scheme:light;--ink:#142d44;--muted:#526578;--line:#d9e3eb}}
*{{box-sizing:border-box}}body{{margin:0;background:#f1f5f8;color:var(--ink);font:16px/1.6 system-ui,sans-serif}}
main{{max-width:1180px;margin:40px auto;padding:0 24px}}header{{border-top:5px solid #087f8c;padding:26px 0}}
.eyebrow{{letter-spacing:.15em;font-size:12px;font-weight:700;color:#087f8c}}h1{{font-size:36px;line-height:1.2;margin:10px 0}}
h2{{font-size:20px;margin:0 0 16px}}p{{color:var(--muted)}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}}
.card,section{{background:white;border:1px solid var(--line);border-radius:12px;padding:22px;margin-bottom:24px}}
.card b{{display:block;font-size:26px}}.card span{{font-size:13px;color:var(--muted)}}.scroll{{overflow:auto}}
table{{width:100%;border-collapse:collapse;font-size:14px;text-align:left}}td,th{{padding:12px;border-bottom:1px solid var(--line)}}
th{{background:#f5f8fa}}.hash{{font:11px monospace;word-break:break-all}}.badge{{display:inline-block;background:#e2f3f1;padding:4px 12px;border-radius:20px}}
ol{{padding-left:24px}}li{{padding:8px}}li span{{margin-left:20px;color:var(--muted)}}footer{{font-size:13px;color:var(--muted)}}
@media(max-width:700px){{.cards{{grid-template-columns:repeat(2,1fr)}}h1{{font-size:27px}}main{{padding:0 12px}}}}
</style></head><body><main><header><div class="eyebrow">BIOSBOM / EVIDENCE REVIEW</div>
<h1>{esc(result.case_name)}</h1><span class="badge">{esc(result.status)}</span>
<p>Mode: {esc(result.mode)} · Synthetic inputs: {esc(result.synthetic)} · No remediation has been executed.</p></header>
<div class="cards"><div class="card"><b>{len(result.collection.dispositions)}</b><span>Components retained</span></div>
<div class="card"><b>{len(result.collection.findings)}</b><span>Advisory candidates</span></div>
<div class="card"><b>{result.calls}</b><span>Model calls</span></div>
<div class="card"><b>{"PASS" if result.audit.passed else "BLOCKED"}</b><span>Evidence verification</span></div></div>
<section><h2>Triage queue</h2><p>Exact affected-version matches do not prove exploitation. Unmatched packages are not certified safe.</p>
<div class="scroll"><table><thead><tr><th>Component</th><th>Version</th><th>Advisory</th><th>Match</th><th>Priority</th><th>CVSS</th></tr></thead><tbody>{table}</tbody></table></div></section>
<section><h2>Audit and human review</h2><ul>{issues or "<li>Structured decisions passed the configured evidence and priority checks.</li>"}</ul>
<p>Review the source snapshots and remaining uncertainty before recording a decision with the review command.</p></section>
<section><h2>Agent transitions</h2><ol>{timeline}</ol></section>
<section><h2>Evidence snapshots</h2><div class="scroll"><table><tr><th>Type</th><th>Input pointer</th><th>SHA-256</th></tr>{evidence}</table></div></section>
<footer>BioSBOM-AgentKG 0.2 · Input fingerprint: {esc(result.input_sha256)}<br>
Calls: {result.calls} · Completion reservation: {result.completion_tokens_reserved} · Reported total tokens: {result.reported_total_tokens}
 · Usage complete: {esc(result.usage_complete)} · Duration: {result.duration_seconds}s</footer></main></body></html>"""
