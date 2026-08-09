#!/usr/bin/env python3
"""Multi-criteria decision framework for PQC KEM selection -- the paper's
novel contribution (advisor item #1, Option B). Entropy-weighted global
PQDRI index + AHP-weighted per-scenario TOPSIS rankings + a crossover /
sensitivity analysis that quantifies exactly when an alternative overtakes
the default. Every input traces to the paper's verified tables; nothing is
tuned to a desired ranking. See revisions/07-mcdm-framework.md.

    python3 mcdm.py
"""
import numpy as np

# ---- Decision matrix: the four families at NIST category 1 ----
# columns: pk(B), ct(B), keygen(us), online=enc+dec(us), impl_maturity(1-5), math_confidence(1-5)
FAMILIES = ["ML-KEM-512", "ntruhps2048677", "HQC-1", "mceliece348864"]
CRITERIA = ["pk", "ct", "keygen", "online", "impl_mat", "math_conf"]
COST = np.array([True, True, True, True, False, False])  # True = minimise
LATTICE = np.array([True, True, False, False])           # False = code-based (the non-lattice hedge)

X = np.array([
    # pk,      ct,      keygen,   online,   impl, math
    [   800,    768,     7.087,   17.272,     5,    4],   # ML-KEM-512
    [   930,    930,    55.766,   19.401,     4,    4],   # ntruhps2048677
    [  2241,   4433,    20.000,  120.000,     3,    4],   # HQC-1 (official AVX2 CPU)
    [261120,     96, 33009.539,  137.462,     2,    5],   # mceliece348864
], dtype=float)

# Scenario priority vectors (justified by what recurs vs amortises).
# Static-key zeroes pk and keygen: paid once, out of band / offline.
SCENARIOS = {
    "Ephemeral TLS":      [7, 7, 8, 6, 8, 4],
    "Static-key VPN":     [0, 9, 0, 4, 5, 8],
    "Constrained device": [8, 8, 7, 7, 7, 4],
}


def entropy_weights(M):
    P = M / M.sum(axis=0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        terms = np.where(P > 0, P * np.log(P), 0.0)
    e = -terms.sum(axis=0) / np.log(M.shape[0])
    d = 1.0 - e
    return d / d.sum()


def ahp_weights(priority):
    p = np.asarray(priority, float)
    return p / p.sum()


def topsis(M, w, cost):
    """TOPSIS closeness scores for the rows of M; higher = better."""
    R = M / np.sqrt((M ** 2).sum(axis=0))
    V = R * w
    best = np.where(cost, V.min(axis=0), V.max(axis=0))
    worst = np.where(cost, V.max(axis=0), V.min(axis=0))
    d_best = np.sqrt(((V - best) ** 2).sum(axis=1))
    d_worst = np.sqrt(((V - worst) ** 2).sum(axis=1))
    return d_worst / (d_best + d_worst)


def show(scores, names, indent="    "):
    for i in np.argsort(-scores):
        print(f"{indent}{names[i]:16s} {scores[i]:.3f}")


def main():
    print("=== Decision matrix (NIST category 1) ===")
    print(f"{'family':16s}" + "".join(f"{c:>11}" for c in CRITERIA))
    for i, f in enumerate(FAMILIES):
        print(f"{f:16s}" + "".join(f"{X[i, j]:>11.1f}" for j in range(len(CRITERIA))))

    # ---- Global PQDRI (objective, entropy weights) ----
    ew = entropy_weights(X)
    print("\n=== Entropy weights (objective) ===")
    print("  " + "   ".join(f"{c}={w:.3f}" for c, w in zip(CRITERIA, ew)))
    print("=== Global PQDRI ranking ===")
    show(topsis(X, ew, COST), FAMILIES, indent="  ")

    # ---- Scenario rankings (AHP weights) ----
    print("\n=== Scenario rankings (AHP weights) ===")
    for name, pri in SCENARIOS.items():
        w = ahp_weights(pri)
        print(f"\n{name}:  " + " ".join(f"{c}={wi:.2f}" for c, wi in zip(CRITERIA, w)))
        show(topsis(X, w, COST), FAMILIES)

    # ---- Assumption diversity as a NON-LATTICE FILTER ----
    print("\n=== Assumption-diversity hedge: non-lattice families only ===")
    idx = np.where(~LATTICE)[0]
    sub_names = [FAMILIES[i] for i in idx]
    sub = X[idx]
    for label, pri in (("general deployability (ephemeral wts)", SCENARIOS["Ephemeral TLS"]),
                       ("static-key (bandwidth wts)", SCENARIOS["Static-key VPN"])):
        print(f"  among code-based, {label}:")
        show(topsis(sub, ahp_weights(pri), COST), sub_names, indent="      ")

    # ---- Static-key crossover: how far must maturity be discounted for McEliece to lead? ----
    print("\n=== Static-key crossover (ct=9, online=4, math=8 fixed; sweep impl_mat weight) ===")
    mce = FAMILIES.index("mceliece348864")
    crossover = None
    for impl in np.arange(5.0, -0.01, -0.5):
        pri = [0, 9, 0, 4, impl, 8]
        s = topsis(X, ahp_weights(pri), COST)
        leader = FAMILIES[int(np.argmax(s))]
        w_impl = ahp_weights(pri)[4]
        tag = "  <-- McEliece overtakes" if int(np.argmax(s)) == mce and crossover is None else ""
        if int(np.argmax(s)) == mce and crossover is None:
            crossover = (impl, w_impl)
        print(f"  impl_priority={impl:.1f} (weight {w_impl:.2f}): leader {leader}{tag}")
    if crossover:
        print(f"  => McEliece leads static-key only once impl-maturity weight drops to <= {crossover[1]:.2f}")
    else:
        print("  => McEliece never leads static-key in this sweep (maturity cost dominates)")

    # ---- Sensitivity: leader stability under +/-25% one-at-a-time ----
    print("\n=== Sensitivity: leader stability under +/-25% one-at-a-time ===")
    for name, pri in SCENARIOS.items():
        w = ahp_weights(pri); s = topsis(X, w, COST); top0 = int(np.argmax(s)); flips = total = 0
        for j in range(len(CRITERIA)):
            for delta in (0.75, 1.25):
                wp = w.copy(); wp[j] *= delta; wp /= wp.sum()
                flips += int(np.argmax(topsis(X, wp, COST)) != top0); total += 1
        print(f"  {name:22s} leader {FAMILIES[top0]:16s} rank-flips {flips}/{total}")


if __name__ == "__main__":
    main()
