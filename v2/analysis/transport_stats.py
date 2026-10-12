#!/usr/bin/env python3
"""Summaries of the size-matched TCP transport emulation (loopback and WAN).

    python3 -I transport_stats.py [--pcap <pcapsum_dir>] <csv> [<csv> ...]

Per condition and parameter set: trials, median latency with 95% bootstrap
CI, the median in RTT multiples, tail quantiles, and per-trial TCP counters
from TCP_INFO (client and server data segments, retransmitted segments).
With --pcap, per-connection trace summaries (pcap_flights.py tcp, files
tcppcap_transport_<cond>.csv) are joined in execution order, each pair
checked against the message sizes, and the median numbers of client and
server data flights (round trips each direction needed) are added.
"""
import csv
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from stats_common import compare, median_ci, quantiles  # noqa: E402

ORDER = ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024", "ntruhps2048677", "ntruhps4096821",
         "HQC-1", "HQC-3", "HQC-5", "mceliece348864", "mceliece460896", "mceliece8192128"]


def join_pcap(rows, pdir):
    """Attach trace summaries to trials. Connections are sequential, so the
    k-th connection of a condition's trace is its k-th trial; a pair is kept
    only if the traced payload covers the message sizes (retransmissions can
    add bytes). Traces may lack the last trials of a condition, cut off when
    the capture stopped."""
    import os
    bycond = defaultdict(list)
    for r in rows:
        bycond[r["cond"]].append(r)
    for cond, rs in bycond.items():
        f = os.path.join(pdir, f"tcppcap_transport_{cond}.csv")
        if not os.path.exists(f):
            continue
        conns = sorted(csv.DictReader(open(f)), key=lambda c: float(c["t_start"]))
        j = 0
        for r in rs:
            if j >= len(conns):
                break
            c = conns[j]
            need_c, need_s = int(r["pk"]) + 4, int(r["ct"]) + 4
            if need_c <= int(c["c2s_bytes"]) <= 2 * need_c + 3000 and \
               need_s <= int(c["s2c_bytes"]) <= 2 * need_s + 3000:
                r["_pcap"] = c
                j += 1


def main(paths):
    pdir = None
    if paths and paths[0] == "--pcap":
        pdir, paths = paths[1], paths[2:]
    rows = []
    for p in paths:
        rows += list(csv.DictReader(open(p)))
    if pdir:
        join_pcap(rows, pdir)
    cells = defaultdict(list)
    for r in rows:
        cells[(r["cond"], r["set"])].append(r)
    conds = sorted({c for c, _ in cells}, key=lambda c: (len(c), c))
    print("cond,set,n,rtt_ms,median_ms,ci_lo,ci_hi,median_rtts,p90_ms,p95_ms,p99_ms,"
          "c_data_segs_out_med,s_data_segs_out_med,retx_segs_mean,retx_trials_pct,"
          "vs_mlkem512_diff_ms,vs_mlkem512_mwu_p,vs_mlkem512_cliff,"
          "pcap_n,c2s_flights_med,s2c_flights_med")
    for c in conds:
        base = [float(r["seconds"]) * 1e3 for r in cells.get((c, "ML-KEM-512"), [])]
        for s in ORDER:
            rs = cells.get((c, s))
            if not rs:
                continue
            x = np.array([float(r["seconds"]) * 1e3 for r in rs])
            rtt = float(rs[0].get("rtt_ms") or rs[0].get("min_rtt_ms") or "nan")
            if "min_rtt_ms" in rs[0]:  # WAN: use the measured path RTT
                rtt = float(np.median([float(r["min_rtt_ms"]) for r in rs]))
            med, lo, hi = median_ci(x)
            q = quantiles(x)
            retx = np.array([int(r["c_total_retrans"]) + int(r.get("s_total_retrans", 0) or 0)
                             for r in rs])
            cso = np.median([int(r["c_data_segs_out"]) for r in rs])
            sso = np.median([int(r["s_data_segs_out"]) for r in rs]) if "s_data_segs_out" in rs[0] else float("nan")
            cmp = compare(x, base) if base and s != "ML-KEM-512" else None
            pk = [r["_pcap"] for r in rs if "_pcap" in r]
            fl = [len(pk), np.median([int(c["c2s_data_flights"]) for c in pk]) if pk else "",
                  np.median([int(c["s2c_data_flights"]) for c in pk]) if pk else ""]
            print(",".join(map(str, [c, s, len(x), round(rtt, 2), round(med, 2), round(lo, 2), round(hi, 2),
                                     round(med / rtt, 2), round(q[1], 2), round(q[2], 2), round(q[3], 2),
                                     cso, sso, round(retx.mean(), 2), round(100 * (retx > 0).mean(), 1),
                                     round(cmp["diff"], 2) if cmp else "",
                                     f"{cmp['mwu_p']:.2e}" if cmp else "",
                                     round(cmp["cliffs_delta"], 3) if cmp else ""] + fl)))


if __name__ == "__main__":
    main(sys.argv[1:])
