#!/usr/bin/env python3
"""PQ-QUIC handshake campaigns (run inside `unshare -r -n`).

    unshare -r -n python3 -I quic_campaign.py main  > ../data/quic_main.csv
    unshare -r -n python3 -I quic_campaign.py chain > ../data/quic_chain.csv

OpenSSL 3.5 QUIC (server: quic_srv.c, client: quic_hs.c). x25519 and the
ML-KEM groups use OpenSSL 3.5's native implementations; HQC groups load
oqs-provider 0.12.0 (built for 3.5) over a shared liboqs 0.16.0 selected by
LD_LIBRARY_PATH ("016" = liboqs reference HQC, "016-hqcavx2" = official AVX2).
Packet traces per condition feed quic_pcap.py (datagrams, bytes, flights,
anti-amplification accounting).
"""
import csv
import io
import os
import random
import subprocess
import sys

sys.path.insert(0, "/home/anss/random/bench/v2")
import netns  # noqa: E402

V2 = "/home/anss/random/bench/v2"
OSSL35 = "/home/anss/random/bench/quic/openssl-install/lib"
CERTS = f"{V2}/tls/certs35"
SERVER_CPU, CLIENT_CPU = "2", "0"
PORT = 4455
SINGLE = ("single", f"{CERTS}/single.pem", f"{CERTS}/single.key", f"{CERTS}/single.pem")


def chain(alg):
    return (alg, f"{CERTS}/{alg}-chain.pem", f"{CERTS}/{alg}-leaf.key", f"{CERTS}/{alg}-root.pem")


def run_cell(impl, group, ch, n, retry=False):
    name, chainf, key, ca = ch
    oqs = group.startswith("hqc")
    env = dict(os.environ, OPENSSL_MODULES=f"{V2}/oqsprov35-012/lib",
               LD_LIBRARY_PATH=f"{OSSL35}:{V2}/install-{impl}/lib")
    extra = ["oqs"] if oqs else []
    srv_extra = (["oqs"] if oqs else ["-"]) + (["retry"] if retry else [])
    srv = subprocess.Popen(["taskset", "-c", SERVER_CPU, f"{V2}/quic/quic_srv", str(PORT),
                            chainf, key, group, str(n)] + srv_extra, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if not netns.wait_listen(PORT, proto="udp"):
        srv.kill()
        raise RuntimeError(f"quic server did not start {impl} {group} {name}")
    cli = subprocess.run(["taskset", "-c", CLIENT_CPU, f"{V2}/quic/quic_hs", "127.0.0.1",
                          str(PORT), group, str(n), ca] + extra, env=env,
                         capture_output=True, text=True, timeout=1800)
    try:
        srv.wait(timeout=15)
    except subprocess.TimeoutExpired:
        srv.kill()
    if cli.returncode:
        raise RuntimeError(f"quic client failed {impl} {group} {name}: {cli.stderr[:400]}")
    return list(csv.DictReader(io.StringIO(cli.stdout)))


def campaign(conds, cells, rounds, per, out, seed):
    rng = random.Random(seed)
    w = None
    for c in conds:
        netns.netem(c["rtt"], c.get("loss", 0))
        dump = netns.tcpdump(f"{V2}/data/pcap/quic_{c['tag']}.pcap", snaplen=128,
                             filt=f"udp port {PORT}")
        for r in range(rounds):
            order = cells[:]
            rng.shuffle(order)
            for impl, group, ch in order:
                for row in run_cell(impl, group, ch, per, c.get("retry", False)):
                    row.update(impl=impl, chain=ch[0], rtt_ms=c["rtt"], retry=int(c.get("retry", False)),
                               loss_pct=c.get("loss", 0), round=r, cond=c["tag"])
                    if w is None:
                        w = csv.DictWriter(out, fieldnames=list(row))
                        w.writeheader()
                    w.writerow(row)
            out.flush()
            print(f"[{c['tag']}] round {r + 1}/{rounds}", file=sys.stderr, flush=True)
        dump.terminate()
        dump.wait()
    netns.clear()


def main():
    which = sys.argv[1]
    os.makedirs(f"{V2}/data/pcap", exist_ok=True)
    netns.link_up()
    if which == "main":
        cells = [("016", g, SINGLE) for g in
                 ("x25519", "X25519MLKEM768", "MLKEM768", "MLKEM1024", "hqc1", "hqc5")] + \
                [("016-hqcavx2", g, SINGLE) for g in ("hqc1", "hqc5")]
        campaign([dict(tag="rtt10", rtt=10), dict(tag="rtt50", rtt=50),
                  dict(tag="rtt100", rtt=100)], cells, 10, 15, sys.stdout, 20261012)
        campaign([dict(tag="rtt50_loss1", rtt=50, loss=1)], cells, 15, 20, sys.stdout, 20261013)
        campaign([dict(tag="rtt50_retry", rtt=50, retry=True)], cells, 5, 20, sys.stdout, 20261015)
    elif which == "chain":
        groups = [("016", "x25519"), ("016", "X25519MLKEM768"), ("016-hqcavx2", "hqc1")]
        cells = [(i, g, chain(a)) for i, g in groups
                 for a in ("ecdsa", "rsa2048", "mldsa44", "mldsa65", "mldsa87")]
        campaign([dict(tag="chain_rtt50", rtt=50)], cells, 5, 20, sys.stdout, 20261014)
    elif which == "smoke":
        cells = [("016", "X25519MLKEM768", SINGLE), ("016-hqcavx2", "hqc1", SINGLE),
                 ("016", "x25519", chain("mldsa65"))]
        campaign([dict(tag="smoke", rtt=50)], cells, 1, 3, sys.stdout, 1)


if __name__ == "__main__":
    main()
