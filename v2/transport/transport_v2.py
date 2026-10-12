#!/usr/bin/env python3
"""Size-matched TCP transport emulation, revision 2 (run in `unshare -r -n`).

What it is: the wire pattern of an ephemeral KEM exchange with application
framing but no cryptography. The client opens a fresh TCP connection and
sends a length-prefixed message (4-byte big-endian length + random bytes of
exactly the public-key size); the server reads it and answers with a
length-prefixed message of exactly the ciphertext size. Timing runs from
just before connect() until the last ciphertext byte is read, so the 2-RTT
floor is TCP handshake + one request/response, NOT a secure handshake.

What is new relative to the first version:
  * TSO/GSO/GRO are disabled on the emulated link (netns.link_up), so netem
    applies delay and loss per 1500-byte packet;
  * every trial records TCP_INFO from both endpoints (segments, data
    segments, bytes, retransmissions, final cwnd), so retransmission
    statistics accompany every latency;
  * trials are interleaved across schemes in shuffled rounds (fixed seed);
  * packet traces (headers only) are captured per condition;
  * two mixed-congestion conditions: a 10 Mbit/s bottleneck shared with a
    competing bulk TCP flow, and a 1 Mbit/s constrained link.

Usage:  unshare -r -n python3 -I transport_v2.py <campaign> > out.csv
"""
import os
import random
import socket
import struct
import sys
import multiprocessing as mp
import threading
import time

sys.path.insert(0, "/home/anss/random/bench/v2")
import netns  # noqa: E402

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
PORT, BULK_PORT = 47101, 47202
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


class Server(threading.Thread):
    """Answers one framed request per connection; records its TCP_INFO."""

    def __init__(self):
        super().__init__(daemon=True)
        self.ls = socket.socket()
        self.ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.ls.bind(("127.0.0.1", PORT))
        self.ls.listen(64)
        self.ct_size = 0
        self.last = None
        self.done = threading.Event()

    def run(self):
        while True:
            conn, _ = self.ls.accept()
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            (n,) = struct.unpack("!I", recv_exact(conn, 4))
            recv_exact(conn, n)
            conn.sendall(struct.pack("!I", self.ct_size) + os.urandom(self.ct_size))
            # wait for the client's close so the counters cover the whole exchange
            conn.recv(1)
            self.last = tcp_info(conn)
            conn.close()
            self.done.set()


def bulk_flow(stop):
    """Competing long-lived TCP flow saturating the shared bottleneck."""
    ls = socket.socket()
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(("127.0.0.1", BULK_PORT))
    ls.listen(1)

    def sink():
        c, _ = ls.accept()
        while c.recv(1 << 20):
            pass
    threading.Thread(target=sink, daemon=True).start()
    s = socket.create_connection(("127.0.0.1", BULK_PORT))
    blob = os.urandom(1 << 16)
    while not stop.is_set():
        s.sendall(blob)
    s.close()


def one_trial(srv, pk, ct):
    srv.ct_size = ct
    srv.done.clear()
    payload = struct.pack("!I", pk) + os.urandom(pk)
    t0 = time.perf_counter()
    c = socket.create_connection(("127.0.0.1", PORT), timeout=120)
    c.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    c.sendall(payload)
    (n,) = struct.unpack("!I", recv_exact(c, 4))
    recv_exact(c, n)
    t1 = time.perf_counter()
    ci = tcp_info(c)
    c.close()
    srv.done.wait(30)
    return t1 - t0, ci, srv.last


CAMPAIGNS = {
    # tag: (rtt_ms, loss_pct, rate_mbit, queue_limit, bulk, rounds, per_round)
    "latency": [("rtt10", 10, 0, None, None, False, 10, 3),
                ("rtt50", 50, 0, None, None, False, 10, 3),
                ("rtt100", 100, 0, None, None, False, 10, 3)],
    "loss": [("rtt50_loss1", 50, 1, None, None, False, 30, 10)],
    "smoke": [("smoke", 50, 1, None, None, False, 1, 1)],
    "congestion": [("bw10_bulk_rtt50", 50, 0, 10, 100, True, 10, 3),
                   ("bw1_rtt100", 100, 0, 1, 100, False, 10, 3)],
}


def main():
    camp = sys.argv[1]
    seed = 20261012
    rng = random.Random(seed)
    netns.link_up()
    pcap_dir = "/home/anss/random/bench/v2/data/pcap"
    os.makedirs(pcap_dir, exist_ok=True)
    srv = Server()
    srv.start()
    cols = ["cond", "family", "set", "category", "pk", "ct", "rtt_ms", "loss_pct",
            "rate_mbit", "bulk", "round", "trial", "seconds"]
    tik = ["snd_cwnd", "total_retrans", "bytes_acked", "bytes_received", "segs_out",
           "segs_in", "data_segs_in", "data_segs_out", "bytes_sent", "bytes_retrans"]
    print(",".join(cols + [f"c_{k}" for k in tik] + [f"s_{k}" for k in tik]), flush=True)
    for tag, rtt, loss, rate, limit, bulk, rounds, per in CAMPAIGNS[camp]:
        netns.netem(rtt, loss, rate, limit)
        dump = netns.tcpdump(f"{pcap_dir}/transport_{tag}.pcap", snaplen=96,
                             filt=f"tcp port {PORT}")
        stop = mp.Event()
        bulk_proc = None
        if bulk:  # separate process, so the bulk sender never contends for our GIL
            bulk_proc = mp.get_context("fork").Process(target=bulk_flow, args=(stop,), daemon=True)
            bulk_proc.start()
            time.sleep(5)  # let the bulk flow reach steady state
        for r in range(rounds):
            order = SCHEMES[:]
            rng.shuffle(order)
            for fam, name, cat, pk, ct in order:
                # very slow cells on the 1 Mbit/s link: one trial per round
                n = 1 if (rate == 1 and fam == "McEliece") else per
                for t in range(n):
                    secs, ci, si = one_trial(srv, pk, ct)
                    row = [tag, fam, name, cat, pk, ct, rtt, loss, rate or "", int(bulk),
                           r, t, f"{secs:.6f}"]
                    row += [ci[k] for k in tik] + [si[k] for k in tik]
                    print(",".join(map(str, row)), flush=True)
            print(f"[{tag}] round {r + 1}/{rounds}", file=sys.stderr, flush=True)
        stop.set()
        if bulk_proc:
            bulk_proc.join(5)
            bulk_proc.kill()
        time.sleep(0.5)
        dump.terminate()
        dump.wait()
    netns.clear()


if __name__ == "__main__":
    main()
