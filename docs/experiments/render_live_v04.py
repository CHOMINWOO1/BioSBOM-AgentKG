"""Recorded live-provider contract evaluation, not a model accuracy benchmark."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
rows = json.loads((ROOT / "live-v04/results.json").read_text())
groups = [[r for r in rows if r["architecture"] == a] for a in ["single_agent", "multi_agent"]]
labels = ["Single + repair", "Multi + repair"]
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
fig, ax = plt.subplots(1, 3, figsize=(14, 5.1))
fig.suptitle("BioSBOM | Live gpt-5.6-luna paired execution study", fontsize=17, weight="bold", y=.98)
passed = [sum(r["verified"] for r in g) for g in groups]
ax[0].bar(labels, passed, color=["#527d99", "#167269"])
ax[0].set(title="A  Final verifier acceptance", ylabel="Accepted runs / 12", ylim=(0, 13.5))
for i, value in enumerate(passed):
    ax[0].text(i, value+.2, f"{value}/12", ha="center", weight="bold")
for axis, field, title, ylabel in [(ax[1], "calls", "B  Attempted model calls", "Calls per run"), (ax[2], "seconds", "C  Observed latency", "Seconds per run")]:
    values = [[r[field] for r in group] for group in groups]
    axis.boxplot(values, tick_labels=labels, showfliers=False, patch_artist=True, boxprops={"facecolor": "#e0ece8"})
    for i, value in enumerate(values, start=1):
        offset = [(n - (len(value)-1)/2)*.022 for n in range(len(value))]
        axis.scatter([i+j for j in offset], value, color=["#527d99", "#167269"][i-1], s=23, alpha=.75)
    axis.set(title=title, ylabel=ylabel)
fig.text(.025, .06, "Six fixed development cases x two repeats; same requested model alias and per-run budget. All 24 runs retained, including one blocked run.\n48 calls / 72,052 reported tokens. Deterministic baseline: 6/6 accepted, zero model calls. No independent accuracy or multi-agent advantage claim.", fontsize=9.5, color="#465b65")
fig.tight_layout(rect=(0, .16, 1, .91), w_pad=3)
fig.savefig(ROOT / "live-model-v04.png", dpi=170)
fig.savefig(ROOT / "live-model-v04.svg")
svg = ROOT / "live-model-v04.svg"
svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines())+"\n")
