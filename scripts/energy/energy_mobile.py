#!/usr/bin/env python3
"""Coarse relative energy estimate for the Pixel 7 Pro (Tensor G2),
from non-root Termux battery-current logs (lines: epoch,current_uA;
current is negative during discharge). Reports mean discharge current
under sustained KEM load minus the idle baseline -> a relative power
proxy. No root and no external meter, so this is for RANKING only, not
absolute joules; values are whole-device, not KEM-isolated.
"""
import glob
import os

import numpy as np
import pandas as pd

D = "/home/anss/random/pixel data"
V = 3.85  # nominal Li-ion pack voltage (volts)


def amps_uA(fname):
    a = pd.read_csv(fname, header=None, names=["t", "i"])
    return np.abs(a["i"].to_numpy(float))  # |microamps| during discharge


idle = amps_uA(os.path.join(D, "idle.csv"))
im, isd = idle.mean(), idle.std()
print(f"idle baseline: |I| = {im/1e3:.0f} mA  (sd {isd/1e3:.0f} mA, n={len(idle)})\n")
print(f"{'scheme':28s}{'n':>4}{'|I| mA':>9}{'dI mA':>8}{'dP mW':>8}   note")
for f in sorted(glob.glob(os.path.join(D, "energy_*.csv"))):
    name = os.path.basename(f)[len("energy_"):-len(".csv")]
    x = amps_uA(f)
    dI = x.mean() - im
    dP = dI / 1e6 * V * 1e3            # mW above idle
    note = "<= looks ~idle (load likely did not run)" if dI < 2 * isd else ""
    print(f"{name:28s}{len(x):>4}{x.mean()/1e3:>9.0f}{dI/1e3:>8.0f}{dP:>8.0f}   {note}")
