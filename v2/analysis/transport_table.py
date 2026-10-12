#!/usr/bin/env python3
"""LaTeX rows of the transport table (tab:transport) from transport_stats.py output.

    python3 -I transport_table.py <latency_stats.csv> <loss_stats.csv> <congestion_stats.csv>
"""
import csv
import sys

ORDER = ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024", "ntruhps2048677", "ntruhps4096821",
         "HQC-1", "HQC-3", "HQC-5", "mceliece348864", "mceliece460896", "mceliece8192128"]
SIZES = {"ML-KEM-512": (800, 768), "ML-KEM-768": (1184, 1088), "ML-KEM-1024": (1568, 1568),
         "ntruhps2048677": (930, 930), "ntruhps4096821": (1230, 1230), "HQC-1": (2241, 4433),
         "HQC-3": (4514, 8978), "HQC-5": (7237, 14421), "mceliece348864": (261120, 96),
         "mceliece460896": (524160, 156), "mceliece8192128": (1357824, 208)}


def load(path):
    return {(r["cond"], r["set"]): r for r in csv.DictReader(open(path))}


def num(v, nd=0):
    v = float(v)
    s = f"{v:,.{nd}f}"
    return s.replace(",", "{,}")


def main(lat, loss, cong):
    L, S, C = load(lat), load(loss), load(cong)
    for i, s in enumerate(ORDER):
        if s in ("ntruhps2048677", "HQC-1", "mceliece348864"):
            print("\\addlinespace")
        pk, ct = SIZES[s]
        r10, r50, r100 = (L[(c, s)] for c in ("rtt10", "rtt50", "rtt100"))
        lo = S[("rtt50_loss1", s)]
        b10, b1 = C[("bw10_bulk_rtt50", s)], C[("bw1_rtt100", s)]
        cells = [s, num(pk), num(ct),
                 f"{float(r10['median_rtts']):.2f}", f"{float(r50['median_rtts']):.2f}",
                 f"{float(r100['median_rtts']):.2f}",
                 num(r50["c_data_segs_out_med"]), num(r50["c2s_flights_med"]),
                 num(lo["median_ms"]), num(lo["p99_ms"]), f"{float(lo['retx_trials_pct']):.1f}",
                 num(b10["median_ms"]), num(b1["median_ms"])]
        print(" & ".join(cells) + " \\\\")


if __name__ == "__main__":
    main(*sys.argv[1:4])
