"""LeadDiscovery → Deal.source attribution path.

Whichever funnel last surfaced a lead must stamp the resulting Deal.
"""
import pytest

from crm.models import Deal, Lead, LeadDiscovery, Source
from linkedin.db.deals import _create_deal, create_disqualified_deal
from linkedin.db.leads import promote_lead_to_deal
from linkedin.enums import ProfileState
from tests.factories import LeadFactory


@pytest.fixture
def lead(db):
    return LeadFactory()


@pytest.fixture
def session(db, lead, mocker):
    from linkedin.models import Campaign
    campaign = Campaign.objects.create(name="t")
    return mocker.Mock(campaign=campaign)


class TestPromoteLeadToDeal:
    def test_stamps_latest_discovery_source(self, db, session, lead):
        LeadDiscovery.objects.create(lead=lead, source=Source.PEOPLE_SEARCH)
        LeadDiscovery.objects.create(lead=lead, source=Source.JOB_SIGNAL)

        deal = promote_lead_to_deal(session, lead.public_identifier)

        assert deal.source == Source.JOB_SIGNAL

    def test_defaults_to_people_search_when_no_discovery(self, db, session, lead):
        deal = promote_lead_to_deal(session, lead.public_identifier)

        assert deal.source == Source.PEOPLE_SEARCH

    def test_post_signal_attribution(self, db, session, lead):
        LeadDiscovery.objects.create(lead=lead, source=Source.JOB_SIGNAL)
        LeadDiscovery.objects.create(lead=lead, source=Source.POST_SIGNAL)

        deal = promote_lead_to_deal(session, lead.public_identifier)

        assert deal.source == Source.POST_SIGNAL


class TestCreateDisqualifiedDeal:
    def test_stamps_source_on_failed_deal(self, db, session, lead):
        LeadDiscovery.objects.create(lead=lead, source=Source.POST_SIGNAL)

        deal = create_disqualified_deal(session, lead.public_identifier, reason="bad fit")

        assert deal.state == ProfileState.FAILED
        assert deal.source == Source.POST_SIGNAL
