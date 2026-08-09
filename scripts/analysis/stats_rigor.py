#!/usr/bin/env python3
"""Statistical rigor pass for the protocol-level experiments (reviewer request:
confidence intervals + significance tests, not just point estimates).

Reads the per-trial CSVs and reports, for the claims that appear in the paper:
  * median latency with a 95% bootstrap CI and IQR (skewed, RTO-tailed data ->
    nonparametric throughout);
  * Mann-Whitney U tests + Cliff's delta effect size for the load-bearing
    comparisons (hybrid ML-KEM vs classical X25519; small KEMs vs McEliece);
  * tail percentiles (p95/p99) with bootstrap CIs for the loss experiment.

Deterministic: fixed RNG seed so the numbers are reproducible run to run.
"""
import csv
import collections
import numpy as np
from scipy import stats

RNG = np.random.default_rng(20260615)
B = 20000  # bootstrap resamples


def load(path, keyfields, value="seconds"):
    d = collections.defaultdict(list)
    with open(path) as fh:
        for r in csv.DictReader(fh):
            d[tuple(r[k] for k in keyfields)].append(float(r[value]))
    return {k: np.asarray(v) for k, v in d.items()}


def boot_ci(x, stat=np.median, ci=95, n=B):
    x = np.asarray(x)
    idx = RNG.integers(0, len(x), size=(n, len(x)))
    samples = stat(x[idx], axis=1)
    lo, hi = np.percentile(samples, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return lo, hi


def boot_ci_diff(a, b, stat=np.median, ci=95, n=B):
    """95% CI on stat(a) - stat(b) by independent resampling."""
    a, b = np.asarray(a), np.asarray(b)
    ia = RNG.integers(0, len(a), size=(n, len(a)))
    ib = RNG.integers(0, len(b), size=(n, len(b)))
    d = stat(a[ia], axis=1) - stat(b[ib], axis=1)
    lo, hi = np.percentile(d, [(100 - ci) / 2, 100 - (100 - ci) / 2])
    return float(np.median(d)), lo, hi


def cliffs_delta(a, b):
    a, b = np.asarray(a), np.asarray(b)
    gt = sum((a[:, None] > b[None, :]).sum(axis=1))
    lt = sum((a[:, None] < b[None, :]).sum(axis=1))
    return (gt - lt) / (len(a) * len(b))


def mwu(a, b):
    if len(set(a)) == 1 and len(set(b)) == 1 and a[0] == b[0]:
        return float("nan"), 1.0
    U, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    return U, p


def ms(x):
    return 1000.0 * x


print("=" * 78)
print("1. TRANSPORT (emulated RTT, no loss) - 2-RTT floor vs McEliece")
print("   per scheme/RTT: n, median ms [95% CI], IQR ms, RTT-multiple")
print("=" * 78)
tr = load("transport_results.csv", ["set", "rtt_ms"])
sets = ["ML-KEM-512", "ntruhps2048677", "HQC-1", "mceliece348864",
        "ML-KEM-768", "ML-KEM-1024", "HQC-3", "HQC-5",
        "ntruhps4096821", "mceliece460896", "mceliece8192128"]
for rtt in ["10", "50", "100"]:
    print(f"\n-- RTT = {rtt} ms (2-RTT floor = {2*int(rtt)} ms) --")
    for s in sets:
        v = tr.get((s, rtt))
        if v is None:
            continue
        med = np.median(v)
        lo, hi = boot_ci(v)
        q1, q3 = np.percentile(v, [25, 75])
        mult = med / (int(rtt) / 1000.0)
        print(f"  {s:18s} n={len(v):3d}  median={ms(med):8.2f} "
              f"[{ms(lo):8.2f}, {ms(hi):8.2f}]  IQR={ms(q3-q1):6.2f}  "
              f"{mult:5.2f}x RTT")

print("\n-- Significance: ephemeral McEliece vs ML-KEM (same category 1, RTT 10) --")
a = tr[("mceliece348864", "10")]
b = tr[("ML-KEM-512", "10")]
U, p = mwu(a, b)
dmed, dlo, dhi = boot_ci_diff(a, b)
print(f"  Mann-Whitney U={U:.1f}, p={p:.2e}; Cliff's delta={cliffs_delta(a,b):+.3f}")
print(f"  median(McEliece-MLKEM) = {ms(dmed):.2f} ms [95% CI {ms(dlo):.2f}, {ms(dhi):.2f}]")

print("\n-- Small KEMs mutually at the floor? pairwise MWU @ RTT 10 --")
floor = ["ML-KEM-512", "ntruhps2048677", "HQC-1"]
for i in range(len(floor)):
    for j in range(i + 1, len(floor)):
        a, b = tr[(floor[i], "10")], tr[(floor[j], "10")]
        U, p = mwu(a, b)
        print(f"  {floor[i]:16s} vs {floor[j]:16s}: "
              f"median {ms(np.median(a)):.2f} vs {ms(np.median(b)):.2f} ms, "
              f"p={p:.3f}, delta={cliffs_delta(a,b):+.3f}")

print("\n" + "=" * 78)
print("2. TLS 1.3 HANDSHAKE - hybrid ML-KEM 'indistinguishable from X25519'")
print("   (coarse 10 ms wall-clock resolution; report medians + MWU honestly)")
print("=" * 78)
tls = load("tls_results.csv", ["group", "rtt_ms"])
for rtt in ["10", "50", "100"]:
    print(f"\n-- RTT = {rtt} ms --")
    base = tls[("x25519", rtt)]
    bmed = np.median(base)
    blo, bhi = boot_ci(base)
    print(f"  {'x25519 (classical)':22s} n={len(base):3d} "
          f"median={ms(bmed):7.2f} [{ms(blo):7.2f}, {ms(bhi):7.2f}]")
    for g in ["X25519MLKEM768", "mlkem768", "hqc256"]:
        v = tls[(g, rtt)]
        med = np.median(v)
        lo, hi = boot_ci(v)
        U, p = mwu(v, base)
        dmed, dlo, dhi = boot_ci_diff(v, base)
        tag = "n.s." if (p != p or p > 0.05) else f"p={p:.3f}"
        print(f"  {g:22s} n={len(v):3d} median={ms(med):7.2f} "
              f"[{ms(lo):7.2f}, {ms(hi):7.2f}]  vs x25519: "
              f"Dmedian={ms(dmed):+6.2f} ms [{ms(dlo):+.2f},{ms(dhi):+.2f}] {tag}")

print("\n" + "=" * 78)
print("3. LOSS (1% pkt loss, RTT 50, 300 trials) - tail with bootstrap CIs")
print("=" * 78)
loss = load("transport_loss_hn.csv", ["set", "rtt_ms"])
for s in ["ML-KEM-512", "ML-KEM-1024", "HQC-1", "ntruhps2048677",
          "mceliece348864", "mceliece8192128"]:
    keys = [k for k in loss if k[0] == s]
    if not keys:
        continue
    v = loss[keys[0]]
    med = np.median(v)
    p95 = np.percentile(v, 95)
    p99 = np.percentile(v, 99)
    lo95, hi95 = boot_ci(v, stat=lambda x, axis: np.percentile(x, 95, axis=axis))
    print(f"  {s:18s} n={len(v):3d} median={ms(med):7.2f}  "
          f"p95={ms(p95):8.2f} [{ms(lo95):8.2f}, {ms(hi95):8.2f}]  "
          f"p99={ms(p99):8.2f} ms")

print("\n" + "=" * 78)
print("4. REAL WAN (cross-continent, GCP) - median + 95% CI")
print("=" * 78)
wan = load("wan_transport_results.csv", ["set"])
for s in ["ML-KEM-512", "ntruhps2048677", "HQC-1", "mceliece348864"]:
    keys = [k for k in wan if k[0] == s]
    if not keys:
        continue
    v = wan[keys[0]]
    med = np.median(v)
    lo, hi = boot_ci(v)
    q1, q3 = np.percentile(v, [25, 75])
    print(f"  {s:18s} n={len(v):3d} median={ms(med):8.2f} "
          f"[{ms(lo):8.2f}, {ms(hi):8.2f}]  IQR={ms(q3-q1):7.2f} ms")
print()
