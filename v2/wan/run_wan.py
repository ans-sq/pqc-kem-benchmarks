#!/usr/bin/env python3
"""Inter-network campaign: size-matched transport, TLS 1.3 and QUIC from this
machine to one VM per region (servers: vm_servers.sh). Clients are pinned to
an E-core (cpu 8) so the run can overlap the loopback campaigns, which use
the P-cores. Each cell is visited in interleaved, shuffled rounds.

    python3 -I run_wan.py <region> [rounds]
"""
import csv
import io
import os
import random
import socket
import subprocess
import sys
import time

V2 = "/home/anss/random/bench/v2"
OSSL35 = "/home/anss/random/bench/quic/openssl-install"
ZONE = {"mumbai": "asia-south1-a", "frankfurt": "europe-west3-a", "iowa": "us-central1-a"}
CPU = "8"
C = f"{V2}/tls/certs35"
TLS_CELLS = [(44330, g, f"{C}/single.pem", False, "single")
             for g in ("x25519", "X25519MLKEM768", "MLKEM768", "MLKEM1024")] + \
            [(44331, g, f"{C}/single.pem", True, "single") for g in ("hqc1", "hqc5")] + \
            [(44332, g, f"{C}/mldsa65-root.pem", False, "mldsa65")
             for g in ("x25519", "X25519MLKEM768")]
QUIC_CELLS = [(4455, g, f"{C}/single.pem", False, "single")
              for g in ("x25519", "X25519MLKEM768", "MLKEM1024")] + \
             [(4456, g, f"{C}/single.pem", True, "single") for g in ("hqc1", "hqc5")] + \
             [(4457, g, f"{C}/mldsa65-root.pem", False, "mldsa65")
              for g in ("x25519", "X25519MLKEM768")]


def env():
    return dict(os.environ, OPENSSL_MODULES=f"{V2}/oqsprov35-012/lib",
                OPENSSL_CONF=f"{V2}/tls/openssl35.cnf",
                LD_LIBRARY_PATH=f"{OSSL35}/lib:{V2}/install-016-hqcavx2/lib")


def gcloud(*args, **kw):
    return subprocess.run(["gcloud", *args], capture_output=True, text=True, **kw)


def run_cells(kind, ip, cells, rounds, per, out, region, seed):
    rng = random.Random(seed)
    w = None
    binary = f"{V2}/tls/tls_hs" if kind == "tls" else f"{V2}/quic/quic_hs"
    for r in range(rounds):
        order = cells[:]
        rng.shuffle(order)
        for port, g, ca, oqs, chain in order:
            args = [ip, str(port), g, str(per)] + (["full", ca] if kind == "tls" else [ca])
            if oqs:
                args.append("oqs")
            p = subprocess.run(["taskset", "-c", CPU, binary, *args], env=env(),
                               capture_output=True, text=True, timeout=600)
            if p.returncode:
                print(f"[{region} {kind}] {g}/{chain} failed: {p.stderr[:300]}",
                      file=sys.stderr, flush=True)
                continue
            for row in csv.DictReader(io.StringIO(p.stdout)):
                row.update(region=region, chain=chain, round=r, port=port)
                if w is None:
                    w = csv.DictWriter(out, fieldnames=list(row))
                    w.writeheader()
                w.writerow(row)
            out.flush()
        print(f"[{region} {kind}] round {r + 1}/{rounds}", file=sys.stderr, flush=True)


def main():
    region = sys.argv[1]
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    zone = ZONE[region]
    ip = gcloud("compute", "instances", "describe", f"pqc-bench-{region}", f"--zone={zone}",
                "--format=value(networkInterfaces[0].accessConfigs[0].natIP)").stdout.strip()
    print(f"{region}: {ip}", file=sys.stderr, flush=True)
    hold = subprocess.Popen(["gcloud", "compute", "ssh", f"pqc-bench-{region}", f"--zone={zone}",
                             "--quiet", "--command", "bash ~/pqc/vm_servers.sh"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True)
    while "SERVERS UP" not in (hold.stdout.readline() or "SERVERS UP"):
        pass
    for _ in range(60):  # wait for the TCP servers to accept from here
        try:
            socket.create_connection((ip, 47101), timeout=3).close()
            break
        except OSError:
            time.sleep(1)
    time.sleep(2)
    d = f"{V2}/data/wan"
    os.makedirs(d, exist_ok=True)
    try:
        with open(f"{d}/transport_{region}.csv", "w") as f:
            subprocess.run(["taskset", "-c", CPU, "python3", "-I", f"{V2}/wan/wan_transport.py",
                            "client", ip, "47101", str(rounds * 3), region], stdout=f, check=True)
        with open(f"{d}/tls_{region}.csv", "w") as f:
            run_cells("tls", ip, TLS_CELLS, rounds, 3, f, region, 20261017)
        with open(f"{d}/quic_{region}.csv", "w") as f:
            run_cells("quic", ip, QUIC_CELLS, rounds, 3, f, region, 20261018)
    finally:
        hold.stdin.close()
        try:
            hold.wait(timeout=30)
        except subprocess.TimeoutExpired:
            hold.kill()
        time.sleep(2)
        gcloud("compute", "scp", f"pqc-bench-{region}:/tmp/wan.pcap", f"{d}/wan_{region}.pcap",
               f"--zone={zone}", "--quiet")
        print(f"{region}: done", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
