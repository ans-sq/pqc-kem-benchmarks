#!/usr/bin/env python3
"""Descriptive statistics over the existing benchmark CSVs, and a
cross-check of the figures quoted in the paper text against the raw
data. Read-only; prints a report to stdout.

Covers:
  transport_results.csv       (latency only, RTT in {10,50,100} ms)
  transport_loss_results.csv  (50 ms RTT, 1% random loss per direction)
  tls_results.csv             (full TLS 1.3 handshakes)

This is the data behind reviewer item #2 (add std dev / CI / spread,
not just means) and item #11 (a dedicated packet-loss table). It also
re-derives the numbers quoted in main.tex so we never ship a stale one.
"""
import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    return pd.read_csv(os.path.join(HERE, name))


def median_ci95(x):
    """Nonparametric ~95% CI for the median via the normal approximation
    to the binomial order-statistic method."""
    x = np.sort(np.asarray(x, float))
    n = len(x)
    if n < 2:
        return (x[0], x[0]) if n else (np.nan, np.nan)
    lo_rank = max(int(np.floor((n - 1.96 * np.sqrt(n)) / 2.0)), 0)
    hi_rank = min(int(np.ceil(1 + (n + 1.96 * np.sqrt(n)) / 2.0)) - 1, n - 1)
    return x[lo_rank], x[hi_rank]


def summarize(df, group_cols):
    out = []
    for keys, g in df.groupby(group_cols, sort=False):
        kd = dict(zip(group_cols, keys if isinstance(keys, tuple) else (keys,)))
        s = g["seconds"].to_numpy(float)
        rtt_s = float(g["rtt_ms"].iloc[0]) / 1000.0
        lo, hi = median_ci95(s)
        kd.update(
            n=len(s),
            mean_ms=1e3 * s.mean(),
            sd_ms=1e3 * s.std(ddof=1) if len(s) > 1 else 0.0,
            median_ms=1e3 * np.median(s),
            ci_lo_ms=1e3 * lo,
            ci_hi_ms=1e3 * hi,
            p90_ms=1e3 * np.percentile(s, 90),
            p95_ms=1e3 * np.percentile(s, 95),
            median_rtts=np.median(s) / rtt_s,
        )
        out.append(kd)
    return pd.DataFrame(out)


pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 300)
pd.set_option("display.float_format", lambda v: f"{v:8.2f}")

tr = load("transport_results.csv")
ls = load("transport_loss_results.csv")
tl = load("tls_results.csv")

print("=" * 78, "\nTRANSPORT (latency only)\n", "=" * 78, sep="")
print(summarize(tr, ["scheme", "set", "category", "rtt_ms"]).to_string(index=False))

print("\n" + "=" * 78, "\nTRANSPORT (50 ms, 1% loss per direction)\n", "=" * 78, sep="")
print(summarize(ls, ["scheme", "set", "category", "rtt_ms"]).to_string(index=False))

print("\n" + "=" * 78, "\nTLS 1.3 handshakes\n", "=" * 78, sep="")
print(summarize(tl, ["group", "rtt_ms"]).to_string(index=False))


def med(df, **f):
    m = df
    for k, v in f.items():
        m = m[m[k] == v]
    return float(np.median(m["seconds"])) * 1e3 if len(m) else float("nan")


def p90(df, **f):
    m = df
    for k, v in f.items():
        m = m[m[k] == v]
    return float(np.percentile(m["seconds"], 90)) * 1e3 if len(m) else float("nan")


print("\n" + "=" * 78, "\nCLAIM CHECKS vs main.tex prose\n", "=" * 78, sep="")
print(f"[transport 100ms] ML-KEM-512    median = {med(tr, set='ML-KEM-512', rtt_ms=100):7.0f} ms  (prose 201)")
print(f"[transport 100ms] mceliece348864 median = {med(tr, set='mceliece348864', rtt_ms=100):7.0f} ms  (prose 602)")
print(f"[transport 100ms] mceliece8192128 median = {med(tr, set='mceliece8192128', rtt_ms=100):7.0f} ms  (prose ~1400)")
for s in ["mceliece348864", "mceliece460896", "mceliece8192128"]:
    print(f"[no-loss 50ms] {s:16s} median = {med(tr, set=s, rtt_ms=50)/50.0:5.1f} RTTs  (prose 6 / ~10 / 14-17)")
print(f"[no-loss 50ms] mceliece8192128 median = {med(tr, set='mceliece8192128', rtt_ms=50):7.0f} ms  (prose 856)")
print(f"[loss 50ms]    ML-KEM-512     median = {med(ls, set='ML-KEM-512', rtt_ms=50):7.0f} ms  (prose 101)")
print(f"[loss 50ms]    mceliece8192128 median = {med(ls, set='mceliece8192128', rtt_ms=50):7.0f} ms  (prose 1160)")
print(f"[loss 50ms p90] mce 348864 / 460896 / 8192128 = "
      f"{p90(ls, set='mceliece348864', rtt_ms=50):.0f} / "
      f"{p90(ls, set='mceliece460896', rtt_ms=50):.0f} / "
      f"{p90(ls, set='mceliece8192128', rtt_ms=50):.0f} ms  (prose 550 / 1460 / 3370)")
print(f"[TLS 10ms] x25519 median = {med(tl, group='x25519', rtt_ms=10):.0f} ms (prose 50);  "
      f"hqc128 = {med(tl, group='hqc128', rtt_ms=10):.0f} ms (prose 90)")
