# linkedin/actions/content_search.py
"""LinkedIn content (posts) discovery.

``search_content(keyword)`` navigates LinkedIn's content search results
and enriches every post author's /in/ profile. Each newly created Lead
is stamped with source="post_signal" so the funnel attribution survives
into qualification.

Content search returns post authors directly, so unlike the job funnel
this is a single-step pipeline — no per-company drill-down.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from linkedin.browser.nav import extract_in_urls, goto_page
from linkedin.db.leads import discover_and_enrich

logger = logging.getLogger(__name__)

CONTENT_SEARCH_URL = "https://www.linkedin.com/search/results/content/"


def search_content(session, keyword: str) -> int:
    """Search LinkedIn posts for ``keyword`` and enrich every author profile.

    Returns the number of /in/ URLs found on the results page (not the
    number of new Leads — ``discover_and_enrich`` dedupes against existing
    rows but still records a LeadDiscovery for attribution).
    """
    page = session.page
    params = urlencode({"keywords": keyword})
    goto_page(
        session,
        action=lambda: page.goto(f"{CONTENT_SEARCH_URL}?{params}"),
        expected_url_pattern="/search/results/content/",
        error_message="Failed to reach Content search results",
    )

    urls = extract_in_urls(page)
    logger.info("Content search %r → %d authors", keyword, len(urls))
    discover_and_enrich(session, urls, source="post_signal", keyword=keyword)
    return len(urls)
