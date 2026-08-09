#!/usr/bin/env python3
"""Packet-loss summary for reviewer item #11, from the high-n re-run
(transport_loss_hn.csv: 300 trials per scheme at 50 ms RTT, 1% random
loss per direction). The no-loss 50 ms median (from transport_results.csv,
30 trials, low variance) is shown for contrast. Prints a human-readable
table and LaTeX-ready rows; every number in the paper's loss table comes
from here.
"""
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
loss = pd.read_csv(os.path.join(HERE, "transport_loss_hn.csv"))
base = pd.read_csv(os.path.join(HERE, "transport_results.csv"))
base50 = base[base["rtt_ms"] == 50]

ORDER = ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024",
         "ntruhps2048677", "ntruhps4096821",
         "HQC-1", "HQC-3", "HQC-5",
         "mceliece348864", "mceliece460896", "mceliece8192128"]

print(f"{'set':16s}{'cat':>4}{'n':>5}{'noloss':>9}{'med':>8}"
      f"{'p90':>8}{'p95':>8}{'p99':>9}{'max':>9}")
rows = []
for s in ORDER:
    g = loss[loss["set"] == s]["seconds"].to_numpy() * 1e3
    cat = int(loss[loss["set"] == s]["category"].iloc[0])
    nl = float(np.median(base50[base50["set"] == s]["seconds"].to_numpy())) * 1e3
    med, p90, p95, p99, mx = (np.median(g), np.percentile(g, 90),
                              np.percentile(g, 95), np.percentile(g, 99), g.max())
    print(f"{s:16s}{cat:>4}{len(g):>5}{nl:>9.0f}{med:>8.0f}"
          f"{p90:>8.0f}{p95:>8.0f}{p99:>9.0f}{mx:>9.0f}")
    rows.append((s, cat, nl, med, p90, p95, p99))

print("\n% LaTeX rows:  set & cat & noloss-med & loss-med & p90 & p95 & p99  (ms)")
for s, cat, nl, med, p90, p95, p99 in rows:
    print(f"{s} & {cat} & {nl:.0f} & {med:.0f} & {p90:.0f} & {p95:.0f} & {p99:.0f} \\\\")
