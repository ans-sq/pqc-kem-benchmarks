#!/usr/bin/env python3
"""Generate the two comparison figures for the PQC KEM survey.

All sizes in bytes, taken from: FIPS 203 (ML-KEM); NTRU round-3
submission (Oct 2020); Classic McEliece round-4 submission (Oct 2022);
HQC specification of 22 Aug 2025.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "font.family": "serif",
    "font.size": 8,
    "axes.labelsize": 8,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "figure.dpi": 150,
})

# family -> list of (label, pk, ct)
DATA = {
    "ML-KEM (FIPS 203)": [
        ("ML-KEM-512", 800, 768),
        ("ML-KEM-768", 1184, 1088),
        ("ML-KEM-1024", 1568, 1568),
    ],
    "NTRU (round 3)": [
        ("ntruhps2048677", 930, 930),
        ("ntruhrss701", 1138, 1138),
        ("ntruhps4096821", 1230, 1230),
    ],
    "HQC (2025 spec)": [
        ("HQC-1", 2241, 4433),
        ("HQC-3", 4514, 8978),
        ("HQC-5", 7237, 14421),
    ],
    "Classic McEliece (round 4)": [
        ("348864", 261120, 96),
        ("460896", 524160, 156),
        ("8192128", 1357824, 208),
    ],
}

MARKERS = {"ML-KEM (FIPS 203)": "o", "NTRU (round 3)": "s",
           "HQC (2025 spec)": "^", "Classic McEliece (round 4)": "D"}
COLORS = {"ML-KEM (FIPS 203)": "#1b6ca8", "NTRU (round 3)": "#2e8b57",
          "HQC (2025 spec)": "#b3541e", "Classic McEliece (round 4)": "#6a3d9a"}

# ---- Figure 1: pk vs ct, log-log scatter ----------------------------------
fig, ax = plt.subplots(figsize=(3.45, 2.7))
for fam, rows in DATA.items():
    pks = [r[1] for r in rows]
    cts = [r[2] for r in rows]
    ax.scatter(pks, cts, marker=MARKERS[fam], color=COLORS[fam],
               s=28, label=fam, zorder=3)
# annotate one representative point per family
ann = [("ML-KEM-512", 800, 768, (4, -10)),
       ("ntruhps2048677", 930, 930, (-8, 7)),
       ("HQC-1", 2241, 4433, (5, -3)),
       ("mceliece348864", 261120, 96, (-66, 7))]
for label, x, y, off in ann:
    ax.annotate(label, (x, y), textcoords="offset points", xytext=off,
                fontsize=6, color="#333333")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("Public-key size (bytes)")
ax.set_ylabel("Ciphertext size (bytes)")
ax.grid(True, which="both", linewidth=0.3, alpha=0.4)
ax.legend(loc="upper right", framealpha=0.9, handletextpad=0.2,
          borderpad=0.3)
fig.tight_layout()
fig.savefig("fig_pk_vs_ct.pdf")
plt.close(fig)

# ---- Figure 2: per-handshake transfer (pk+ct) by category, log bars -------
cats = ["Category 1", "Category 3", "Category 5"]
series = {
    "ML-KEM (FIPS 203)": [800 + 768, 1184 + 1088, 1568 + 1568],
    "NTRU (round 3)": [930 + 930, 1230 + 1230, None],
    "HQC (2025 spec)": [2241 + 4433, 4514 + 8978, 7237 + 14421],
    "Classic McEliece (round 4)": [261120 + 96, 524160 + 156,
                                   1357824 + 208],
}
fig, ax = plt.subplots(figsize=(3.45, 2.5))
width = 0.2
x = np.arange(len(cats))
for i, (fam, vals) in enumerate(series.items()):
    xs = [x[j] + (i - 1.5) * width for j in range(len(cats))
          if vals[j] is not None]
    ys = [v for v in vals if v is not None]
    bars = ax.bar(xs, ys, width=width * 0.92, color=COLORS[fam],
                  label=fam, zorder=3)
    for b, v in zip(bars, ys):
        txt = f"{v/1000:.1f}k" if v < 100000 else f"{v/1e6:.2f}M"
        ax.annotate(txt, (b.get_x() + b.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 1.5),
                    ha="center", fontsize=5.5, color="#333333")
ax.set_yscale("log")
ax.set_ylim(1e3, 6e6)
ax.set_xticks(x)
ax.set_xticklabels(cats)
ax.set_ylabel("Public key + ciphertext (bytes)")
ax.grid(True, axis="y", which="both", linewidth=0.3, alpha=0.4)
ax.legend(loc="upper left", framealpha=0.9, handletextpad=0.2,
          borderpad=0.3, ncol=1)
fig.tight_layout()
fig.savefig("fig_handshake_cost.pdf")
plt.close(fig)

print("wrote fig_pk_vs_ct.pdf and fig_handshake_cost.pdf")
