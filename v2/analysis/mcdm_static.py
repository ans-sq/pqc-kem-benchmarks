#!/usr/bin/env python3
"""Static-key supplement to mcdm_v2.py (review item P0-1).

(1) Scenario rankings under every security encoding and normalization, for
both implementation choices; (2) the ciphertext-weight crossover: the
smallest share of weight on ciphertext size (other static-key weights
scaled proportionally) at which Classic McEliece leads; (3) the share of
20,000 flat-Dirichlet weight vectors over the four static-key criteria in
which each family leads.

    python3 -I mcdm_static.py <data_dir>
"""
import sys

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from mcdm_v2 import (FAM, IM_ENC, MC_ENC, SCEN, cpu_columns, load_cpu,  # noqa: E402
                     matrix, topsis)


def main(d):
    cpu = load_cpu(d)
    for choice in ("best available code", "liboqs 0.16.0 as released"):
        kg, on = cpu_columns(cpu, choice)
        print(f"\n######## {choice}")
        print("  [1] leader per scenario x encoding x normalization")
        for sc, pri in SCEN.items():
            w = np.array(pri, float) / sum(pri)
            for ie, im in IM_ENC.items():
                for me, mc in MC_ENC.items():
                    X, cost, _ = matrix(kg, on, im, mc)
                    leaders = []
                    for how in ("vector", "max", "minmax", "log-vector"):
                        s = topsis(X, w, cost, how)
                        o = np.argsort(-s)
                        leaders.append(f"{how}:{FAM[o[0]]}>{FAM[o[1]]}>{FAM[o[2]]}>{FAM[o[3]]}")
                    print(f"    {sc:18s} impl={ie:20s} math={me:18s} " + "  ".join(leaders))
        print("  [2] static-key crossover: ct weight share at which McEliece first leads")
        base = np.array(SCEN["Static-key"], float)
        for ie, im in IM_ENC.items():
            for me, mc in MC_ENC.items():
                X, cost, _ = matrix(kg, on, im, mc)
                res = []
                for how in ("vector", "max", "minmax", "log-vector"):
                    cross = None
                    for share in np.linspace(0.0, 1.0, 1001):
                        rest = base.copy(); rest[1] = 0
                        w = rest / rest.sum() * (1 - share); w[1] = share
                        if np.argmax(topsis(X, w, cost, how)) == 3:
                            cross = share
                            break
                    res.append(f"{how}:{'never' if cross is None else f'{cross:.3f}'}")
                print(f"    impl={ie:20s} math={me:18s} " + "  ".join(res))
        print("  [3] flat-Dirichlet weights over static-key criteria (ct, online, impl, math): leader share")
        rng = np.random.default_rng(20260615)
        W4 = rng.dirichlet(np.ones(4), 20000)
        for ie, im in IM_ENC.items():
            for me, mc in MC_ENC.items():
                X, cost, _ = matrix(kg, on, im, mc, [1, 3, 4, 5])
                wins = np.zeros(4, int)
                for w in W4:
                    wins[np.argmax(topsis(X, w, cost))] += 1
                print(f"    impl={ie:20s} math={me:18s} " +
                      "  ".join(f"{f}={100 * v / len(W4):.1f}%" for f, v in zip(FAM, wins)))


if __name__ == "__main__":
    main(sys.argv[1])
