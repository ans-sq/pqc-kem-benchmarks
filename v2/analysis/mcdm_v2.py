#!/usr/bin/env python3
"""Selection framework, revision 2 (review items P0-1, P0-2, Section XI notes).

What changed relative to bench/mcdm.py:
  * CPU criteria come from the controlled, single-harness campaign (fixed
    1.7 GHz clock), for two implementation choices: liboqs 0.16.0 as released,
    and the best available code (official AVX2 HQC, McEliece AVX2 at -O3);
  * the two security criteria are encoded from independently checkable
    indicators (rubric below), with the original expert scores kept as one
    alternative encoding, and ablations that drop them;
  * robustness battery: four normalizations, leave-one-criterion-out,
    rank reversal under removal of an alternative, criterion correlations,
    and weights sampled from the flat Dirichlet distribution on the simplex;
  * the static-key contradiction is resolved by a Pareto/feasibility
    analysis instead of a single compromise score.

    python3 -I mcdm_v2.py <cpu_csv_dir> > ../data/mcdm_v2.txt   (also writes mcdm_v2.json)
"""
import glob
import itertools
import json
import os
import sys

import numpy as np
from scipy.stats import spearmanr

FAM = ["ML-KEM", "NTRU", "HQC", "McEliece"]
SETS = {"ML-KEM": "ML-KEM-512", "NTRU": "ntruhps2048677", "HQC": "HQC-1",
        "McEliece": "mceliece348864"}
PK = np.array([800, 930, 2241, 261120], float)
CT = np.array([768, 930, 4433, 96], float)
LATTICE = np.array([True, True, False, False])

# ---- Security indicators (1 = met). Every cell is a checkable fact. ----
# Implementation maturity
IM_IND = {
    "final standard (FIPS 203 / ISO/IEC 18033-2 Amd 2)": [1, 0, 0, 1],
    "default key exchange in Chrome/Firefox/OpenSSH":     [1, 0, 0, 0],
    "SIMD implementation in liboqs 0.16.0":               [1, 1, 0, 1],
    "liboqs 0.16.0: no secret-dependent branching claimed": [1, 1, 1, 0],
    "liboqs 0.16.0: constant-time checked with Valgrind":   [1, 1, 0, 0],
}
# Family-level reading of the deployment indicator: NTRU Prime (sntrup761)
# was the OpenSSH default 2022-2025; strict reading counts only the
# evaluated NTRU-HPS/HRSS sets.
IM_FAMILY_NTRU_BONUS = np.array([0, 1, 0, 0])
# Mathematical confidence (historical scrutiny / reductions / concrete estimates)
MC_IND = {
    "assumption introduced before 2000 (Goppa SD 1978, NTRU 1998)": [0, 1, 0, 1],
    "worst-case to average-case reduction (Module-LWE)":                           [1, 0, 0, 0],
    "no official statement that security falls short of claims (NIST IR 8545 fn. 5; BSI 2026)": [1, 1, 1, 0],
}
IM_ENC = {
    "expert (v1 rubric)": np.array([5, 4, 3, 2], float),
    "indicators, strict": np.array([sum(c) for c in zip(*IM_IND.values())], float),
}
IM_ENC["indicators, family"] = IM_ENC["indicators, strict"] + IM_FAMILY_NTRU_BONUS
MC_ENC = {
    "expert (v1 rubric)": np.array([4, 4, 4, 5], float),
    "indicators": np.array([sum(c) for c in zip(*MC_IND.values())], float),
}

CRIT = ["pk", "ct", "keygen", "online", "impl", "math"]
COST = np.array([1, 1, 1, 1, 0, 0], bool)
SCEN = {  # priority points per criterion (normalized to weights); unchanged from v1
    "Ephemeral TLS":      [7, 7, 8, 6, 8, 4],
    "Static-key":         [0, 9, 0, 4, 5, 8],
    "Constrained device": [8, 8, 7, 7, 7, 4],
}


def load_cpu(d):
    """Median over repetitions of the per-run median time (us)."""
    rows = []
    for f in glob.glob(os.path.join(d, "cpu_*_r*.csv")):
        for line in open(f):
            if line.startswith(("#", "label")):
                continue
            lab, impl, scheme, op, n, med = line.split(",")[:6]
            rows.append((lab.rsplit("_r", 1)[0], impl, scheme, op, float(med)))
    agg = {}
    for build, impl, scheme, op, med in rows:
        agg.setdefault((build, impl, scheme, op), []).append(med)
    return {k: float(np.median(v)) for k, v in agg.items()}


def cpu_columns(cpu, choice):
    g = lambda b, i, s, o: cpu[(b, i, s, o)]
    kg, on = [], []
    picks = {
        "liboqs 0.16.0 as released": [("016", "liboqs", "ML-KEM-512"), ("016", "liboqs", "NTRU-HPS-2048-677"),
                                      ("016", "liboqs", "HQC-1"), ("016", "liboqs", "Classic-McEliece-348864")],
        "best available code":       [("016", "liboqs", "ML-KEM-512"), ("016", "liboqs", "NTRU-HPS-2048-677"),
                                      ("016", "official-avx2", "HQC-1"), ("016O3", "liboqs", "Classic-McEliece-348864")],
    }[choice]
    for b, i, s in picks:
        kg.append(g(b, i, s, "keygen"))
        on.append(g(b, i, s, "encaps") + g(b, i, s, "decaps"))
    return np.array(kg), np.array(on)


def matrix(kg, on, im, mc, keep=None):
    X = np.column_stack([PK, CT, kg, on, im, mc])
    idx = list(range(6)) if keep is None else keep
    return X[:, idx], COST[idx], [CRIT[i] for i in idx]


def normalize(X, cost, how):
    X = X.astype(float)
    if how == "vector":
        return X / np.sqrt((X ** 2).sum(0))
    if how == "max":
        return X / X.max(0)
    if how == "minmax":
        rng = X.max(0) - X.min(0)
        rng[rng == 0] = 1
        return (X - X.min(0)) / rng
    if how == "log-vector":  # log10 for the cost criteria spanning orders of magnitude
        Y = X.copy()
        Y[:, cost] = np.log10(Y[:, cost])
        return Y / np.sqrt((Y ** 2).sum(0))
    raise ValueError(how)


def topsis(X, w, cost, how="vector"):
    R = normalize(X, cost, how)
    V = R * w
    best = np.where(cost, V.min(0), V.max(0))
    worst = np.where(cost, V.max(0), V.min(0))
    dp = np.sqrt(((V - best) ** 2).sum(1))
    dn = np.sqrt(((V - worst) ** 2).sum(1))
    return dn / (dp + dn)


def entropy_w(X):
    P = X / X.sum(0)
    with np.errstate(divide="ignore", invalid="ignore"):
        e = -np.where(P > 0, P * np.log(P), 0).sum(0) / np.log(X.shape[0])
    d = 1 - e
    return d / d.sum()


def ranks(s):
    r = np.empty(len(s), int)
    r[np.argsort(-s)] = np.arange(1, len(s) + 1)
    return r


def pareto(X, cost):
    """Indices of non-dominated alternatives."""
    Y = np.where(cost, X, -X)
    nd = []
    for i in range(len(Y)):
        dom = any(np.all(Y[j] <= Y[i]) and np.any(Y[j] < Y[i]) for j in range(len(Y)) if j != i)
        if not dom:
            nd.append(i)
    return nd


def fmt(s, names=FAM):
    return "  ".join(f"{n}={v:.3f}({r})" for n, v, r in zip(names, s, ranks(s)))


def main():
    d = sys.argv[1]
    cpu = load_cpu(d)
    out = {"indicators": {"impl": IM_IND, "math": MC_IND},
           "encodings": {"impl": {k: v.tolist() for k, v in IM_ENC.items()},
                         "math": {k: v.tolist() for k, v in MC_ENC.items()}}}
    print("== Security indicator rubric (1 = met)")
    for name, tab in (("Implementation maturity", IM_IND), ("Mathematical confidence", MC_IND)):
        print(f"  {name}:")
        for k, v in tab.items():
            print(f"    {k:85s} {v}")
    for k, v in IM_ENC.items():
        print(f"  impl encoding {k:22s} {v}")
    for k, v in MC_ENC.items():
        print(f"  math encoding {k:22s} {v}")

    for choice in ("best available code", "liboqs 0.16.0 as released"):
        kg, on = cpu_columns(cpu, choice)
        res = out.setdefault(choice, {})
        print(f"\n######## CPU inputs: {choice}")
        print(f"  keygen us {np.round(kg, 1)}   online(enc+dec) us {np.round(on, 1)}")
        base_im, base_mc = IM_ENC["indicators, strict"], MC_ENC["indicators"]
        X, cost, names = matrix(kg, on, base_im, base_mc)
        ew = entropy_w(X)
        res["raw_matrix"] = X.tolist()
        res["normalized_vector"] = normalize(X, cost, "vector").tolist()
        res["entropy_weights"] = dict(zip(names, ew.round(4).tolist()))
        print("  raw matrix rows (pk, ct, keygen, online, impl, math):")
        for f, row in zip(FAM, X):
            print(f"    {f:9s} {row}")
        print("  vector-normalized:")
        for f, row in zip(FAM, normalize(X, cost, "vector")):
            print(f"    {f:9s} {np.round(row, 4)}")
        print(f"  entropy weights: {res['entropy_weights']}")

        # 1. encodings x ablations under entropy weights (global index)
        print("\n  [1] Global entropy-weighted TOPSIS under every security encoding / ablation")
        enc_res = {}
        variants = [(f"impl={a} | math={b}", IM_ENC[a], MC_ENC[b], None)
                    for a, b in itertools.product(IM_ENC, MC_ENC)]
        variants += [("ablate math", base_im, base_mc, [0, 1, 2, 3, 4]),
                     ("ablate impl", base_im, base_mc, [0, 1, 2, 3, 5]),
                     ("ablate both security criteria", base_im, base_mc, [0, 1, 2, 3])]
        for lab, im, mc, keep in variants:
            Xv, cv, nv = matrix(kg, on, im, mc, keep)
            s = topsis(Xv, entropy_w(Xv), cv)
            enc_res[lab] = s.round(4).tolist()
            print(f"    {lab:55s} {fmt(s)}")
        res["global_by_encoding"] = enc_res

        # 2. normalizations, global + scenarios
        print("\n  [2] Normalization sensitivity (indicator encodings)")
        norm_res = {}
        for how in ("vector", "max", "minmax", "log-vector"):
            line = {}
            s = topsis(X, entropy_w(X), cost, how)
            line["PQDRI"] = s.round(4).tolist()
            txt = [f"PQDRI: {fmt(s)}"]
            for sc, pri in SCEN.items():
                w = np.array(pri, float) / sum(pri)
                s = topsis(X, w, cost, how)
                line[sc] = s.round(4).tolist()
                txt.append(f"{sc}: {fmt(s)}")
            norm_res[how] = line
            print(f"    -- {how}")
            for t in txt:
                print(f"       {t}")
        res["normalization"] = norm_res

        # 3. scenario weights + leader stability
        print("\n  [3] Scenario weights (normalized) and rankings (vector normalization)")
        sc_res = {}
        for sc, pri in SCEN.items():
            w = np.array(pri, float) / sum(pri)
            s = topsis(X, w, cost)
            flips = 0
            for j in range(6):
                for f in (0.75, 1.25):
                    wp = w.copy(); wp[j] *= f; wp /= wp.sum()
                    flips += int(np.argmax(topsis(X, wp, cost)) != np.argmax(s))
            sc_res[sc] = dict(weights=dict(zip(CRIT, w.round(3).tolist())), scores=s.round(4).tolist(),
                              leader_flips_pm25=f"{flips}/12")
            print(f"    {sc:20s} w={np.round(w, 3)}  {fmt(s)}  flips(+-25%)={flips}/12")
        res["scenarios"] = sc_res

        # 4. leave-one-criterion-out (global)
        print("\n  [4] Leave-one-criterion-out (entropy weights recomputed)")
        loo = {}
        for j in range(6):
            keep = [i for i in range(6) if i != j]
            Xv, cv, nv = X[:, keep], cost[keep], [CRIT[i] for i in keep]
            s = topsis(Xv, entropy_w(Xv), cv)
            loo[CRIT[j]] = s.round(4).tolist()
            print(f"    without {CRIT[j]:7s} {fmt(s)}")
        res["leave_one_out"] = loo

        # 5. rank reversal: remove one alternative, check order of the rest
        print("\n  [5] Rank reversal under removal of one alternative (global, entropy re-derived)")
        full_order = list(np.argsort(-topsis(X, ew, cost)))
        rr = {}
        for k in range(4):
            keep = [i for i in range(4) if i != k]
            s = topsis(X[keep], entropy_w(X[keep]), cost)
            order = [keep[i] for i in np.argsort(-s)]
            expected = [i for i in full_order if i != k]
            rr[FAM[k]] = dict(order=[FAM[i] for i in order], reversal=order != expected)
            print(f"    drop {FAM[k]:9s} -> {' > '.join(FAM[i] for i in order)}"
                  f"{'   RANK REVERSAL' if order != expected else ''}")
        res["rank_reversal"] = rr

        # 6. criterion correlations
        sp = spearmanr(X).correlation
        res["spearman_4alt"] = np.round(sp, 3).tolist()
        print("\n  [6] Spearman correlation between criteria across the four families")
        print("       " + " ".join(f"{c:>7s}" for c in CRIT))
        for c, row in zip(CRIT, sp):
            print(f"    {c:7s}" + " ".join(f"{v:7.2f}" for v in row))

        # 7. weights sampled from the flat Dirichlet distribution
        print("\n  [7] 20,000 weight vectors sampled from the flat Dirichlet (uniform simplex)")
        mc_res = {}
        for lab, im, mc, keep in variants:
            Xv, cv, nv = matrix(kg, on, im, mc, keep)
            rng = np.random.default_rng(20260615)
            W = rng.dirichlet(np.ones(Xv.shape[1]), 20000)
            wins = np.zeros(4, int)
            for w in W:
                wins[np.argmax(topsis(Xv, w, cv))] += 1
            mc_res[lab] = (wins / len(W)).round(4).tolist()
            print(f"    {lab:55s} " + "  ".join(f"{f}={100 * v / len(W):.1f}%" for f, v in zip(FAM, wins)))
        res["dirichlet_rank1_share"] = mc_res

        # 8. Pareto / feasibility per scenario
        print("\n  [8] Pareto-optimal families on each scenario's criteria (weight > 0)")
        par = {}
        for sc, pri in SCEN.items():
            keep = [i for i in range(6) if pri[i] > 0]
            for lab, im, mc in (("indicators", base_im, base_mc),
                                ("expert", IM_ENC["expert (v1 rubric)"], MC_ENC["expert (v1 rubric)"])):
                Xv, cv, nv = matrix(kg, on, im, mc, keep)
                nd = pareto(Xv, cv)
                par[f"{sc} | {lab}"] = [FAM[i] for i in nd]
                print(f"    {sc:20s} [{lab:10s}] criteria {nv}: non-dominated = {[FAM[i] for i in nd]}")
        res["pareto"] = par
        print("\n  Feasibility filters:")
        print("    ephemeral TLS 1.3 key share <= 65,535 B -> feasible:",
              [f for f, p in zip(FAM, PK) if p <= 65535])
        print("    ciphertext budget B per message: feasible sets")
        fb = {}
        for B_ in (64, 96, 102, 256, 512, 768, 930, 1500, 4433):
            ok = [f for f, c in zip(FAM, CT) if c <= B_]
            fb[B_] = ok
            print(f"      B={B_:5d}: {ok}")
        res["ct_budget_feasible"] = fb
        print("    non-lattice filter (assumption diversity):")
        sub = np.where(~LATTICE)[0]
        for sc in ("Ephemeral TLS", "Static-key"):
            w = np.array(SCEN[sc], float) / sum(SCEN[sc])
            s = topsis(X[sub], w, cost)
            print(f"      {sc:15s} " + "  ".join(f"{FAM[i]}={v:.3f}" for i, v in zip(sub, s)))
            res.setdefault("nonlattice", {})[sc] = {FAM[i]: float(v) for i, v in zip(sub, s)}

    json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "mcdm_v2.json"), "w"),
              indent=1, default=str)


if __name__ == "__main__":
    main()
