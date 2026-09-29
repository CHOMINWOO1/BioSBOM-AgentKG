"""Rebuild the 0.4 figure from recorded, source-derived results; no model calls."""
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent
old = json.loads((ROOT / "public-corpus-v03/case-results.json").read_text())
new = json.loads((ROOT / "public-corpus-v04/case-results.json").read_text())
with (ROOT / "public-corpus-v04/latency.csv").open() as handle:
    latency = list(csv.DictReader(handle))
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
fig, axes = plt.subplots(1, 3, figsize=(15, 5.2))
fig.suptitle("BioSBOM 0.4 | Release-range validation and measured core runtime", fontsize=17, weight="bold", y=.98)
counts = [sum(r["variant"] == "fixed_boundary" and r["observed"] == "ambiguous" for r in rows) for rows in [old, new]]
axes[0].bar(["0.3", "0.4"], counts, color=["#94a9b5", "#167269"])
axes[0].set(title="A  Fixed-version review candidates", ylabel="Candidates / 8 fixed boundaries", ylim=(0, 9))
for i, count in enumerate(counts):
    axes[0].text(i, count+.15, str(count), ha="center", weight="bold")
labels = ["Enumerated", "Range-only", "Unresolved", "Version missing", "No candidate"]
keys = ["exact_version", "range_version", "ambiguous", "version_missing", "no_candidate"]
values = [sum(r["observed"] == key for r in new) for key in keys]
axes[1].barh(labels, values, color=["#167269", "#348d82", "#bc8b4b", "#d6b37f", "#94a9b5"])
axes[1].invert_yaxis()
axes[1].set(title="B  72 controlled cases", xlabel="Observed cases", xlim=(0, 28))
for i, count in enumerate(values):
    axes[1].text(count+.3, i, str(count), va="center")
groups = [[float(r["milliseconds"]) for r in latency if int(r["components"]) == size] for size in [10, 100, 1000]]
axes[2].boxplot(groups, tick_labels=["10", "100", "1,000"], patch_artist=True, boxprops={"facecolor": "#cae4de"})
axes[2].set(title="C  30 repeats per size", xlabel="SBOM components", ylabel="Core runtime (ms; log scale)", yscale="log")
fig.text(.03, .055, "A: same eight fixed boundaries; no general safety verdict. B: source-derived fixture agreement (72/72), not independent accuracy.\nC: Windows / Python 3.12; excludes HTTP, queue, SQLite, artifact writes and LLM calls. No live-model results are represented.", fontsize=10, color="#465b65")
fig.tight_layout(rect=(0, .16, 1, .91), w_pad=3)
fig.savefig(ROOT / "validation-v04.png", dpi=170)
fig.savefig(ROOT / "validation-v04.svg")
svg = ROOT / "validation-v04.svg"
svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines())+"\n")
