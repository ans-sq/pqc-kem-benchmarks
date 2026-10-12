#!/usr/bin/env python3
"""Figures for the revised manuscript (static PDF, print).

    python3 -I make_figures_v2.py <data_dir> <out_dir>

Palette: the dataviz reference categorical slots 1-4 in fixed order
(ML-KEM blue, NTRU orange, HQC aqua, Classic McEliece yellow), validated
for adjacent CVD separation; two slots sit below 3:1 contrast on white, so
every series is directly labeled.
"""
import csv
import glob
import os
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats_common import compare  # noqa: E402

COL = {"ML-KEM": "#2a78d6", "NTRU": "#eb6834", "HQC": "#1baf7a", "McEliece": "#eda100",
       "classical": "#52514e"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e1"
plt.rcParams.update({"font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                     "axes.spines.right": False, "font.family": "serif",
                     "pdf.fonttype": 42})


def fam(name):
    n = name.lower()
    if "mlkem" in n or "ml-kem" in n:
        return "ML-KEM"
    if "ntru" in n:
        return "NTRU"
    if "hqc" in n:
        return "HQC"
    if "mceliece" in n:
        return "McEliece"
    return "classical"


def cpu_meds(d):
    meds = defaultdict(list)
    for f in glob.glob(os.path.join(d, "cpu_*_r*.csv")):
        for line in open(f):
            if line.startswith(("#", "label")):
                continue
            c = line.strip().split(",")
            meds[(c[0].rsplit("_r", 1)[0], c[1], c[2], c[3])].append(float(c[5]))
    return {k: float(np.median(v)) for k, v in meds.items()}


def fig_decomposition(d, out):
    """HQC-1 and McEliece-348864: time per operation under each build."""
    M = cpu_meds(d)
    ops = ["keygen", "encaps", "decaps"]
    stages = [("liboqs 0.15\nref., -O0", ("015", "liboqs", "HQC-128")),
              ("liboqs 0.15\nref., -O3", ("015O3", "liboqs", "HQC-128")),
              ("liboqs 0.16\nref. (2025 spec)", ("016", "liboqs", "HQC-1")),
              ("official\nAVX2", ("016", "official-avx2", "HQC-1"))]
    mstages = [("liboqs 0.16\nAVX2, -O1", ("016", "liboqs", "Classic-McEliece-348864")),
               ("liboqs 0.16\nAVX2, -O3", ("016O3", "liboqs", "Classic-McEliece-348864"))]
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.5), gridspec_kw={"width_ratios": [4, 2.3]})
    for ax, st, color, title in ((axes[0], stages, COL["HQC"], "HQC-1"),
                                 (axes[1], mstages, COL["McEliece"], "mceliece348864")):
        x = np.arange(len(st))
        w = 0.26
        for j, op in enumerate(ops):
            vals = [M[k + (op,)] for _, k in st]
            ax.bar(x + (j - 1) * w, vals, w - 0.02, color=color, alpha=[0.45, 0.7, 1.0][j],
                   edgecolor="white", linewidth=0.8)
            for xi, v in zip(x + (j - 1) * w, vals):
                ax.text(xi, v * 1.12, f"{v:,.0f}" if v >= 10 else f"{v:.1f}", ha="center",
                        va="bottom", fontsize=5.5, color=INK, rotation=90)
        ax.set_yscale("log")
        ax.set_xticks(x, [s for s, _ in st], fontsize=6.5)
        ax.set_title(title, fontsize=8, color=INK)
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        ax.set_ylim(top=ax.get_ylim()[1] * 6)
    axes[0].set_ylabel(r"time per operation ($\mu$s, log)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=MUTED, alpha=a) for a in (0.45, 0.7, 1.0)]
    axes[1].legend(handles, ops, frameon=False, fontsize=6.5, loc="upper right")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig_cpu_decomposition.pdf"))
    plt.close(fig)


def fig_transport(d, out):
    """(a) median duration in RTT multiples at three RTTs; (b) quantiles under 1% loss."""
    rows = list(csv.DictReader(open(os.path.join(d, "transport_latency.csv"))))
    order = ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024", "ntruhps2048677", "ntruhps4096821",
             "HQC-1", "HQC-3", "HQC-5", "mceliece348864", "mceliece460896", "mceliece8192128"]
    loss_path = os.path.join(d, "transport_loss.csv")
    has_loss = os.path.exists(loss_path)
    fig, axes = plt.subplots(1, 2 if has_loss else 1, figsize=(7.0 if has_loss else 3.4, 2.7),
                             squeeze=False)
    ax = axes[0][0]
    marks = {"rtt10": "o", "rtt50": "s", "rtt100": "^"}
    for ci, cond in enumerate(("rtt10", "rtt50", "rtt100")):
        rtt = {"rtt10": 10, "rtt50": 50, "rtt100": 100}[cond]
        ys = []
        for s_ in order:
            x = [float(r["seconds"]) * 1e3 / rtt for r in rows if r["cond"] == cond and r["set"] == s_]
            ys.append(np.median(x))
        ax.scatter(np.arange(len(order)) + (ci - 1) * 0.22, ys, s=16, marker=marks[cond],
                   c=[COL[fam(s_)] for s_ in order], edgecolors="white", linewidths=0.5,
                   label=f"{rtt} ms RTT", zorder=3)
    ax.axhline(2, color=MUTED, linewidth=0.7, linestyle=(0, (3, 2)))
    ax.text(4.0, 2.25, "2-RTT floor", fontsize=6, color=MUTED, ha="center")
    ax.set_xticks(range(len(order)), order, rotation=60, ha="right", fontsize=6)
    ax.set_ylabel("median duration (RTTs)")
    ax.set_title("(a) no loss", fontsize=8, color=INK, loc="left")
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    leg = ax.legend(frameon=False, fontsize=6, loc="upper left")
    for h in leg.legend_handles:
        h.set_color(MUTED)
    if has_loss:
        ax = axes[0][1]
        lrows = [r for r in csv.DictReader(open(loss_path)) if r["seconds"] != "seconds"]
        qs = [("median", 50, "o"), ("90th pct.", 90, "D"), ("99th pct.", 99, "v")]
        for k, s_ in enumerate(order):
            x = np.array([float(r["seconds"]) * 1e3 for r in lrows if r["set"] == s_])
            v = [np.percentile(x, q) for _, q, _ in qs]
            off = (-0.2, 0.0, 0.2)  # side by side, so a median under a 90th percentile stays visible
            ax.plot([k + o for o in off], v, color=COL[fam(s_)], linewidth=1.0, alpha=0.5, zorder=2)
            for (lab, q, m), y, o in zip(qs, v, off):
                ax.scatter([k + o], [y], s=16, marker=m, color=COL[fam(s_)], edgecolors="white",
                           linewidths=0.5, zorder=3, label=lab if k == 0 else None)
        ax.set_yscale("log")
        ax.set_xticks(range(len(order)), order, rotation=60, ha="right", fontsize=6)
        ax.set_ylabel("duration (ms, log)")
        ax.set_title("(b) 50 ms RTT, 1% loss", fontsize=8, color=INK, loc="left")
        ax.grid(axis="y", color=GRID, linewidth=0.6, which="both")
        ax.set_axisbelow(True)
        leg = ax.legend(frameon=False, fontsize=6, loc="upper left")
        for h in leg.legend_handles:
            h.set_color(MUTED)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig_transport_rtts.pdf"))
    plt.close(fig)


def fig_tls_forest(d, out):
    rows = [r for r in csv.DictReader(open(os.path.join(d, "tls_main.csv"))) if r["hs_us"] != "hs_us"]
    cells = defaultdict(list)
    for r in rows:
        cells[(r["cond"], r["impl"], r["group"])].append(float(r["hs_us"]) / 1e3)
    groups = [("016", "X25519MLKEM768", "X25519MLKEM768"), ("016", "MLKEM512", "ML-KEM-512"),
              ("016", "MLKEM768", "ML-KEM-768"), ("016", "MLKEM1024", "ML-KEM-1024"),
              ("016-hqcavx2", "hqc1", "HQC-1 (AVX2)"), ("016-hqcavx2", "hqc3", "HQC-3 (AVX2)"),
              ("016-hqcavx2", "hqc5", "HQC-5 (AVX2)"), ("016", "hqc1", "HQC-1 (ref.)")]
    conds = [("rtt10", "10 ms"), ("rtt50", "50 ms"), ("rtt100", "100 ms")]
    fig, axes = plt.subplots(1, 3, figsize=(7.0, 2.4), sharey=True)
    for ax, (cond, lab) in zip(axes, conds):
        base = cells[(cond, "016", "x25519")]
        for i, (impl, g, name) in enumerate(groups):
            c = compare(cells[(cond, impl, g)], base)
            color = COL[fam(g)]
            ax.plot([c["ci90_lo"], c["ci90_hi"]], [i, i], color=color, linewidth=2,
                    solid_capstyle="round")
            ax.plot(c["diff"], i, "o", color=color, markersize=4, markeredgecolor="white",
                    markeredgewidth=0.5)
        ax.axvspan(-1, 1, color=GRID, zorder=0)
        ax.axvline(0, color=MUTED, linewidth=0.6)
        ax.set_title(f"RTT {lab}", fontsize=8, color=INK)
        ax.set_xscale("symlog", linthresh=1)
        ax.set_xlim(-2, 400)
        ax.set_xticks([-1, 0, 1, 10, 100], ["\u22121", "0", "1", "10", "100"])
        ax.grid(axis="x", color=GRID, linewidth=0.4)
    axes[0].set_yticks(range(len(groups)), [g[2] for g in groups], fontsize=6.5)
    axes[0].invert_yaxis()
    axes[1].set_xlabel("median handshake time minus x25519 baseline (ms, symmetric log scale); "
                       "shaded band = $\\pm$1 ms equivalence margin", fontsize=6.5)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "fig_tls_equivalence.pdf"))
    plt.close(fig)


if __name__ == "__main__":
    d, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for f in (fig_decomposition, fig_transport, fig_tls_forest):
        try:
            f(d, out)
            print("ok", f.__name__)
        except FileNotFoundError as e:
            print("skip", f.__name__, "(data not yet available:", os.path.basename(e.filename), ")")
