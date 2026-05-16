# linkedin/pipeline/job_pool.py
"""Job-signal discovery: hiring keyword → companies → buyer personas.

The pool is just a discovery loop:
- Take the next unused ``Campaign.job_keywords`` entry.
- Search LinkedIn Jobs for that keyword to get companies.
- For each company, walk ``Campaign.persona_keywords`` and enrich the
  matching /in/ profiles.

Every enriched Lead is stamped source="job_signal" by
``discover_and_enrich``. Qualification still flows through the shared
qualify pool — this module's job is purely to fill the Lead table with
job-signal candidates.
"""
from __future__ import annotations

import logging

from linkedin.actions.job_search import discover_people_at_company, search_jobs

logger = logging.getLogger(__name__)


def run_job_discovery(session, max_keywords: int = 1) -> int:
    """Run one tick of job-signal discovery for the active campaign.

    Returns the number of companies processed. Does nothing if the
    campaign has no ``job_keywords`` or ``persona_keywords`` configured.
    """
    campaign = session.campaign
    job_keywords: list[str] = list(campaign.job_keywords or [])
    persona_keywords: list[str] = list(campaign.persona_keywords or [])

    if not job_keywords or not persona_keywords:
        return 0

    processed = 0
    for kw in job_keywords[:max_keywords]:
        companies = search_jobs(session, kw)
        for company_url in companies:
            discover_people_at_company(session, company_url, persona_keywords, kw)
            processed += 1
            session.wait()
    return processed
