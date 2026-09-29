"""Render only recorded measurements. Run from any working directory."""
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).parent
summary = json.loads((ROOT / "public-corpus-v03/summary.json").read_text())
with (ROOT / "public-corpus-v03/latency.csv").open() as handle:
    latency = list(csv.DictReader(handle))
with (ROOT / "fault-injection/summary.csv").open() as handle:
    faults = list(csv.DictReader(handle))
plt.rcParams.update({"font.family":"DejaVu Sans", "font.size":10,
                     "axes.spines.top":False,"axes.spines.right":False,
                     "axes.edgecolor":"#cad9d1", "axes.labelcolor":"#344e45",
                     "text.color":"#183c31", "xtick.color":"#496257","ytick.color":"#496257"})
fig, axes = plt.subplots(2,2,figsize=(13,8),layout="constrained")
fig.set_facecolor("#f4f7f1")
fig.suptitle("BioSBOM 0.3 | Evidence and operational validation",fontsize=20,fontweight="bold")
ax=axes[0,0]
keys=["exact_version","ambiguous","version_missing","no_candidate"]
values=[summary["observed"].get(k,0) for k in keys]
bars=ax.barh(["Enumerated affected","Fixed: unresolved range","Missing version","Wrong ecosystem / withdrawn"],values,
             color=["#197660","#cbab63","#c6d9cd","#88ad9b"])
ax.bar_label(bars,padding=4)
ax.set(xlim=(0,19),xlabel="Cases",title="A  Public-source consistency: 40 / 40 expected outputs")
ax.invert_yaxis()
ax.text(0,-.31,"8 advisories x 5 controlled variants; source-derived labels.\nUnresolved fixed versions are a known limitation, not correct vulnerability alerts.",
        transform=ax.transAxes,fontsize=8,color="#66796d")
ax=axes[0,1]
sizes=[10,100,1000]
groups=[[float(x["milliseconds"]) for x in latency if int(x["components"])==n] for n in sizes]
ax.boxplot(groups,tick_labels=[str(n) for n in sizes],patch_artist=True,
           boxprops={"facecolor":"#c5dfd1"},medianprops={"color":"#126c54"})
ax.set(xlabel="SBOM components (8 advisories)",ylabel="Core execution time (ms)",
       title="B  Measured scaling: 30 repeats per size")
ax.text(0,-.31,"One warm-up per size; shuffled execution order; Windows / Python 3.12.\nExcludes HTTP, SQLite, artifact I/O and LLM. Not an end-to-end SLA.",
        transform=ax.transAxes,fontsize=8,color="#66796d")
ax=axes[1,0]
conditions=["single_pass","single_with_repair","multi_agent"]
repaired=[sum(int(r["repaired"]) for r in faults if r["architecture"]==c and r["persistent"]=="False" and r["fault"]!="none") for c in conditions]
bars=ax.bar(["Single pass","Single + repair","Multi + repair"],repaired,color=["#a0b5a8","#78a38e","#16785d"])
ax.bar_label(bars,padding=4)
ax.set(ylim=(0,105),ylabel="Transient cases recovered / 90",title="C  Scripted fault injection (existing 570-run study)")
ax.text(0,-.26,"Repair-enabled single and multi both recover 90 / 90.\nThis measures control-flow recovery, not real LLM superiority.",transform=ax.transAxes,fontsize=8,color="#66796d")
ax=axes[1,1]
ax.axis("off")
ax.set_title("D  What the evidence does and does not establish",loc="left")
lines=[("MEASURED", "40 source-consistency cases + 90 timing runs"),
       ("EXERCISED", "Browser submit > evidence > graph > human review"),
       ("TESTED", "Queue / restart / cancel / tamper / browser boundaries"),
       ("PREPARED", "Same-model paired live evaluation with call limits"),
       ("PENDING", "Live-model outcomes; expert labels; external deployment")]
for i,(label,body) in enumerate(lines):
    y=.88-i*.18
    ax.text(0,y,label,weight="bold",fontsize=9,color="#16785d" if label!="PENDING" else "#a27627")
    ax.text(0,y-.075,body,fontsize=9)
for ax in axes.flat:
    ax.set_facecolor("#ffffff")
fig.savefig(ROOT / "validation-v03.png",dpi=180,bbox_inches="tight")
fig.savefig(ROOT / "validation-v03.svg",bbox_inches="tight")
svg = ROOT / "validation-v03.svg"
svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8")
