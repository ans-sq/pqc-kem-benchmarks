#!/usr/bin/env python3
"""Robustness of the global PQDRI ranking to the CHOICE OF WEIGHTING METHOD
(reviewer concern: an entropy-weighted index could be dismissed as 'just
another weighted score'). We re-rank the four families under several weighting
schemes and under a Monte-Carlo ensemble of weights drawn uniformly from the
simplex. If the order is invariant to how the weights are picked, the ranking
is a property of the data, not of the weights.
"""
import numpy as np
from mcdm import X, COST, CRITERIA, FAMILIES, entropy_weights, ahp_weights, topsis

RNG = np.random.default_rng(20260615)


def ranks(scores):
    order = np.argsort(-scores)
    r = np.empty(len(scores), int)
    for pos, i in enumerate(order):
        r[i] = pos + 1
    return r


print("=== Global ranking under different weighting METHODS ===")
methods = {
    "Entropy (objective)":        entropy_weights(X),
    "Equal (1/6 each)":           np.full(len(CRITERIA), 1 / len(CRITERIA)),
    "AHP balanced (deployer)":    ahp_weights([5, 5, 5, 5, 5, 5]),
    "AHP CPU+maturity-first":     ahp_weights([3, 3, 5, 5, 6, 5]),
    "AHP bandwidth-first":        ahp_weights([8, 8, 3, 3, 3, 3]),
}
print(f"{'method':28s} " + "  ".join(f"{f.split('-')[0][:7]:>8s}" for f in FAMILIES))
for name, w in methods.items():
    s = topsis(X, w, COST)
    r = ranks(s)
    print(f"{name:28s} " + "  ".join(f"{s[i]:.2f}({r[i]})" for i in range(len(FAMILIES))))

print("\n=== Monte-Carlo over the weight simplex (Dirichlet(1,...,1)) ===")
N = 20000
win = np.zeros(len(FAMILIES), int)
order_counts = {}
for _ in range(N):
    w = RNG.dirichlet(np.ones(len(CRITERIA)))
    s = topsis(X, w, COST)
    win[int(np.argmax(s))] += 1
    key = tuple(np.argsort(-s))
    order_counts[key] = order_counts.get(key, 0) + 1
print(f"  N={N} random weightings; rank-1 frequency:")
for i in np.argsort(-win):
    print(f"    {FAMILIES[i]:16s} {100*win[i]/N:5.1f}%")
print("  most common full orderings:")
for key, c in sorted(order_counts.items(), key=lambda kv: -kv[1])[:3]:
    print(f"    {100*c/N:5.1f}%  " + " > ".join(FAMILIES[i].split('-')[0] for i in key))
