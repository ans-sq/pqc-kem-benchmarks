#!/usr/bin/env python3
"""Transport-level KEM key-exchange emulation under controlled RTT.

Emulates the wire pattern of an ephemeral KEM handshake: the client
opens a fresh TCP connection, sends a public key of authentic size,
and the server replies with a ciphertext of authentic size. Payload
bytes are random; TCP behavior (initial congestion window, slow
start) depends only on sizes, which is the variable under test.

Run inside a network namespace whose loopback has MTU 1500 and a
netem qdisc:  unshare -r -n python3 kex_transport_bench.py <rtt_ms>
The script itself configures lo and netem for each RTT it tests.

Output: CSV on stdout  (scheme,set,category,pk,ct,rtt_ms,trial,seconds)
"""
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time

# (family, parameter set, category, pk bytes, ct bytes)
# Sources: FIPS 203; NTRU round-3 submission; HQC spec 2025-08-22;
# Classic McEliece round-4 submission.
SCHEMES = [
    ("ML-KEM", "ML-KEM-512", 1, 800, 768),
    ("ML-KEM", "ML-KEM-768", 3, 1184, 1088),
    ("ML-KEM", "ML-KEM-1024", 5, 1568, 1568),
    ("NTRU", "ntruhps2048677", 1, 930, 930),
    ("NTRU", "ntruhps4096821", 3, 1230, 1230),
    ("HQC", "HQC-1", 1, 2241, 4433),
    ("HQC", "HQC-3", 3, 4514, 8978),
    ("HQC", "HQC-5", 5, 7237, 14421),
    ("McEliece", "mceliece348864", 1, 261120, 96),
    ("McEliece", "mceliece460896", 3, 524160, 156),
    ("McEliece", "mceliece8192128", 5, 1357824, 208),
]

RTTS_MS = [int(x) for x in os.environ.get("RTTS", "10,50,100").split(",")]
LOSS = os.environ.get("LOSS")  # e.g. "1%" -> netem random loss each direction
TRIALS = int(os.environ.get("TRIALS", "30"))
PORT = 47101


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            raise ConnectionError("peer closed early")
        buf += chunk
    return buf


def server_loop(sock, ct_size, n_conns, ready):
    ready.set()
    for _ in range(n_conns):
        conn, _ = sock.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        (pk_len,) = struct.unpack("!I", recv_exact(conn, 4))
        recv_exact(conn, pk_len)
        ct = os.urandom(ct_size)
        conn.sendall(struct.pack("!I", len(ct)) + ct)
        conn.close()


def set_netem(rtt_ms):
    subprocess.run(["tc", "qdisc", "del", "dev", "lo", "root"],
                   stderr=subprocess.DEVNULL)
    cmd = ["tc", "qdisc", "add", "dev", "lo", "root", "netem",
           "delay", f"{rtt_ms/2:g}ms"]
    if LOSS:
        cmd += ["loss", LOSS]
    subprocess.run(cmd, check=True)


def bench_one(pk_size, ct_size, rtt_ms):
    """One handshake: connect, send pk, receive ct. Returns seconds."""
    pk = os.urandom(pk_size)
    t0 = time.perf_counter()
    c = socket.create_connection(("127.0.0.1", PORT), timeout=60)
    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    c.sendall(struct.pack("!I", len(pk)) + pk)
    (ct_len,) = struct.unpack("!I", recv_exact(c, 4))
    recv_exact(c, ct_len)
    t1 = time.perf_counter()
    c.close()
    return t1 - t0


def main():
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True)
    subprocess.run(["ip", "link", "set", "lo", "mtu", "1500"], check=True)

    print("scheme,set,category,pk,ct,rtt_ms,trial,seconds")
    for rtt in RTTS_MS:
        set_netem(rtt)
        for fam, name, cat, pk, ct in SCHEMES:
            lsock = socket.socket()
            lsock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            lsock.bind(("127.0.0.1", PORT))
            lsock.listen(8)
            ready = threading.Event()
            t = threading.Thread(target=server_loop,
                                 args=(lsock, ct, TRIALS, ready),
                                 daemon=True)
            t.start()
            ready.wait()
            for trial in range(TRIALS):
                secs = bench_one(pk, ct, rtt)
                print(f"{fam},{name},{cat},{pk},{ct},{rtt},{trial},"
                      f"{secs:.6f}", flush=True)
            t.join(timeout=30)
            lsock.close()
    subprocess.run(["tc", "qdisc", "del", "dev", "lo", "root"],
                   stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
