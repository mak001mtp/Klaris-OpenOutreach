# linkedin/actions/job_search.py
"""LinkedIn Jobs discovery.

Two-step funnel:

1. ``search_jobs(keyword)`` — navigate Jobs search for a hiring keyword
   (e.g. "Customer Success Operations"), extract the set of companies
   posting matching jobs.
2. ``discover_people_at_companies(companies, persona_keywords)`` — for
   each company, run People search filtered to the company with the
   campaign's persona keywords (e.g. "VP Customer Success") and enrich
   the resulting /in/ profiles. Each new Lead is stamped with
   source="job_signal" via ``discover_and_enrich``.

Selectors are best-effort against LinkedIn's current DOM; the helpers
log and skip rather than crash when LinkedIn moves things.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode, urljoin, urlparse

from linkedin.browser.nav import extract_in_urls, goto_page
from linkedin.db.leads import discover_and_enrich

logger = logging.getLogger(__name__)

JOBS_SEARCH_URL = "https://www.linkedin.com/jobs/search/"
PEOPLE_SEARCH_URL = "https://www.linkedin.com/search/results/people/"

_COMPANY_LINK_SELECTOR = 'a[href*="/company/"]'


def _company_url_from_href(page_url: str, href: str) -> str | None:
    """Normalize a /company/<slug>/... href to its canonical company URL."""
    if not href:
        return None
    full = urljoin(page_url, href.split("?")[0].rstrip("/"))
    parsed = urlparse(full)
    parts = [p for p in parsed.path.split("/") if p]
    # Expect ['company', '<slug>', ...]
    if len(parts) < 2 or parts[0] != "company":
        return None
    return f"https://www.linkedin.com/company/{parts[1]}/"


def search_jobs(session, keyword: str) -> list[str]:
    """Return canonical company URLs hiring for ``keyword``.

    LinkedIn's Jobs search DOM changes frequently, so rather than walk
    job cards we scrape every ``/company/<slug>`` link on the page and
    dedupe — every job card always contains one.
    """
    session.ensure_browser()
    page = session.page
    params = urlencode({"keywords": keyword})
    goto_page(
        session,
        action=lambda: page.goto(f"{JOBS_SEARCH_URL}?{params}", wait_until="domcontentloaded"),
        expected_url_pattern="/jobs/search/",
        error_message="Failed to reach Jobs search results",
    )

    # Let the results panel hydrate.
    session.wait()

    companies: list[str] = []
    seen: set[str] = set()
    for link in page.locator(_COMPANY_LINK_SELECTOR).all():
        href = link.get_attribute("href")
        company_url = _company_url_from_href(page.url, href or "")
        if company_url and company_url not in seen:
            seen.add(company_url)
            companies.append(company_url)

    logger.info("Jobs search %r → %d companies", keyword, len(companies))
    return companies


def discover_people_at_company(
    session,
    company_url: str,
    persona_keywords: list[str],
    job_keyword: str,
) -> int:
    """Run People search for each persona keyword filtered to the company.

    Returns the number of /in/ URLs enriched across all personas.
    """
    session.ensure_browser()
    page = session.page
    company_slug = urlparse(company_url).path.strip("/").split("/")[-1]

    enriched_total = 0
    for persona in persona_keywords:
        # LinkedIn supports `currentCompany=<slug>` and also `company=<name>`
        # but the slug form is more stable. Fall back to keyword-only search
        # if LinkedIn requires the resolved companyId.
        params = urlencode({
            "keywords": f"{persona} {company_slug}",
            "origin": "GLOBAL_SEARCH_HEADER",
        })
        try:
            goto_page(
                session,
                action=lambda: page.goto(f"{PEOPLE_SEARCH_URL}?{params}"),
                expected_url_pattern="/search/results/",
                error_message=f"Failed company-persona search ({persona} @ {company_slug})",
            )
        except RuntimeError as exc:
            logger.warning("Skipping persona %r at %s: %s", persona, company_slug, exc)
            continue

        urls = extract_in_urls(page)
        before = enriched_total
        # We don't have a clean count from discover_and_enrich; just call it.
        discover_and_enrich(
            session, urls,
            source="job_signal",
            keyword=f"{job_keyword} | {persona} @ {company_slug}",
        )
        enriched_total = before + len(urls)
    return enriched_total
