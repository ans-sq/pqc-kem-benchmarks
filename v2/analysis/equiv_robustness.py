#!/usr/bin/env python3
"""Robustness of the TLS/QUIC equivalence decisions.

    python3 -I equiv_robustness.py <data_dir>

1. Dependence within a visit: each cell was measured in visits (rounds) of
   consecutive handshakes. The 90% interval of every median difference is
   recomputed by resampling whole visits instead of single trials, and any
   equivalence decision that changes is listed. The lag-1 autocorrelation of
   consecutive handshakes within a visit is summarized.
2. Margin sensitivity: the largest absolute 90% bound among the ML-KEM
   comparisons (native groups, no Retry) is the smallest margin at which every
   ML-KEM equivalence claim would still hold; the smallest lower bound among
   the optimized-HQC comparisons is the largest margin below which none of
   them would be declared equivalent.
"""
import csv
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats_common import B, SEED, compare  # noqa: E402

FILES = ["tls_main", "tls_resume", "tls_chain", "tls_provider", "quic_main", "quic_chain"]


def load(path):
    cells = defaultdict(lambda: defaultdict(list))
    for r in csv.DictReader(open(path)):
        if r.get("hs_us") in (None, "", "hs_us"):
            continue
        key = (r["cond"], r["impl"], r["group"], r.get("chain", "single"), r.get("mode", "full"))
        cells[key][int(r["round"])].append(float(r["hs_us"]) / 1e3)
    return {k: [v[i] for i in sorted(v)] for k, v in cells.items()}


def block_ci90(xb, yb, rng):
    xb = [np.asarray(b) for b in xb]
    yb = [np.asarray(b) for b in yb]
    d = np.empty(B)
    for i in range(B):
        xs = np.concatenate([xb[j] for j in rng.integers(0, len(xb), len(xb))])
        ys = np.concatenate([yb[j] for j in rng.integers(0, len(yb), len(yb))])
        d[i] = np.median(xs) - np.median(ys)
    return float(np.quantile(d, 0.05)), float(np.quantile(d, 0.95))


def lag1(blocks):
    r = []
    for b in blocks:
        b = np.asarray(b)
        if len(b) > 3 and b.std() > 0:
            r.append(np.corrcoef(b[:-1], b[1:])[0, 1])
    return r


def main(d):
    rng = np.random.default_rng(SEED)
    lags, flips, rows = [], [], []
    for f in FILES:
        p = os.path.join(d, f + ".csv")
        if not os.path.exists(p):
            continue
        cells = load(p)
        for key, bl in sorted(cells.items()):
            lags += lag1(bl)
            cond, impl, g, chain, mode = key
            base = cells.get((cond, "016", "x25519", chain, mode))
            if g == "x25519" or not base:
                continue
            c = compare(np.concatenate(bl), np.concatenate(base))
            lo, hi = block_ci90(bl, base, rng)
            eq_b = -1 < lo and hi < 1
            native_mlkem = g.upper().startswith(("MLKEM", "X25519MLKEM"))
            kind = ("mlkem" if native_mlkem and not cond.endswith("retry") else
                    "hqc-opt" if impl == "016-hqcavx2" and not cond.endswith("retry") else "other")
            rows.append((f, key, kind, c, lo, hi, eq_b))
            if eq_b != c["equivalent"]:
                flips.append((f, key))
    print("file,cond,impl,group,chain,mode,kind,ci90_lo_iid,ci90_hi_iid,ci90_lo_visit,ci90_hi_visit,equiv_iid,equiv_visit")
    for f, key, kind, c, lo, hi, eq_b in rows:
        print(",".join([f, *key, kind, f"{c['ci90_lo']:.3f}", f"{c['ci90_hi']:.3f}",
                        f"{lo:.3f}", f"{hi:.3f}", str(int(c["equivalent"])), str(int(eq_b))]))
    print()
    print(f"# comparisons: {len(rows)}; equivalence decisions changed by visit resampling: {len(flips)} {flips}")
    print(f"# lag-1 autocorrelation within visits: median {np.median(lags):+.3f}, "
          f"IQR {np.quantile(lags, .25):+.3f} to {np.quantile(lags, .75):+.3f} ({len(lags)} visits)")
    for lab, sel in (("single certificate", lambda f, k: k[3] == "single"),
                     ("certificate chains", lambda f, k: k[3] != "single")):
        m = [max(abs(r[3]["ci90_lo"]), abs(r[3]["ci90_hi"]), abs(r[4]), abs(r[5]))
             for r in rows if r[2] == "mlkem" and sel(r[0], r[1])]
        h = [min(r[3]["ci90_lo"], r[4]) for r in rows if r[2] == "hqc-opt" and sel(r[0], r[1])]
        if m:
            print(f"# ML-KEM, {lab}: largest |90% bound| (either bootstrap) {max(m):.3f} ms over {len(m)} comparisons")
        if h:
            print(f"# optimized HQC vs x25519, {lab}: smallest lower 90% bound {min(h):.3f} ms over {len(h)} comparisons")


if __name__ == "__main__":
    main(sys.argv[1])
