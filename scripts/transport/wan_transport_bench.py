#!/usr/bin/env python3
"""Real-WAN transport-level KEM exchange (reviewer item #12). Same wire
pattern as kex_transport_bench.py, but split across a real Internet path
instead of loopback+netem: the client sends a public key of authentic
size and the server replies with a ciphertext of authentic size, so the
genuine path RTT and TCP slow-start / congestion-window behaviour are
what is measured. Payload bytes are random; only sizes matter.

  server (on the remote VM):  python3 wan_transport_bench.py server [port]
  client (local):             python3 wan_transport_bench.py client <host> <port> [trials]

Client emits CSV to stdout:  scheme,set,category,pk,ct,trial,seconds
The server is stateless: the client tells it the ciphertext size to return.
"""
import os
import socket
import struct
import sys
import time

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


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            raise ConnectionError("peer closed early")
        buf += chunk
    return bytes(buf)


def server(port):
    ls = socket.socket()
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(("0.0.0.0", port))
    ls.listen(16)
    sys.stderr.write(f"wan-bench server listening on :{port}\n")
    sys.stderr.flush()
    while True:
        try:
            conn, _ = ls.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            (pk_len,) = struct.unpack("!I", recv_exact(conn, 4))
            recv_exact(conn, pk_len)
            (ct_len,) = struct.unpack("!I", recv_exact(conn, 4))
            conn.sendall(struct.pack("!I", ct_len) + os.urandom(ct_len))
            conn.close()
        except Exception as e:
            sys.stderr.write(f"conn error: {e}\n")
            sys.stderr.flush()


def bench_one(host, port, pk_size, ct_size):
    pk = os.urandom(pk_size)
    t0 = time.perf_counter()
    c = socket.create_connection((host, port), timeout=60)
    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    c.sendall(struct.pack("!I", pk_size) + pk + struct.pack("!I", ct_size))
    (ct_len,) = struct.unpack("!I", recv_exact(c, 4))
    recv_exact(c, ct_len)
    dt = time.perf_counter() - t0
    c.close()
    return dt


def client(host, port, trials):
    print("scheme,set,category,pk,ct,trial,seconds")
    for fam, name, cat, pk, ct in SCHEMES:
        for trial in range(trials):
            try:
                secs = bench_one(host, port, pk, ct)
                print(f"{fam},{name},{cat},{pk},{ct},{trial},{secs:.6f}", flush=True)
            except Exception as e:
                sys.stderr.write(f"{name} trial {trial}: {e}\n")
                sys.stderr.flush()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("server", "client"):
        sys.exit("usage: server [port] | client <host> <port> [trials]")
    if sys.argv[1] == "server":
        server(int(sys.argv[2]) if len(sys.argv) > 2 else 47101)
    else:
        client(sys.argv[2], int(sys.argv[3]),
               int(sys.argv[4]) if len(sys.argv) > 4 else 30)
