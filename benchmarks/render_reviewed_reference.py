"""Plot measured external-reference agreement; no human accuracy claim."""
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/experiments"


def main():
    summary = json.loads((OUT / "reviewed-reference-v1/summary.json").read_text())
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "svg.hashsalt": "biosbom-reviewed-reference-v1"})
    fig, axes = plt.subplots(1, 2, figsize=(12, 6), gridspec_kw={"width_ratios": [1.1, 1]})
    fig.patch.set_facecolor("#f7f9fc")
    values = np.array([[summary["tp"], summary["fn"], summary["abstain_affected"]],
                       [summary["fp"], summary["tn"], summary["abstain_outside"]]])
    axes[0].imshow(values, cmap="Blues", vmin=0, vmax=max(1, values.max()))
    axes[0].set_xticks(range(3), ["Affected", "Outside this\nadvisory", "Abstain"])
    axes[0].set_yticks(range(2), ["Affected", "Outside this\nadvisory"])
    axes[0].set_xlabel("BioSBOM prediction")
    axes[0].set_ylabel("GitHub reviewed-query reference")
    axes[0].set_title("40 version-boundary cases", pad=16, fontweight="bold")
    for (y, x), value in np.ndenumerate(values):
        axes[0].text(x, y, str(value), ha="center", va="center", fontsize=24,
                     color="white" if value > 10 else "#24415e", fontweight="bold")
    packages = list(summary["by_package"])
    records = [summary["by_package"][p] for p in packages]
    axes[1].barh(packages, [r["tp"] + r["tn"] for r in records], color="#187f88", height=.65)
    axes[1].invert_yaxis()
    axes[1].set_xlim(0, 4.8)
    axes[1].set_xticks(range(5))
    axes[1].set_xlabel("Cases agreeing with external reference")
    axes[1].set_title("10 packages; 4 versions each", pad=16, fontweight="bold")
    for i, row in enumerate(records):
        axes[1].text(row["tp"] + row["tn"] + .08, i, f'{row["tp"] + row["tn"]}/{row["n"]}', va="center")
    for spine in axes[1].spines.values():
        spine.set_visible(False)
    fig.suptitle("BioSBOM 0.4.2 | External reviewed-reference agreement", fontsize=17,
                 fontweight="bold", y=.98)
    fig.text(.5, .10, "40/40 agreement | 0 false positives | 0 false negatives | 0 abstentions",
             ha="center", fontsize=12, fontweight="bold")
    fig.text(.5, .045, "0 new human reviewers • 0 model calls • GitHub / OSV share advisory curation\n"
             "Selected historical boundaries; not independent expert validation or deployment accuracy.",
             ha="center", fontsize=10, color="#465569")
    fig.subplots_adjust(left=.12, right=.96, bottom=.24, top=.86, wspace=.6)
    fig.savefig(OUT / "reviewed-reference-v1.png", dpi=180, facecolor=fig.get_facecolor())
    svg = OUT / "reviewed-reference-v1.svg"
    fig.savefig(svg, facecolor=fig.get_facecolor(), metadata={"Date": None})
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n",
                   encoding="utf-8", newline="\n")
    plt.close(fig)


if __name__ == "__main__":
    main()
