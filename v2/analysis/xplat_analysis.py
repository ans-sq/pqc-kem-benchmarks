#!/usr/bin/env python3
"""Cross-platform replication: the decomposition factors and cross-family
ratios of the CPU campaign on the laptop (Intel, fixed 1.7 GHz) and on the
two cloud VMs (AMD Zen 4, Google Axion), plus the TLS provider-path control.

    python3 -I xplat_analysis.py <data_dir>      (reads data/ and data/xplat/{amd,arm}/data/)

Ratios, not absolute times, are compared across platforms: the VMs run at
an uncontrolled clock, and a ratio between two implementations timed in the
same process, interleaved, cancels most of that.
"""
import csv
import glob
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats_common import compare  # noqa: E402

OPS = ("keygen", "encaps", "decaps")


def load(d):
    meds = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(d, "cpu_*_r*.csv"))):
        for line in open(f):
            if line.startswith(("#", "label")):
                continue
            c = line.strip().split(",")
            meds[(c[0].rsplit("_r", 1)[0], c[1], c[2], c[3])].append(float(c[5]))
    return meds


def med(M, *k):
    v = M.get(k)
    return float(np.median(v)) if v else float("nan")


def spread(M):
    s = [(max(v) / min(v) - 1) * 100 for v in M.values() if len(v) > 1]
    return float(np.median(s)), float(np.max(s))


def rng(vals):
    vals = [v for v in vals if np.isfinite(v)]
    return f"{min(vals):.2f}-{max(vals):.2f}" if vals else "n/a"


def factors(M):
    out = {}
    # HQC reference code: -O0 (liboqs 0.15 as released) over -O3, every op and category
    out["hqc_O0"] = [med(M, "015", "liboqs", s, op) / med(M, "015O3", "liboqs", s, op)
                     for s in ("HQC-128", "HQC-192", "HQC-256") for op in OPS]
    # 2023 spec at -O3 (0.15) to 2025 spec (0.16), liboqs reference code
    out["spec"] = [med(M, "015O3", "liboqs", a, op) / med(M, "016", "liboqs", b, op)
                   for a, b in (("HQC-128", "HQC-1"), ("HQC-192", "HQC-3"), ("HQC-256", "HQC-5"))
                   for op in OPS]
    # SIMD: liboqs 0.16 reference code over the official AVX2 code (x86 only)
    out["simd"] = [med(M, "016", "liboqs", s, op) / med(M, "016", "official-avx2", s, op)
                   for s in ("HQC-1", "HQC-3", "HQC-5") for op in OPS]
    # Classic McEliece decapsulation: liboqs's -O1 AVX2 build over the same code at -O3 (x86 only)
    out["mce_O1"] = [med(M, "016", "liboqs", s, "decaps") / med(M, "016O3", "liboqs", s, "decaps")
                     for s in ("Classic-McEliece-348864", "Classic-McEliece-460896",
                               "Classic-McEliece-8192128")]
    # official reference HQC over liboqs's reference HQC (same 2025 code base)
    out["off_ref"] = [med(M, "016", "official-ref", s, op) / med(M, "016", "liboqs", s, op)
                      for s in ("HQC-1", "HQC-3", "HQC-5") for op in OPS]
    return out


def family_ratios(M):
    """Category 1, best available code on the platform, relative to ML-KEM-512."""
    def online(b, i, s):
        return med(M, b, i, s, "encaps") + med(M, b, i, s, "decaps")
    base_on, base_kg = online("016", "liboqs", "ML-KEM-512"), med(M, "016", "liboqs", "ML-KEM-512", "keygen")
    hqc = ("016", "official-avx2", "HQC-1") if ("016", "official-avx2", "HQC-1", "encaps") in M \
        else ("016", "liboqs", "HQC-1")
    mce = ("016O3", "liboqs", "Classic-McEliece-348864") \
        if ("016O3", "liboqs", "Classic-McEliece-348864", "encaps") in M \
        else ("016", "liboqs", "Classic-McEliece-348864")
    rows = {"NTRU (ntruhps2048677)": ("016", "liboqs", "NTRU-HPS-2048-677"),
            f"HQC-1 ({'AVX2' if hqc[1] == 'official-avx2' else 'ref.'})": hqc,
            "HQC-1 (liboqs ref.)": ("016", "liboqs", "HQC-1"),
            "mceliece348864": mce}
    return base_on, base_kg, {k: (online(*v) / base_on, med(M, *v, "keygen") / base_kg)
                              for k, v in rows.items()}


def provider(path):
    if not os.path.exists(path):
        return None
    c = defaultdict(list)
    for r in csv.DictReader(open(path)):
        if r["hs_us"] == "hs_us":
            continue
        c[(r["cond"], r["impl"], r["group"])].append(float(r["hs_us"]) / 1e3)
    res = {}
    for cond in ("prov_rtt10", "prov_rtt50"):
        x = lambda i, g: c.get((cond, i, g), [])
        pairs = {"native hybrid vs x25519": (("016", "X25519MLKEM768"), ("016", "x25519")),
                 "provider ML-KEM-512 vs x25519": (("016", "x25519_mlkem512"), ("016", "x25519")),
                 "provider HQC-1 AVX2 vs provider ML-KEM-512": (("016-hqcavx2", "x25519_hqc1"), ("016", "x25519_mlkem512")),
                 "provider HQC-1 ref vs provider ML-KEM-512": (("016", "x25519_hqc1"), ("016", "x25519_mlkem512"))}
        for lab, (a, b) in pairs.items():
            if x(*a) and x(*b):
                r = compare(x(*a), x(*b))
                res[(cond, lab)] = (r["diff"], r["ci90_lo"], r["ci90_hi"], r["equivalent"])
    return res


def main(d):
    plats = [("laptop (Intel i7-1355U, 1.7 GHz fixed)", d),
             ("AMD EPYC Zen 4 (GCP C3D)", os.path.join(d, "xplat", "amd", "data")),
             ("Google Axion Neoverse V2 (GCP C4A)", os.path.join(d, "xplat", "arm", "data"))]
    for name, p in plats:
        M = load(p)
        if not M:
            print(f"== {name}: no data")
            continue
        f = factors(M)
        sm, sx = spread(M)
        print(f"== {name}")
        env = os.path.join(p, "env_cpu.txt")
        if os.path.exists(env):
            mn = [l.split(":", 1)[1].strip() for l in open(env) if l.startswith("Model name")]
            print(f"   CPU: {mn[0] if mn else '?'}")
        print(f"   between-repetition spread: median {sm:.1f}%, max {sx:.1f}%")
        print(f"   HQC -O0 factor (0.15 ref, all ops/cats): {rng(f['hqc_O0'])}")
        print(f"   spec factor 2023->2025 (ref -O3):        {rng(f['spec'])}")
        print(f"   SIMD factor (liboqs ref / official AVX2): {rng(f['simd'])}")
        print(f"   McEliece -O1 decaps factor:               {rng(f['mce_O1'])}")
        print(f"   official ref / liboqs ref (0.16):         {rng(f['off_ref'])}")
        bo, bk, fr = family_ratios(M)
        print(f"   ML-KEM-512: encaps+decaps {bo:.1f} us, keygen {bk:.1f} us")
        for k, (on, kg) in fr.items():
            print(f"   {k:24s} online x{on:8.1f}   keygen x{kg:10.1f}")
        pv = provider(os.path.join(p, "tls_provider.csv"))
        if pv:
            for (cond, lab), (df, lo, hi, eq) in sorted(pv.items()):
                print(f"   TLS {cond} {lab:45s} {df:+7.2f} ms [{lo:+.2f}, {hi:+.2f}] equiv={eq}")


def latex(d):
    """Rows of tab:xplat: one column per platform."""
    paths = [d, os.path.join(d, "xplat", "amd", "data"), os.path.join(d, "xplat", "arm", "data")]
    Ms = [load(p) for p in paths]
    Fs = [factors(M) if M else None for M in Ms]
    FR = [family_ratios(M) if M else None for M in Ms]
    PV = [provider(os.path.join(p, "tls_provider.csv")) for p in paths]

    def r2(vals, nd=1):
        vals = [v for v in vals if np.isfinite(v)]
        if not vals:
            return "--"
        lo, hi = min(vals), max(vals)
        return f"{lo:.{nd}f}--{hi:.{nd}f}" if f"{lo:.{nd}f}" != f"{hi:.{nd}f}" else f"{lo:.{nd}f}"

    def row(label, cells):
        print(label + " & " + " & ".join(cells) + " \\\\")
    row("HQC ref.\\ \\texttt{-O0} / \\texttt{-O3} (0.15)", [r2(F["hqc_O0"]) if F else "--" for F in Fs])
    row("HQC 2023 / 2025 spec. (ref., \\texttt{-O3})", [r2(F["spec"], 2) if F else "--" for F in Fs])
    row("HQC ref.\\ / official AVX2", [r2(F["simd"], 0) if F else "--" for F in Fs])
    row("McEliece decaps \\texttt{-O1} / \\texttt{-O3}", [r2(F["mce_O1"]) if F else "--" for F in Fs])
    print("\\addlinespace")
    row("ML-KEM-512 encaps + decaps ($\\mu$s)", [f"{fr[0]:.1f}" if fr else "--" for fr in FR])
    for key, lab in (("NTRU (ntruhps2048677)", "ntruhps2048677"), ("HQC-1 (liboqs ref.)", "HQC-1, liboqs ref.")):
        row(f"{lab}, online / keygen", [f"{fr[2][key][0]:,.1f} / {fr[2][key][1]:,.0f}".replace(",", "{,}") if fr else "--" for fr in FR])
    cells = []
    for fr in FR:
        k = next((k for k in fr[2] if k.startswith("HQC-1 (AVX2")), None) if fr else None
        cells.append(f"{fr[2][k][0]:.1f} / {fr[2][k][1]:.1f}" if k else "--")
    row("HQC-1, official AVX2, online / keygen", cells)
    row("mceliece348864, online / keygen", [f"{fr[2]['mceliece348864'][0]:.1f} / {fr[2]['mceliece348864'][1]:,.0f}".replace(",", "{,}") if fr else "--" for fr in FR])
    print("\\addlinespace")
    def pv(P, lab):
        v = P.get(("prov_rtt50", lab)) if P else None
        return f"${v[0]:+.2f}$ [{v[1]:.2f}, {v[2]:.2f}]" if v else "--"
    row("TLS: provider ML-KEM-512 $-$ native x25519 (ms)", [pv(P, "provider ML-KEM-512 vs x25519") for P in PV])
    row("TLS: HQC-1 AVX2 $-$ ML-KEM-512, both provider (ms)", [pv(P, "provider HQC-1 AVX2 vs provider ML-KEM-512") for P in PV])
    row("TLS: native hybrid $-$ x25519 (ms)", [pv(P, "native hybrid vs x25519") for P in PV])
    print("\\addlinespace")
    row("Between-repetition spread, median (max) \\%", [f"{spread(M)[0]:.1f} ({spread(M)[1]:.0f})" if M else "--" for M in Ms])


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[2] == "--latex":
        latex(sys.argv[1])
    else:
        main(sys.argv[1])
