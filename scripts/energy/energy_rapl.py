#!/usr/bin/env python3
"""Desktop energy via Intel RAPL (reviewer item #13, the reliable path).
Brackets each liboqs `speed_kem` run with reads of the package energy
counter and reports average power; combined with the per-operation times
(speed_parsed.json) this yields a relative energy-per-handshake figure
for the MCDM energy criterion.

RAPL's energy_uj is root-only, so run with sudo:

    sudo python3 energy_rapl.py

Output: per scheme -- wall time, package energy (J), average power (W).
"""
import subprocess
import time

RAPL = "/sys/class/powercap/intel-rapl:0"
SPEED = "/home/anss/random/bench/liboqs/build/tests/speed_kem"
KEMS = ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024",
        "NTRU-HPS-2048-677", "NTRU-HRSS-701", "NTRU-HPS-4096-821",
        "Classic-McEliece-348864", "Classic-McEliece-460896",
        "Classic-McEliece-8192128"]


def read_uj():
    with open(f"{RAPL}/energy_uj") as f:
        return int(f.read())


def main():
    try:
        max_uj = int(open(f"{RAPL}/max_energy_range_uj").read())
    except PermissionError:
        raise SystemExit("RAPL energy_uj is root-only -- run with: sudo python3 energy_rapl.py")
    print(f"{'scheme':28s}{'wall_s':>8}{'energy_J':>10}{'avg_W':>8}")
    for k in KEMS:
        e0 = read_uj(); t0 = time.perf_counter()
        subprocess.run([SPEED, k], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        t1 = time.perf_counter(); e1 = read_uj()
        dE = (e1 - e0) if e1 >= e0 else (e1 - e0 + max_uj)   # handle counter wrap
        dt = t1 - t0
        print(f"{k:28s}{dt:>8.1f}{dE/1e6:>10.2f}{dE/1e6/dt:>8.1f}", flush=True)


if __name__ == "__main__":
    main()
