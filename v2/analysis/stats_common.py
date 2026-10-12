"""Shared statistics for the revision analyses.

Pre-registered choices (fixed before the revision campaigns were run,
2026-10-12): medians with 95% percentile-bootstrap CIs (20,000 resamples,
seed 20260615); between-cell differences of medians with 90% and 95%
bootstrap CIs (independent resampling of each sample); equivalence of a
post-quantum configuration to its classical baseline is declared when the
90% CI of the median difference lies inside +/- EQUIV_MARGIN_MS (the
confidence-interval form of two one-sided tests at alpha = 0.05);
two-sided Mann-Whitney U and Cliff's delta for location differences.
"""
import numpy as np
from scipy.stats import mannwhitneyu

B = 20000
SEED = 20260615
EQUIV_MARGIN_MS = 1.0


def _rng():
    return np.random.default_rng(SEED)


def median_ci(x, level=0.95):
    x = np.asarray(x, float)
    idx = _rng().integers(0, len(x), size=(B, len(x)))
    meds = np.median(x[idx], axis=1)
    a = (1 - level) / 2
    return float(np.median(x)), float(np.quantile(meds, a)), float(np.quantile(meds, 1 - a))


def diff_median_ci(x, y, levels=(0.90, 0.95)):
    """Median(x) - median(y) with bootstrap CIs at each level."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    rng = _rng()
    mx = np.median(x[rng.integers(0, len(x), size=(B, len(x)))], axis=1)
    my = np.median(y[rng.integers(0, len(y), size=(B, len(y)))], axis=1)
    d = mx - my
    out = {"diff": float(np.median(x) - np.median(y))}
    for lv in levels:
        a = (1 - lv) / 2
        out[f"ci{int(lv * 100)}"] = (float(np.quantile(d, a)), float(np.quantile(d, 1 - a)))
    return out


def cliffs_delta(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    gt = (x[:, None] > y[None, :]).sum()
    lt = (x[:, None] < y[None, :]).sum()
    return float((gt - lt) / (len(x) * len(y)))


def compare(x, y, margin=EQUIV_MARGIN_MS):
    """x = candidate, y = baseline (same units as margin)."""
    d = diff_median_ci(x, y)
    lo90, hi90 = d["ci90"]
    p = float(mannwhitneyu(x, y, alternative="two-sided").pvalue)
    return dict(diff=d["diff"], ci90_lo=lo90, ci90_hi=hi90, ci95_lo=d["ci95"][0],
                ci95_hi=d["ci95"][1], equivalent=bool(-margin < lo90 and hi90 < margin),
                mwu_p=p, cliffs_delta=cliffs_delta(x, y))


def quantiles(x, qs=(0.5, 0.9, 0.95, 0.99)):
    x = np.asarray(x, float)
    return [float(np.quantile(x, q)) for q in qs]
