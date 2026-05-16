import logging

from django.db import transaction
from termcolor import colored

from linkedin.enums import ProfileState

logger = logging.getLogger(__name__)


def _existing_deal_or_lead(public_id: str, campaign):
    """Check for an existing Deal in campaign; if none, look up the Lead.

    Returns (lead, existing_deal) — exactly one will be non-None,
    or both None if no Lead exists at all.
    """
    from crm.models import Deal, Lead

    existing = Deal.objects.filter(lead__public_identifier=public_id, campaign=campaign).first()
    if existing:
        return None, existing
    lead = Lead.objects.filter(public_identifier=public_id).first()
    return lead, None


# ── Deal creation ──


@transaction.atomic
def create_disqualified_deal(session, public_id: str, reason: str = ""):
    """Create a FAILED Deal with 'Disqualified' closing reason for an LLM-rejected lead.

    LLM qualification rejections are tracked as FAILED Deals (campaign-scoped),
    NOT as Lead.disqualified (which is for permanent account-level exclusion).
    """
    from crm.models import Outcome

    campaign = session.campaign
    lead, existing = _existing_deal_or_lead(public_id, campaign)
    if existing:
        return existing
    if not lead:
        logger.warning("create_disqualified_deal: no Lead for %s", public_id)
        return None

    deal = _create_deal(
        lead=lead,
        state=ProfileState.FAILED,
        session=session,
        outcome=Outcome.WRONG_FIT,
        reason=reason,
    )

    suffix = f" ({reason})" if reason else ""
    logger.info("%s %s%s", public_id, colored("DISQUALIFIED", "red", attrs=["bold"]), suffix)
    return deal


def _create_deal(
    *, lead, state, session,
    outcome="", reason="",
):
    """Shared Deal creation with common defaults.

    Funnel attribution: read the latest LeadDiscovery for this Lead and
    stamp its ``source`` onto the Deal so disqualified/freemium rows are
    attributable too.
    """
    from crm.models import Deal, Source

    latest = lead.discoveries.order_by("-discovered_at").first()
    source = latest.source if latest else Source.PEOPLE_SEARCH

    return Deal.objects.create(
        lead=lead,
        campaign=session.campaign,
        state=state,
        source=source,
        outcome=outcome,
        reason=reason,
    )
