"""Shared network-namespace helpers for the revision experiments.

Every campaign runs inside `unshare -r -n`, i.e. a private network
namespace whose loopback is the emulated link. Compared with the first
version of the experiments, the link set-up now also disables TCP/generic
segmentation and receive offload, so netem delays and drops individual
1500-byte packets rather than 64-kB GSO super-packets.
"""
import socket
import subprocess
import time


def sh(*cmd, check=True):
    return subprocess.run(cmd, check=check, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL)


def link_up(mtu=1500):
    sh("ip", "link", "set", "lo", "up")
    sh("ip", "link", "set", "lo", "mtu", str(mtu))
    sh("ethtool", "-K", "lo", "tso", "off", "gso", "off", "gro", "off")


def netem(rtt_ms, loss_pct=0.0, rate_mbit=None, limit=None):
    """Symmetric emulation on loopback: each direction traverses lo once, so
    a one-way delay of rtt/2 gives the target RTT and loss applies per
    direction."""
    sh("tc", "qdisc", "del", "dev", "lo", "root", check=False)
    cmd = ["tc", "qdisc", "add", "dev", "lo", "root", "netem",
           "delay", f"{rtt_ms / 2:g}ms"]
    if loss_pct:
        cmd += ["loss", f"{loss_pct:g}%"]
    if rate_mbit:
        cmd += ["rate", f"{rate_mbit:g}mbit"]
    if limit:
        cmd += ["limit", str(limit)]
    sh(*cmd)


def clear():
    sh("tc", "qdisc", "del", "dev", "lo", "root", check=False)


def wait_listen(port, proto="tcp", timeout=10.0):
    """Wait until something listens on port without consuming an accept."""
    flag = "-ltn" if proto == "tcp" else "-lun"
    t0 = time.time()
    while time.time() - t0 < timeout:
        out = subprocess.run(["ss", flag], capture_output=True, text=True).stdout
        if f":{port} " in out:
            return True
        time.sleep(0.05)
    return False


def tcpdump(path, snaplen=128, filt=None):
    cmd = ["tcpdump", "-Z", "root", "-i", "lo", "-s", str(snaplen), "-U", "-w", path]
    if filt:
        cmd += filt.split()
    p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.8)
    return p
