#!/usr/bin/env python3
"""CPU results of the controlled campaign.

    python3 -I cpu_analysis.py <data_dir>

Prints (1) the primary table: median of the three repetition medians per
operation, with the between-repetition spread; (2) the decomposition of
the HQC gap (liboqs 0.15 -O0 -> 0.15 -O3 -> 0.16/official reference ->
official AVX2) and of the Classic McEliece -O1/-O3 effect; (3) the frequency
check over every timed operation.
"""
import glob
import os
import sys
from collections import defaultdict

import numpy as np


def load(d):
    meds = defaultdict(list)
    khz = []
    for f in sorted(glob.glob(os.path.join(d, "cpu_*_r*.csv"))):
        for line in open(f):
            if line.startswith(("#", "label")):
                continue
            c = line.strip().split(",")
            build = c[0].rsplit("_r", 1)[0]
            meds[(build, c[1], c[2], c[3])].append(float(c[5]))
            khz += [int(c[10]), int(c[11])]
    return meds, np.array(khz)


def m(meds, *k):
    v = meds.get(k)
    return (float(np.median(v)), (max(v) / min(v) - 1) * 100 if v else float("nan")) if v else (float("nan"), float("nan"))


def main(d):
    meds, khz = load(d)
    print(f"frequency over all timed operations: min {khz.min()} max {khz.max()} kHz; "
          f"max deviation from 1.7 GHz {100 * np.max(np.abs(khz - 1.7e6)) / 1.7e6:.2f}%; "
          f"share within 1%: {100 * np.mean(np.abs(khz - 1.7e6) <= 1.7e4):.1f}%")
    reps = {k: len(v) for k, v in meds.items()}
    print(f"repetitions per configuration: {sorted(set(reps.values()))}")

    print("\n== Primary table (liboqs 0.16.0 as released unless noted), median of repetition medians (us) [max between-rep spread %]")
    rows = [("016", "liboqs", s) for s in ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024",
            "NTRU-HPS-2048-677", "NTRU-HRSS-701", "NTRU-HPS-4096-821", "sntrup761",
            "HQC-1", "HQC-3", "HQC-5"]] + \
           [("016", "official-avx2", s) for s in ["HQC-1", "HQC-3", "HQC-5"]] + \
           [("016", "liboqs", s) for s in ["Classic-McEliece-348864", "Classic-McEliece-460896",
                                            "Classic-McEliece-8192128"]] + \
           [("016O3", "liboqs", s) for s in ["Classic-McEliece-348864", "Classic-McEliece-460896",
                                              "Classic-McEliece-8192128"]]
    spreads = []
    for b, i, s in rows:
        vals = [m(meds, b, i, s, op) for op in ("keygen", "encaps", "decaps")]
        spreads += [v[1] for v in vals]
        print(f"  {b:6s} {i:14s} {s:26s} " + "  ".join(f"{v[0]:12.1f} [{v[1]:4.1f}]" for v in vals))
    print(f"  max between-repetition spread in primary table: {np.nanmax(spreads):.1f}%  median {np.nanmedian(spreads):.1f}%")

    print("\n== HQC decomposition (us)")
    names = {1: ("HQC-128", "HQC-1"), 3: ("HQC-192", "HQC-3"), 5: ("HQC-256", "HQC-5")}
    for L, (old, new) in names.items():
        for op in ("keygen", "encaps", "decaps"):
            a = m(meds, "015", "liboqs", old, op)[0]
            b = m(meds, "015O3", "liboqs", old, op)[0]
            c = m(meds, "016", "liboqs", new, op)[0]
            c2 = m(meds, "016", "official-ref", new, op)[0]
            e = m(meds, "016", "official-avx2", new, op)[0]
            print(f"  cat{L} {op:6s} 0.15(-O0) {a:10.1f} | 0.15(-O3) {b:10.1f} | 0.16 ref {c:10.1f} | "
                  f"official ref {c2:10.1f} | AVX2 {e:8.1f} || -O0 x{a / b:5.2f}  spec/code x{b / c:5.2f}  "
                  f"SIMD x{c / e:6.1f}  total x{a / e:6.1f}")

    print("\n== Classic McEliece -O1 (released) vs -O3 (us)")
    for s in ["Classic-McEliece-348864", "Classic-McEliece-460896", "Classic-McEliece-8192128"]:
        for op in ("keygen", "encaps", "decaps"):
            a = m(meds, "016", "liboqs", s, op)[0]
            b = m(meds, "016O3", "liboqs", s, op)[0]
            print(f"  {s:26s} {op:6s} -O1 {a:12.1f}  -O3 {b:12.1f}  x{a / b:5.2f}")

    print("\n== Ratios vs ML-KEM-512 (category 1)")
    mk = {op: m(meds, "016", "liboqs", "ML-KEM-512", op)[0] for op in ("keygen", "encaps", "decaps")}
    for lab, k in [("NTRU-HPS-2048-677", ("016", "liboqs", "NTRU-HPS-2048-677")),
                   ("HQC-1 ref", ("016", "liboqs", "HQC-1")),
                   ("HQC-1 AVX2", ("016", "official-avx2", "HQC-1")),
                   ("McEliece-348864 -O1", ("016", "liboqs", "Classic-McEliece-348864")),
                   ("McEliece-348864 -O3", ("016O3", "liboqs", "Classic-McEliece-348864"))]:
        r = {op: m(meds, *k, op)[0] / mk[op] for op in mk}
        on = (m(meds, *k, "encaps")[0] + m(meds, *k, "decaps")[0]) / (mk["encaps"] + mk["decaps"])
        print(f"  {lab:22s} keygen x{r['keygen']:8.1f} encaps x{r['encaps']:6.1f} decaps x{r['decaps']:6.1f} online x{on:6.1f}")


if __name__ == "__main__":
    main(sys.argv[1])
