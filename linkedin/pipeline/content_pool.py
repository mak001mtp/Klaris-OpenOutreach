# linkedin/pipeline/content_pool.py
"""Post-signal discovery: content keywords → post authors.

One tick consumes one ``Campaign.content_keywords`` entry, searches
LinkedIn content, and enriches every post-author profile. Each new Lead
is stamped source="post_signal" via ``discover_and_enrich``.
"""
from __future__ import annotations

import logging

from linkedin.actions.content_search import search_content

logger = logging.getLogger(__name__)


def run_content_discovery(session, max_keywords: int = 1) -> int:
    """Run one tick of post-signal discovery for the active campaign.

    Returns the number of keywords searched. Does nothing if the campaign
    has no ``content_keywords`` configured.
    """
    campaign = session.campaign
    keywords: list[str] = list(campaign.content_keywords or [])
    if not keywords:
        return 0

    searched = 0
    for kw in keywords[:max_keywords]:
        search_content(session, kw)
        searched += 1
        session.wait()
    return searched
