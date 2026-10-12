#!/usr/bin/env python3
"""Per-connection packet-trace summaries for the revision experiments.

Reads a classic pcap (as written by tcpdump on the namespace loopback) and
summarizes each connection, identified by its client (ephemeral) port:
packets and payload bytes per direction, TCP retransmitted segments, and
"flights": maximal runs of same-direction packets whose inter-packet gaps are
below a quarter of the emulated RTT. On a request/response exchange the
number of flights in one direction counts the round trips that direction
needed. For QUIC it additionally separates long-header (Initial/Handshake)
datagrams from short-header (1-RTT) ones and reports the anti-amplification
budget: server bytes sent before the client's second flight arrives,
against three times the bytes of the client's first flight (RFC 9000, 8.1).

    python3 -I pcap_flights.py tcp  <pcap> <server_port> <rtt_ms> > out.csv
    python3 -I pcap_flights.py quic <pcap> <server_port> <rtt_ms> > out.csv
"""
import struct
import sys
from collections import defaultdict


def packets(path):
    with open(path, "rb") as f:
        hdr = f.read(24)
        magic = struct.unpack("<I", hdr[:4])[0]
        if magic == 0xA1B2C3D4:
            endian, scale = "<", 1e-6
        elif magic == 0xA1B23C4D:
            endian, scale = "<", 1e-9
        else:
            raise ValueError("unsupported pcap")
        link = struct.unpack(endian + "I", hdr[20:24])[0]
        while True:
            rh = f.read(16)
            if len(rh) < 16:
                return
            ts, tf, caplen, origlen = struct.unpack(endian + "IIII", rh)
            data = f.read(caplen)
            off = {1: 14, 113: 16, 276: 20}.get(link, 0)  # Ethernet, Linux SLL, Linux SLL2
            ip = data[off:]
            if len(ip) < 20 or ip[0] >> 4 != 4:
                continue
            ihl = (ip[0] & 15) * 4
            tot = struct.unpack("!H", ip[2:4])[0]
            proto = ip[9]
            l4 = ip[ihl:]
            yield ts + tf * scale, proto, ihl, tot, l4


def tcp_conns(path, sport):
    """Connections keyed by (client port, sequence number of that port's use):
    a client SYN on a port starts a new connection, so ports the kernel reused
    within one trace are not merged."""
    conns, seq_of = defaultdict(list), defaultdict(int)
    for t, proto, ihl, tot, l4 in packets(path):
        if proto != 6 or len(l4) < 20:
            continue
        sp, dp, seq = struct.unpack("!HHI", l4[:8])
        doff = (l4[12] >> 4) * 4
        flags = l4[13]
        plen = tot - ihl - doff
        if dp == sport and flags & 0x12 == 0x02 and conns.get((sp, seq_of[sp])):
            if not any(f & 0x12 == 0x02 and q == seq for _, d, _, q, f in conns[(sp, seq_of[sp])]
                       if d == "c2s"):
                seq_of[sp] += 1  # a fresh SYN (not a retransmitted one): new connection
        if sp == sport:
            conns[(dp, seq_of[dp])].append((t, "s2c", plen, seq, flags))
        elif dp == sport:
            conns[(sp, seq_of[sp])].append((t, "c2s", plen, seq, flags))
    return conns


def flights(pkts, direction, gap):
    out, last = [], None
    for p in pkts:
        if p[1] != direction or p[2] <= 0:
            continue
        if last is None or p[0] - last > gap:
            out.append([0, 0])
        out[-1][0] += 1
        out[-1][1] += p[2]
        last = p[0]
    return out


def tcp_main(path, sport, rtt):
    gap = rtt / 4000.0
    print("client_port,conn_seq,t_start,c2s_pkts,c2s_bytes,s2c_pkts,s2c_bytes,c2s_retx,s2c_retx,"
          "c2s_data_flights,s2c_data_flights,s2c_first_flight_pkts,s2c_first_flight_bytes")
    for (cport, cseq), pk in tcp_conns(path, sport).items():
        pk.sort()
        row = {"c2s": [0, 0, 0], "s2c": [0, 0, 0]}
        seen = {"c2s": set(), "s2c": set()}
        for t, d, plen, seq, flags in pk:
            row[d][0] += 1
            row[d][1] += max(plen, 0)
            if plen > 0:
                if seq in seen[d]:
                    row[d][2] += 1
                seen[d].add(seq)
        fc, fs = flights(pk, "c2s", gap), flights(pk, "s2c", gap)
        ff = fs[0] if fs else [0, 0]
        print(f"{cport},{cseq},{pk[0][0]:.6f},{row['c2s'][0]},{row['c2s'][1]},{row['s2c'][0]},"
              f"{row['s2c'][1]},{row['c2s'][2]},{row['s2c'][2]},{len(fc)},{len(fs)},{ff[0]},{ff[1]}")


def quic_main(path, sport, rtt):
    gap = rtt / 4000.0
    # Connections keyed by (client port, sequence number of that port's use).
    # The client's Initial carries a fresh random Destination Connection ID per
    # connection; a client Initial whose DCID is neither that connection's
    # original DCID nor a CID the server announced (e.g. in a Retry) starts a
    # new connection, so ports the kernel reused within one trace are not merged.
    conns, seq_of, cids = defaultdict(list), defaultdict(int), {}
    for t, proto, ihl, tot, l4 in packets(path):
        if proto != 17 or len(l4) < 9:
            continue
        sp, dp, ulen = struct.unpack("!HHH", l4[:6])
        payload = ulen - 8
        h = l4[8:]
        first = h[0] if h else 0
        long_hdr = bool(first & 0x80)
        ptype = (first >> 4) & 3 if long_hdr else -1  # 0 Initial, 2 Handshake, 3 Retry (v1)
        dcid = scid = None
        if long_hdr and len(h) > 6:
            dl = h[5]
            dcid = bytes(h[6:6 + dl])
            if len(h) > 6 + dl:
                scid = bytes(h[7 + dl:7 + dl + h[6 + dl]])
        if dp == sport and ptype == 0 and dcid is not None:
            known = cids.get(sp)
            if known is not None and dcid not in known:
                seq_of[sp] += 1
                known = None
            if known is None:
                cids[sp] = {dcid}
        if sp == sport and long_hdr and scid and dp in cids:
            cids[dp].add(scid)
        if sp == sport:
            conns[(dp, seq_of[dp])].append((t, "s2c", payload, long_hdr, ptype))
        elif dp == sport:
            conns[(sp, seq_of[sp])].append((t, "c2s", payload, long_hdr, ptype))
    print("client_port,conn_seq,t_start,c2s_dgrams,c2s_bytes,s2c_dgrams,s2c_bytes,"
          "c2s_long_dgrams,s2c_long_dgrams,client_flight1_bytes,server_bytes_before_client_flight2,"
          "amp_budget,server_hs_flights,amp_limited,s2c_long_bytes,binding_limit")
    for (cport, cseq), pk in conns.items():
        pk.sort()
        c = [x for x in pk if x[1] == "c2s"]
        s = [x for x in pk if x[1] == "s2c"]
        # client's first flight: c2s datagrams before the first server datagram
        t_s1 = s[0][0] if s else float("inf")
        cf1 = sum(x[2] for x in c if x[0] < t_s1)
        # client's second flight: first c2s datagram after the server started
        later = [x for x in c if x[0] > t_s1]
        t_c2 = later[0][0] if later else float("inf")
        sb = sum(x[2] for x in s if x[0] < t_c2)
        hs = [x for x in pk if x[3]]  # long-header datagrams carry the handshake
        hs_flights = flights(hs, "s2c", gap)
        s_long = sum(x[2] for x in s if x[3])
        # Which limit capped the server's first flight (RFC 9000 s. 8.1 vs RFC 9002 s. 7.2):
        # the 3x anti-amplification budget, or the 10 x 1200-B initial congestion window.
        if len(hs_flights) <= 1:
            limit = "none"
        elif sb >= 0.9 * 3 * cf1 and 3 * cf1 < 12000:
            limit = "amplification"
        elif 0.9 * 12000 <= sb <= 1.1 * 12000:
            limit = "cwnd"
        else:
            limit = "other"
        print(f"{cport},{cseq},{pk[0][0]:.6f},{len(c)},{sum(x[2] for x in c)},{len(s)},"
              f"{sum(x[2] for x in s)},{sum(1 for x in c if x[3])},{sum(1 for x in s if x[3])},"
              f"{cf1},{sb},{3 * cf1},{len(hs_flights)},{int(len(hs_flights) > 1)},{s_long},{limit}")


if __name__ == "__main__":
    kind, path, port, rtt = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
    (tcp_main if kind == "tcp" else quic_main)(path, port, rtt)
