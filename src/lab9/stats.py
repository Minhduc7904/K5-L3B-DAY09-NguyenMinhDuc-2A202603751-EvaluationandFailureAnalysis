"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

POS = "FAIL"


def _check_nck(n: int, c: int, k: int) -> None:
    """pass@k / pass^k are only defined for integers 1 <= k <= n and 0 <= c <= n."""
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (n, c, k)):
        raise ValueError(f"n, c, k must be integers, got {n!r}, {c!r}, {k!r}")
    if n < 1 or k < 1 or k > n or c < 0 or c > n:
        raise ValueError(f"need 1 <= k <= n and 0 <= c <= n, got n={n}, c={c}, k={k}")   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError(f"length mismatch: {len(human)} human vs {len(judge)} judge labels")
    bad = {x for x in (*human, *judge) if x not in (POS, "PASS")}
    if bad:
        # a typo ("fail", "FAIL ", None) must not silently count as PASS and bend every metric
        raise ValueError(f"labels must be 'PASS' or 'FAIL', got {sorted(map(repr, bad))}")
    tp = fp = fn = tn = 0
    for h, j in zip(human, judge):
        h_pos, j_pos = h == POS, j == POS
        if h_pos and j_pos:
            tp += 1
        elif j_pos:
            fp += 1
        elif h_pos:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    precision = cm["tp"] / (cm["tp"] + cm["fp"]) if cm["tp"] + cm["fp"] else 0.0
    recall = cm["tp"] / (cm["tp"] + cm["fn"]) if cm["tp"] + cm["fn"] else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    cm = confusion(human, judge)
    n = sum(cm.values())
    if n == 0:
        raise ValueError("kappa undefined: no labels")
    p_o = (cm["tp"] + cm["tn"]) / n
    # chance agreement from the two raters' marginal FAIL / PASS rates
    h_fail, j_fail = (cm["tp"] + cm["fn"]) / n, (cm["tp"] + cm["fp"]) / n
    p_e = h_fail * j_fail + (1 - h_fail) * (1 - j_fail)
    if p_e >= 1.0:
        raise ValueError("kappa undefined: both raters are constant (p_e == 1)")
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1.0
    if denom <= 0:
        # Youden's J <= 0: the judge is no better than a coin, so its rate cannot be corrected.
        raise ValueError(f"cannot correct: sensitivity + specificity - 1 = {denom:.3f} <= 0")
    return min(1.0, max(0.0, (observed_rate + specificity - 1.0) / denom))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy import stats as sps

    if len(a) != len(b):
        raise ValueError(f"paired samples need equal length, got {len(a)} and {len(b)}")
    if len(a) < 2:
        raise ValueError("paired bootstrap needs at least 2 items")
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if np.array_equal(x, y):
        return (0.0, 0.0, 0.0)          # nothing to resample: identical runs have a zero-width CI at 0
    res = sps.bootstrap((x, y), lambda u, v, axis: np.mean(u, axis=axis) - np.mean(v, axis=axis),
                        paired=True, vectorized=True, n_resamples=n_resamples, confidence_level=confidence,
                        method="percentile", rng=np.random.default_rng(rng))
    return (float(np.mean(x) - np.mean(y)), float(res.confidence_interval.low), float(res.confidence_interval.high))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    _check_nck(n, c, k)
    if n - c < k:                       # fewer than k failures: every draw of k contains a pass
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    _check_nck(n, c, k)
    return math.comb(c, k) / math.comb(n, k)    # comb(c, k) = 0 when c < k
