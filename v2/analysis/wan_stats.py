#!/usr/bin/env python3
"""Inter-network TLS and QUIC summaries.

    python3 -I wan_stats.py <data_dir>

Per region and cell: n, median handshake time with 95% bootstrap CI, the
median in multiples of the path RTT (median TCP min_rtt of the region's
transport run), and the median difference from x25519 with the same
certificate chain and its 95% CI. The +/-1 ms equivalence margin was
pre-registered for the loopback experiments only and is not applied to
these paths, whose jitter is two orders of magnitude larger.
"""
import csv
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats_common import compare, median_ci  # noqa: E402


def main(d):
    print("region,proto,group,chain,n,path_rtt_ms,median_ms,ci_lo,ci_hi,median_rtts,"
          "diff_vs_x25519_ms,ci95_lo,ci95_hi,mwu_p")
    for r in ("frankfurt", "iowa", "mumbai"):
        tp = os.path.join(d, "wan", f"transport_{r}.csv")
        if not os.path.exists(tp):
            continue
        rtt = float(np.median([float(x["min_rtt_ms"]) for x in csv.DictReader(open(tp))]))
        for proto in ("tls", "quic"):
            p = os.path.join(d, "wan", f"{proto}_{r}.csv")
            if not os.path.exists(p):
                continue
            cells = defaultdict(list)
            for x in csv.DictReader(open(p)):
                cells[(x["group"], x["chain"])].append(float(x["hs_us"]) / 1e3)
            for (g, ch), v in sorted(cells.items(), key=lambda kv: (kv[0][1], kv[0][0])):
                med, lo, hi = median_ci(v)
                base = cells.get(("x25519", ch))
                c = compare(v, base) if base and g != "x25519" else None
                print(",".join(map(str, [r, proto, g, ch, len(v), round(rtt, 1), round(med, 1),
                                         round(lo, 1), round(hi, 1), round(med / rtt, 2),
                                         round(c["diff"], 1) if c else "",
                                         round(c["ci95_lo"], 1) if c else "",
                                         round(c["ci95_hi"], 1) if c else "",
                                         f"{c['mwu_p']:.2e}" if c else ""])))


if __name__ == "__main__":
    main(sys.argv[1])
