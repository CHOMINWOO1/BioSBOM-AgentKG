"""Plot fixed ablation data. Re-run the summary validator before rendering."""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
summary = json.loads((root / "triage-v042/summary.json").read_text(encoding="utf-8"))
groups = summary["groups"]
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False})
fig, axes = plt.subplots(1, 3, figsize=(13, 4.8), layout="constrained")
colors = ["#9bafb5", "#167a68", "#9bafb5", "#167a68"]
labels = ["Single\nOriginal", "Single\nExplicit", "Multi\nOriginal", "Multi\nExplicit"]
for ax, metric, title in zip(axes, ["no_repair_completion", "calls", "reported_tokens"],
                            ["Verified without repair (of 12)", "Total model calls", "Reported total tokens"]):
    values = [g[metric] for g in groups]
    bars = ax.bar(range(4), values, color=colors, width=.65)
    ax.set_xticks(range(4), labels)
    ax.set_title(title, fontsize=11, pad=14)
    ax.bar_label(bars, labels=[f"{v:,}" for v in values], padding=4)
    ax.set_ylim(0, max(values) * 1.25 if max(values) else 1)
    ax.grid(axis="y", alpha=.16)
    ax.set_axisbelow(True)
fig.suptitle("BioSBOM | Explicit review-state contract", fontsize=17, fontweight="bold")
fig.supxlabel(f"12 controlled cases x 2 architectures x 2 contracts | {summary['calls']} real calls | "
              "One repeat per cell; development contract test, not independent accuracy", fontsize=9)
for extension in ("png", "svg"):
    fig.savefig(root / f"triage-ablation-v042.{extension}", dpi=180, facecolor="white")
svg = root / "triage-ablation-v042.svg"
svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
print("Citation ablation figure saved from recorded values.")
