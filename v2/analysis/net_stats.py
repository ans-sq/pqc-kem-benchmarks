#!/usr/bin/env python3
"""TLS 1.3 and QUIC handshake summaries with the pre-registered comparisons.

    python3 -I net_stats.py tls  <tls_csv>  [baseline_group]
    python3 -I net_stats.py quic <quic_csv> [baseline_group] [pcap_summary_dir]

For every condition and cell: n, median handshake time with 95% bootstrap CI,
p95/p99, median in RTT multiples, and (TLS) the TCP_INFO byte/segment counts
at handshake completion. Each cell is compared against the classical
baseline (x25519, same certificate chain and mode) with the median
difference, its 90%/95% bootstrap CIs, the equivalence decision at the
+/- 1 ms margin, Mann-Whitney U and Cliff's delta.
"""
import csv
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats_common import EQUIV_MARGIN_MS, compare, median_ci, quantiles  # noqa: E402


def main():
    kind, path = sys.argv[1], sys.argv[2]
    base_g = sys.argv[3] if len(sys.argv) > 3 else "x25519"
    pdir = sys.argv[4] if len(sys.argv) > 4 else None
    # campaigns with several phases append a header per phase: skip repeats
    rows = [r for r in csv.DictReader(open(path)) if r["hs_us"] != "hs_us"]
    pc = {}
    if kind == "quic" and pdir:
        for f in os.listdir(pdir):
            if f.startswith("quicpcap_") and f.endswith(".csv"):
                cond = f[len("quicpcap_"):-4]
                for r in csv.DictReader(open(os.path.join(pdir, f))):
                    pc[(cond, r["client_port"], int(r.get("conn_seq", 0)))] = r
    # the k-th trial on a client port within a condition is that port's k-th
    # connection in the trace (rows are written in execution order)
    use = defaultdict(int)
    for r in rows:
        u = (r["cond"], r.get("client_port"))
        r["_seq"] = use[u]
        use[u] += 1
    key = lambda r: (r["cond"], r["impl"], r["group"], r["chain"], r.get("mode", "full"))
    cells = defaultdict(list)
    for r in rows:
        cells[key(r)].append(r)
    hdr = ["cond", "impl", "group", "chain", "mode", "n", "rtt_ms", "median_ms", "ci_lo", "ci_hi",
           "median_rtts", "p95_ms", "p99_ms"]
    if kind == "tls":
        hdr += ["hs_bytes_sent", "hs_bytes_received", "hs_segs_in", "retx_trials_pct", "reused_pct"]
    else:
        hdr += ["c2s_bytes", "s2c_bytes", "c2s_dgrams", "s2c_dgrams", "client_flight1_bytes",
                "server_bytes_pre_validation", "amp_limited_pct", "cwnd_limited_pct", "server_hs_flights_med"]
    hdr += ["diff_ms", "ci90_lo", "ci90_hi", "ci95_lo", "ci95_hi",
            f"equiv_pm{EQUIV_MARGIN_MS:g}ms", "mwu_p", "cliffs_delta"]
    print(",".join(hdr))
    for k in sorted(cells, key=lambda k: (k[0], k[3], k[4], k[1], k[2])):
        cond, impl, grp, chain, mode = k
        rs = cells[k]
        x = np.array([float(r["hs_us"]) / 1e3 for r in rs])
        rtt = float(rs[0]["rtt_ms"])
        med, lo, hi = median_ci(x)
        q = quantiles(x)
        line = [cond, impl, grp, chain, mode, len(x), rtt, round(med, 3), round(lo, 3), round(hi, 3),
                round(med / rtt, 3) if rtt else "", round(q[2], 2), round(q[3], 2)]
        if kind == "tls":
            line += [int(np.median([int(r["hs_bytes_sent"]) for r in rs])),
                     int(np.median([int(r["hs_bytes_received"]) for r in rs])),
                     int(np.median([int(r["hs_segs_in"]) for r in rs])),
                     round(100 * np.mean([int(r["total_retrans"]) > 0 for r in rs]), 1),
                     round(100 * np.mean([int(r["reused"]) for r in rs]), 1)]
        else:
            p = [pc.get((cond, r["client_port"], r["_seq"])) for r in rs]
            p = [e for e in p if e]
            g = lambda f: int(np.median([int(e[f]) for e in p])) if p else ""
            line += [g("c2s_bytes"), g("s2c_bytes"), g("c2s_dgrams"), g("s2c_dgrams"),
                     g("client_flight1_bytes"), g("server_bytes_before_client_flight2"),
                     round(100 * np.mean([e.get("binding_limit") == "amplification" for e in p]), 1) if p else "",
                     round(100 * np.mean([e.get("binding_limit") == "cwnd" for e in p]), 1) if p else "",
                     g("server_hs_flights")]
        bk = next((b for b in cells if b[0] == cond and b[2] == base_g and b[3] == chain and b[4] == mode), None)
        if bk and bk != k:
            y = np.array([float(r["hs_us"]) / 1e3 for r in cells[bk]])
            c = compare(x, y)
            line += [round(c["diff"], 3), round(c["ci90_lo"], 3), round(c["ci90_hi"], 3),
                     round(c["ci95_lo"], 3), round(c["ci95_hi"], 3), int(c["equivalent"]),
                     f"{c['mwu_p']:.2e}", round(c["cliffs_delta"], 3)]
        else:
            line += [""] * 8
        print(",".join(map(str, line)))


if __name__ == "__main__":
    main()
