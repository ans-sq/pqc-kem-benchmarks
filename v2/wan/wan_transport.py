#!/usr/bin/env python3
"""Size-matched TCP transport emulation over real inter-network paths.

Same wire pattern and framing as transport_v2.py, but the client names the
reply size in its request header, so one long-lived server on a remote VM
serves every scheme:
    request  = !I pk_len | !I ct_len | pk_len random bytes
    response = !I ct_len | ct_len random bytes

    server:  python3 -I wan_transport.py server <port>
    client:  python3 -I wan_transport.py client <host> <port> <trials> <tag> > out.csv
"""
import os
import random
import socket
import struct
import sys
import threading
import time

# (self-contained copy of the transport_v2 definitions, so the VM needs only this file)
SCHEMES = [  # family, set, category, pk, ct (FIPS 203; NTRU r3; HQC 2025-08-22; McEliece r4)
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
TI = struct.Struct("<8B24I4Q6I4Q2I2Q")  # struct tcp_info up to tcpi_bytes_retrans


def tcp_info(sock):
    raw = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, TI.size)
    v = TI.unpack(raw.ljust(TI.size, b"\0"))
    u32 = v[8:32]
    u64a = v[32:36]
    u32b = v[36:42]
    u64c = v[48:50]
    return dict(snd_cwnd=u32[18], total_retrans=u32[23], bytes_acked=u64a[2],
                bytes_received=u64a[3], segs_out=u32b[0], segs_in=u32b[1],
                data_segs_in=u32b[4], data_segs_out=u32b[5], bytes_sent=u64c[0],
                bytes_retrans=u64c[1])


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(1 << 20, n - len(buf)))
        if not chunk:
            raise ConnectionError("peer closed early")
        buf += chunk
    return bytes(buf)


def serve(port):
    ls = socket.socket()
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(("0.0.0.0", port))
    ls.listen(64)

    def handle(conn):
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            pk_len, ct_len = struct.unpack("!II", recv_exact(conn, 8))
            recv_exact(conn, pk_len)
            conn.sendall(struct.pack("!I", ct_len) + os.urandom(ct_len))
            conn.recv(1)
        except Exception:
            pass
        finally:
            conn.close()
    while True:
        c, _ = ls.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()


def client(host, port, trials, tag):
    rng = random.Random(20261016)
    tik = ["snd_cwnd", "total_retrans", "bytes_acked", "bytes_received", "segs_out",
           "segs_in", "data_segs_in", "data_segs_out", "bytes_sent", "bytes_retrans"]
    print(",".join(["cond", "family", "set", "category", "pk", "ct", "round", "seconds",
                    "tcp_connect_s", "min_rtt_ms"] + [f"c_{k}" for k in tik]), flush=True)
    for r in range(trials):
        order = SCHEMES[:]
        rng.shuffle(order)
        for fam, name, cat, pk, ct in order:
            payload = struct.pack("!II", pk, ct) + os.urandom(pk)
            t0 = time.perf_counter()
            c = socket.create_connection((host, port), timeout=120)
            t1 = time.perf_counter()
            c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            c.sendall(payload)
            (n,) = struct.unpack("!I", recv_exact(c, 4))
            recv_exact(c, n)
            t2 = time.perf_counter()
            ti = tcp_info(c)
            raw = c.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, 160)
            min_rtt_us = struct.unpack_from("<I", raw, 148)[0]
            c.close()
            print(",".join(map(str, [tag, fam, name, cat, pk, ct, r, f"{t2 - t0:.6f}",
                                     f"{t1 - t0:.6f}", f"{min_rtt_us / 1000:.2f}"]
                               + [ti[k] for k in tik])), flush=True)
        print(f"[{tag}] round {r + 1}/{trials}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "server":
        serve(int(sys.argv[2]))
    else:
        client(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5])
