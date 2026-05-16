# linkedin/pipeline/pools.py
"""People-search pool: search → enrich → qualify.

Two generators chain via next(upstream, None):

    qualify_source  <- pulls from search_source
     (keeps searching until P > 0.5 candidates exist in exploit mode)
                            |
                  search_source  <- yields keywords (never truly exhausts)

Each qualify_source iteration produces exactly one label, which shifts the
GP model — preventing the infinite-search-without-qualifying bug. The
job_pool and content_pool funnels enrich Leads directly (without going
through ``search_source``), but still feed the same ``qualify_source``
loop downstream because qualification is shared across all three funnels.
"""
from __future__ import annotations

import logging
from typing import Generator

import numpy as np

from linkedin.conf import CAMPAIGN_CONFIG
from linkedin.ml.qualifier import BayesianQualifier
from linkedin.pipeline.qualify import fetch_qualification_candidates, run_qualification
from linkedin.pipeline.search import run_search

logger = logging.getLogger(__name__)


def _needs_search(qualifier: BayesianQualifier, candidates) -> bool:
    """True only in exploit mode when no candidate meets the adaptive threshold.

    Effective threshold = max(0, base - 1/sqrt(n_obs)).
    Stays at zero until ~1/base² observations, then gradually rises
    toward base — favoring qualification over search early on.

    Returns False on cold start, explore mode, or empty candidates.
    """
    if not candidates:
        return False

    n_neg, n_pos = qualifier.class_counts
    if n_neg <= n_pos:
        # explore mode — no need to search for high-P profiles
        return False

    embeddings = np.array([c.embedding_array for c in candidates], dtype=np.float32)
    probs = qualifier.predict_probs(embeddings)
    if probs is None:
        # cold start
        return False

    # If the GP can't differentiate profiles (all predictions identical),
    # searching won't help — qualify from existing pool to build up labels.
    if len(probs) > 1 and np.ptp(probs) < 1e-6:
        logger.debug(
            "GP predictions degenerate (all ~%.3f) with %d obs — "
            "skipping search, qualifying from existing pool",
            float(probs[0]), qualifier.n_obs,
        )
        return False

    base = CAMPAIGN_CONFIG["min_positive_pool_prob"]
    n = qualifier.n_obs
    threshold = max(0.0, base - 1 / np.sqrt(n)) if n > 0 else 0.0
    if bool(np.any(probs >= threshold)):
        return False

    logger.info(
        "Pool (%d unlabeled) has no P >= %.3f in exploit mode "
        "(neg=%d, pos=%d, n_obs=%d, base=%.2f). "
        "P distribution: min=%.3f, p25=%.3f, median=%.3f, p75=%.3f, max=%.3f",
        len(candidates), threshold, n_neg, n_pos, n, base,
        float(np.min(probs)), float(np.percentile(probs, 25)),
        float(np.median(probs)), float(np.percentile(probs, 75)),
        float(np.max(probs)),
    )
    return True


def search_source(session) -> Generator[str, None, None]:
    """Yield keywords from run_search(). Stops when run_search returns None."""
    while True:
        keyword = run_search(session)
        if keyword is None:
            return
        yield keyword


def qualify_source(session, qualifier: BayesianQualifier) -> Generator[str, None, None]:
    """Yield public_ids from run_qualification(), pulling from search when needed.

    In exploit mode, the effective pool is candidates with P > 0.5. When
    this pool is empty, keeps searching until high-P candidates appear or
    search is exhausted. Every yield produces a label that shifts the GP
    model. Only falls through to qualifying low-P candidates when search
    can no longer bring in new profiles.
    """
    search = search_source(session)

    while True:
        candidates = fetch_qualification_candidates(session)

        # If no candidates at all, search to bring some in
        if not candidates:
            if next(search, None) is None:
                return
            candidates = fetch_qualification_candidates(session)
            if not candidates:
                return

        # In exploit mode with no P > 0.5 candidates, keep searching
        # until the positive pool is non-empty or search is exhausted.
        while _needs_search(qualifier, candidates):
            if next(search, None) is None:
                break
            candidates = fetch_qualification_candidates(session)

        result = run_qualification(session, qualifier)
        if result is None:
            return
        yield result


