"""Measured development validation; do not label as independent human accuracy."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "docs/experiments"


def main():
    summary = json.loads((ROOT / "complex-v05/summary.json").read_text())
    reference = json.loads((ROOT / "reviewed-reference-v05/summary.json").read_text())
    rows = json.loads((ROOT / "complex-v05/results.json").read_text())
    plt.rcParams.update({"font.size": 11, "svg.hashsalt": "biosbom-v05"})
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    fig.patch.set_facecolor("#f7f9fc")
    groups = summary["groups"]
    totals = [reference["n"], groups["public_composition"]["n"], groups["synthetic_contract"]["n"]]
    passed = [reference["tp"] + reference["tn"], groups["public_composition"]["passed"], groups["synthetic_contract"]["passed"]]
    axes[0].barh(["Reused reference cases", "Composite SBOM contracts", "Synthetic edge contracts"],
                 [p / n * 100 for p, n in zip(passed, totals, strict=True)], color="#187f88")
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, 125)
    axes[0].set_xticks([0, 50, 100])
    axes[0].set_xlabel("Contract agreement (%)")
    for i, (p, n) in enumerate(zip(passed, totals, strict=True)):
        axes[0].text(102, i, f"{p}/{n}", va="center")
    scale = sorted([r for r in rows if r["case"].startswith("public-composition-")
                    and r["case"] != "public-composition-spdx"], key=lambda r: r["components"])
    axes[1].plot([r["components"] for r in scale], [r["seconds"] * 1000 for r in scale],
                 marker="o", color="#3653a8", linewidth=2)
    axes[1].set_xlabel("Components (10 advisory records)")
    axes[1].set_ylabel("Offline run + plan time (ms)")
    axes[1].set_title("Single run per size; offline, no LLM", fontsize=10)
    axes[1].grid(alpha=.2)
    fig.suptitle("BioSBOM 0.5 | Discovery, remediation and complex-input validation", fontsize=16, fontweight="bold")
    fig.text(.5, .055, "Development checks and reused source labels; not independent expert accuracy.\n"
             "Public-source compositions use synthetic deployment contexts. No packages were changed.",
             ha="center", color="#465569", fontsize=10)
    fig.subplots_adjust(left=.22, right=.96, top=.83, bottom=.23, wspace=.5)
    fig.savefig(ROOT / "validation-v05.png", dpi=180, facecolor=fig.get_facecolor())
    svg = ROOT / "validation-v05.svg"
    fig.savefig(svg, facecolor=fig.get_facecolor(), metadata={"Date": None})
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8", newline="\n")
    plt.close(fig)


if __name__ == "__main__":
    main()
