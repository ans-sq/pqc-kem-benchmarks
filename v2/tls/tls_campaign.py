#!/usr/bin/env python3
"""TLS 1.3 handshake campaigns for the revision (run inside `unshare -r -n`).

    unshare -r -n python3 -I tls_campaign.py main   > ../data/tls_main.csv
    unshare -r -n python3 -I tls_campaign.py resume > ../data/tls_resume.csv
    unshare -r -n python3 -I tls_campaign.py chain  > ../data/tls_chain.csv

Each cell (implementation x group x certificate chain x mode) is measured in
interleaved rounds: every round visits all cells of a condition in a freshly
shuffled order (fixed seed), so slow drift (thermal state, background load)
spreads evenly over cells instead of biasing whichever ran last. Server and
client are pinned to different physical P-cores. The handshake timer and the
TCP_INFO counters are in tls_hs.c.

Stack: OpenSSL 3.5 (s_server and tls_hs). x25519, the ML-KEM groups and the
X25519MLKEM768 hybrid use OpenSSL's native implementations; HQC groups load
oqs-provider 0.12.0 over a shared liboqs 0.16.0 selected by LD_LIBRARY_PATH:
"016" (HQC = liboqs reference code, 2025 spec) or "016-hqcavx2" (HQC =
official 2025 AVX2 code linked into the same liboqs).
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
PROV = f"{V2}/oqsprov35-012/lib"
OSSL35 = "/home/anss/random/bench/quic/openssl-install"
CERTS = f"{V2}/tls/certs35"
SERVER_CPU, CLIENT_CPU = "2", "0"
PORT = 44330

# pre-registered analysis margin for the equivalence test (see tls_stats.py)
EQUIV_MARGIN_MS = 1.0

SINGLE = ("single", f"{CERTS}/single.pem", f"{CERTS}/single.key", None,
          f"{CERTS}/single.pem")


def chain(alg):
    return (alg, f"{CERTS}/{alg}-leaf.pem", f"{CERTS}/{alg}-leaf.key",
            f"{CERTS}/{alg}-int.pem", f"{CERTS}/{alg}-root.pem")


BASE_GROUPS = ["x25519", "X25519MLKEM768", "MLKEM512", "MLKEM768", "MLKEM1024",
               "hqc1", "hqc3", "hqc5"]
AVX_GROUPS = ["hqc1", "hqc3", "hqc5"]
REF, AVX = "016", "016-hqcavx2"   # liboqs 0.16.0: reference HQC / official AVX2 HQC


def run_cell(impl, group, ch, mode, n):
    name, cert, key, inter, ca = ch
    oqs = group.startswith("hqc") or "_" in group   # provider groups (hqc*, x25519_*)
    env = dict(os.environ, OPENSSL_MODULES=PROV, OPENSSL_CONF=f"{V2}/tls/openssl35.cnf",
               LD_LIBRARY_PATH=f"{OSSL35}/lib:{V2}/install-{impl}/lib")
    srv_cmd = ["taskset", "-c", SERVER_CPU, f"{OSSL35}/bin/openssl", "s_server"]
    if oqs:
        srv_cmd += ["-provider", "oqsprovider", "-provider", "default"]
    srv_cmd += ["-tls1_3", "-groups", group, "-cert", cert, "-key", key,
                "-accept", str(PORT), "-naccept", str(n + (mode == "resume")),
                "-rev", "-quiet"]
    if inter:
        srv_cmd += ["-cert_chain", inter]
    srv = subprocess.Popen(srv_cmd, env=env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if not netns.wait_listen(PORT):
        srv.kill()
        raise RuntimeError(f"server did not start: {impl} {group} {name}")
    cli = subprocess.run(["taskset", "-c", CLIENT_CPU, f"{V2}/tls/tls_hs",
                          "127.0.0.1", str(PORT), group, str(n), mode, ca]
                         + (["oqs"] if oqs else []),
                         env=env, capture_output=True, text=True, timeout=1800)
    try:
        srv.wait(timeout=15)
    except subprocess.TimeoutExpired:
        srv.kill()
    if cli.returncode:
        raise RuntimeError(f"client failed {impl} {group} {name}: {cli.stderr[:400]}")
    return list(csv.DictReader(io.StringIO(cli.stdout)))


def campaign(conditions, cells, rounds, per, out, pcap_dir=None, seed=20261012):
    # cells whose liboqs build is absent on this host (the official AVX2 HQC
    # build exists only on x86) are skipped, not failed
    missing = sorted({c[0] for c in cells if not os.path.isdir(f"{V2}/install-{c[0]}")})
    if missing:
        print(f"skipping cells of absent builds: {missing}", file=sys.stderr, flush=True)
        cells = [c for c in cells if c[0] not in missing]
    rng = random.Random(seed)
    w = None
    for cond in conditions:
        rtt, loss = cond["rtt"], cond.get("loss", 0)
        netns.netem(rtt, loss)
        dump = None
        if pcap_dir:
            dump = netns.tcpdump(f"{pcap_dir}/tls_{cond['tag']}.pcap",
                                 filt=f"tcp port {PORT}")
        for r in range(rounds):
            order = cells[:]
            rng.shuffle(order)
            for impl, group, ch, mode in order:
                for row in run_cell(impl, group, ch, mode, per):
                    row.update(impl=impl, chain=ch[0], rtt_ms=rtt, loss_pct=loss,
                               round=r, cond=cond["tag"])
                    if w is None:
                        w = csv.DictWriter(out, fieldnames=list(row.keys()))
                        w.writeheader()
                    w.writerow(row)
            out.flush()
            print(f"[{cond['tag']}] round {r + 1}/{rounds} done", file=sys.stderr, flush=True)
        if dump:
            dump.terminate()
            dump.wait()
    netns.clear()


def main():
    which = sys.argv[1]
    pcap_dir = f"{V2}/data/pcap"
    os.makedirs(pcap_dir, exist_ok=True)
    netns.link_up()
    out = sys.stdout
    if which == "main":
        cells = [(REF, g, SINGLE, "full") for g in BASE_GROUPS] + \
                [(AVX, g, SINGLE, "full") for g in AVX_GROUPS]
        conds = [dict(tag="rtt10", rtt=10), dict(tag="rtt50", rtt=50),
                 dict(tag="rtt100", rtt=100)]
        campaign(conds, cells, rounds=10, per=20, out=out, pcap_dir=pcap_dir)
        campaign([dict(tag="rtt50_loss1", rtt=50, loss=1)], cells, rounds=15,
                 per=20, out=out, pcap_dir=pcap_dir, seed=20261013)
    elif which == "resume":
        groups = [(REF, "x25519"), (REF, "X25519MLKEM768"),
                  (REF, "MLKEM768"), (REF, "hqc1"), (AVX, "hqc1")]
        cells = [(i, g, SINGLE, m) for i, g in groups for m in ("full", "resume")]
        campaign([dict(tag="resume_rtt50", rtt=50)], cells, rounds=10, per=20, out=out)
    elif which == "chain":
        groups = [(REF, "x25519"), (REF, "X25519MLKEM768"),
                  (AVX, "hqc1"), (AVX, "hqc5")]
        cells = [(i, g, chain(a), "full") for i, g in groups
                 for a in ("ecdsa", "rsa2048", "mldsa44", "mldsa65", "mldsa87")]
        campaign([dict(tag="chain_rtt50", rtt=50)], cells, rounds=5, per=20, out=out,
                 pcap_dir=pcap_dir)
    elif which == "provider":
        # Provider-path control: ML-KEM and HQC through the same oqs-provider
        # hybrid code path (x25519_mlkem512 vs x25519_hqc1), against native
        # X25519MLKEM768 and the classical baseline.
        cells = [(REF, "x25519", SINGLE, "full"), (REF, "X25519MLKEM768", SINGLE, "full"),
                 (REF, "x25519_mlkem512", SINGLE, "full"), (AVX, "x25519_hqc1", SINGLE, "full"),
                 (REF, "x25519_hqc1", SINGLE, "full")]
        campaign([dict(tag="prov_rtt10", rtt=10), dict(tag="prov_rtt50", rtt=50)], cells,
                 rounds=10, per=20, out=out, seed=20261019)
    elif which == "smoke":
        cells = [(REF, "x25519", SINGLE, "full"), (AVX, "hqc1", SINGLE, "full"),
                 (REF, "hqc1", SINGLE, "full"),
                 (REF, "X25519MLKEM768", chain("mldsa65"), "full"),
                 (REF, "MLKEM768", SINGLE, "resume")]
        campaign([dict(tag="smoke", rtt=50)], cells, rounds=1, per=3, out=out)


if __name__ == "__main__":
    main()
