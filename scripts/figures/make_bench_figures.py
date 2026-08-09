#!/usr/bin/env python3
"""Figures 3 and 4 for the report: measured CPU cost and measured
transport round trips. Reads speed_parsed.json and
transport_results.csv produced by the benchmark runs."""
import csv
import json
import statistics as st

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 11,
    "axes.labelsize": 11,
    "legend.fontsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 10,
    "figure.dpi": 200,
})

FAM_COLOR = {"ML-KEM": "#1b6ca8", "NTRU": "#2e8b57",
             "HQC": "#b3541e", "McEliece": "#6a3d9a"}

# ---- Figure 3: measured CPU time per operation (log scale) ----------------
speed = json.load(open("speed_parsed.json"))
ORDER = [
    ("ML-KEM-512", "ML-KEM"), ("ML-KEM-768", "ML-KEM"),
    ("ML-KEM-1024", "ML-KEM"),
    ("NTRU-HPS-2048-677", "NTRU"), ("NTRU-HRSS-701", "NTRU"),
    ("NTRU-HPS-4096-821", "NTRU"),
    ("HQC-128", "HQC"), ("HQC-192", "HQC"), ("HQC-256", "HQC"),
    ("Classic-McEliece-348864", "McEliece"),
    ("Classic-McEliece-460896", "McEliece"),
    ("Classic-McEliece-8192128", "McEliece"),
]
SHORT = {"Classic-McEliece-348864": "McEliece-348864",
         "Classic-McEliece-460896": "McEliece-460896",
         "Classic-McEliece-8192128": "McEliece-8192128",
         "NTRU-HPS-2048-677": "NTRU-HPS-677",
         "NTRU-HPS-4096-821": "NTRU-HPS-821",
         "NTRU-HRSS-701": "NTRU-HRSS-701"}

fig, ax = plt.subplots(figsize=(7.4, 4.8))
x = np.arange(len(ORDER))
w = 0.27
hatches = {"keygen": "", "encaps": "//", "decaps": ".."}
for i, op in enumerate(["keygen", "encaps", "decaps"]):
    ys = [speed[a][op]["us"] for a, _ in ORDER]
    cols = [FAM_COLOR[f] for _, f in ORDER]
    ax.bar(x + (i - 1) * w, ys, width=w * 0.92, color=cols,
           hatch=hatches[op], edgecolor="white", linewidth=0.4, zorder=3)
ax.set_yscale("log")
ax.set_ylim(1, 5e5)
ax.set_xticks(x)
ax.set_xticklabels([SHORT.get(a, a) for a, _ in ORDER],
                   rotation=40, ha="right")
ax.set_ylabel("Mean time per operation (µs, log scale)")
ax.grid(True, axis="y", which="both", linewidth=0.3, alpha=0.4)
import matplotlib.patches as mpatches
op_handles = [mpatches.Patch(facecolor="#888888", hatch=hatches[o],
                             edgecolor="white", label=o)
              for o in ["keygen", "encaps", "decaps"]]
ax.legend(handles=op_handles, loc="upper left", framealpha=0.95, ncol=3)
fig.tight_layout()
fig.savefig("fig3_cpu_cost.png"); fig.savefig("fig3_cpu_cost.pdf")
plt.close(fig)

# ---- Figure 4: measured handshake round trips at 50 ms RTT ----------------
rows = list(csv.DictReader(open("transport_results.csv")))
sets = []
for r in rows:
    k = (r["scheme"], r["set"])
    if k not in sets:
        sets.append(k)

fig, ax = plt.subplots(figsize=(7.4, 4.4))
labels, vals, cols = [], [], []
for fam, name in sets:
    med = st.median(float(r["seconds"]) for r in rows
                    if r["set"] == name and r["rtt_ms"] == "50")
    labels.append(name)
    vals.append(med / 0.050)
    cols.append(FAM_COLOR[fam])
x = np.arange(len(labels))
bars = ax.bar(x, vals, width=0.62, color=cols, zorder=3)
for b, v in zip(bars, vals):
    ax.annotate(f"{v:.1f}", (b.get_x() + b.get_width() / 2, v),
                textcoords="offset points", xytext=(0, 3),
                ha="center", fontsize=9, color="#333333")
ax.axhline(2.0, color="#cc0000", linewidth=1.0, linestyle="--", zorder=2)
ax.set_xticks(x)
ax.set_xticklabels(labels, rotation=40, ha="right")
ax.set_ylabel("Median handshake duration (× RTT)")
ax.set_ylim(0, max(vals) * 1.18)
ax.grid(True, axis="y", linewidth=0.3, alpha=0.4)
from matplotlib.lines import Line2D
fam_handles = [mpatches.Patch(facecolor=c, label=f)
               for f, c in FAM_COLOR.items()]
fam_handles.append(Line2D([0], [0], color="#cc0000", linewidth=1.0,
                          linestyle="--",
                          label="2-RTT floor (connect + exchange)"))
ax.legend(handles=fam_handles, loc="upper left", framealpha=0.95)
fig.tight_layout()
fig.savefig("fig4_round_trips.png"); fig.savefig("fig4_round_trips.pdf")
plt.close(fig)

print("wrote fig3_cpu_cost.png and fig4_round_trips.png")
