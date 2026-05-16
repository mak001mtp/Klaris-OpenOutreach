# linkedin/tasks/qualify.py
"""Qualify-only task handler.

One QUALIFY task per campaign drives the full pipeline:
  1. People-search discovery (the existing search keyword pool).
  2. Job-signal discovery (Campaign.job_keywords → companies → personas).
  3. Post-signal discovery (Campaign.content_keywords → post authors).
  4. Drain ``qualify_source`` — the shared LLM/Bayesian qualifier that
     promotes Leads into Deals with whichever funnel surfaced them.

There is no connect, check_pending, or follow_up. Qualification produces
a QUALIFIED or FAILED Deal and stops.
"""
from __future__ import annotations

import logging

from termcolor import colored

from linkedin.conf import CAMPAIGN_CONFIG
from linkedin.pipeline.content_pool import run_content_discovery
from linkedin.pipeline.job_pool import run_job_discovery
from linkedin.pipeline.pools import qualify_source

logger = logging.getLogger(__name__)


def handle_qualify(task, session, qualifiers):
    """Run one round of discovery + qualification, then self-reschedule."""
    from linkedin.tasks.scheduler import enqueue_qualify

    campaign = session.campaign
    qualifier = qualifiers.get(campaign.pk)

    logger.info("[%s] %s", campaign, colored("▶ qualify", "cyan", attrs=["bold"]))

    # Discovery: walk all three funnels. Each populates Leads (people,
    # job_signal, post_signal). Source attribution lives on LeadDiscovery.
    try:
        job_count = run_job_discovery(session)
        if job_count:
            logger.info("[%s] job-signal: processed %d companies", campaign, job_count)
    except Exception:
        logger.exception("[%s] job-signal discovery failed", campaign)

    try:
        content_count = run_content_discovery(session)
        if content_count:
            logger.info("[%s] post-signal: searched %d keywords", campaign, content_count)
    except Exception:
        logger.exception("[%s] post-signal discovery failed", campaign)

    # Drain the shared qualifier. ``qualify_source`` pulls from the
    # people-search keyword pool when its internal pool is empty, so all
    # three funnels feed the same LLM qualification step.
    qualified = 0
    for _public_id in qualify_source(session, qualifier):
        qualified += 1
    logger.info("[%s] qualified %d new leads this tick", campaign, qualified)

    enqueue_qualify(
        campaign.pk,
        delay_seconds=CAMPAIGN_CONFIG["connect_no_candidate_delay_seconds"],
    )
