# ABOUTME: Shared test fixtures for letters app tests
# ABOUTME: Provides ParliamentFixtureMixin with common test data setup

from datetime import date

from django.contrib.auth.models import User

from letters.models import (
    Constituency,
    Parliament,
    ParliamentTerm,
    Representative,
)


class ParliamentFixtureMixin:
    """Create a minimal Parliament/ParliamentTerm/Representative graph for tests."""

    def setUp(self):
        super().setUp()

        self.user = User.objects.create_user(
            username='alice',
            password='password123',
            email='alice@example.com',
        )
        self.other_user = User.objects.create_user(
            username='bob',
            password='password123',
            email='bob@example.com',
        )

        self.parliament = Parliament.objects.create(
            name='Deutscher Bundestag',
            level='FEDERAL',
            legislative_body='Bundestag',
            region='DE',
            metadata={'source': 'test'},
        )
        self.term = ParliamentTerm.objects.create(
            parliament=self.parliament,
            name='20. Wahlperiode',
            start_date=date(2021, 10, 26),
            metadata={'source': 'test'},
        )

        self.constituency_direct = Constituency.objects.create(
            parliament_term=self.term,
            name='Berlin-Mitte (WK 75)',
            scope='FEDERAL_DISTRICT',
            metadata={'state': 'Berlin'},
        )
        self.constituency_state = Constituency.objects.create(
            parliament_term=self.term,
            name='Landesliste Berlin',
            scope='FEDERAL_STATE_LIST',
            metadata={'state': 'Berlin'},
        )
        self.constituency_other = Constituency.objects.create(
            parliament_term=self.term,
            name='Berlin-Pankow (WK 76)',
            scope='FEDERAL_DISTRICT',
            metadata={'state': 'Berlin'},
        )
        self.constituency_hamburg_list = Constituency.objects.create(
            parliament_term=self.term,
            name='Landesliste Hamburg',
            scope='FEDERAL_STATE_LIST',
            metadata={'state': 'Hamburg'},
        )

        self.state_parliament = Parliament.objects.create(
            name='Bayerischer Landtag',
            level='STATE',
            legislative_body='Landtag',
            region='Bayern',
            metadata={'source': 'test'},
        )
        self.state_term = ParliamentTerm.objects.create(
            parliament=self.state_parliament,
            name='18. Wahlperiode',
            start_date=date(2018, 10, 14),
            metadata={'source': 'test'},
        )
        self.state_constituency_direct = Constituency.objects.create(
            parliament_term=self.state_term,
            name='München-Süd (Stimmkreis)',
            scope='STATE_DISTRICT',
            metadata={'state': 'Bayern'},
        )
        self.state_constituency_list = Constituency.objects.create(
            parliament_term=self.state_term,
            name='Bayern Landesliste',
            scope='STATE_LIST',
            metadata={'state': 'Bayern'},
        )

        self.state_rep_direct = Representative.objects.create(
            parliament=self.state_parliament,
            parliament_term=self.state_term,
            election_mode='DIRECT',
            external_id='state-direct-base',
            first_name='Sabine',
            last_name='Schmidt',
            party='CSU',
            term_start=date(2018, 10, 14),
        )
        self.state_rep_direct.constituencies.add(self.state_constituency_direct)

        self.state_rep_list = Representative.objects.create(
            parliament=self.state_parliament,
            parliament_term=self.state_term,
            election_mode='STATE_LIST',
            external_id='state-list-base',
            first_name='Thomas',
            last_name='Thal',
            party='CSU',
            term_start=date(2018, 10, 14),
        )
        self.state_rep_list.constituencies.add(self.state_constituency_list)

        self.direct_rep = Representative.objects.create(
            parliament=self.parliament,
            parliament_term=self.term,
            election_mode='DIRECT',
            external_id='rep-direct-1',
            first_name='Max',
            last_name='Mustermann',
            party='Independent',
            term_start=date(2021, 10, 26),
        )
        self.direct_rep.constituencies.add(self.constituency_direct)

        self.other_direct_rep = Representative.objects.create(
            parliament=self.parliament,
            parliament_term=self.term,
            election_mode='DIRECT',
            external_id='rep-direct-2',
            first_name='Fritz',
            last_name='Fischer',
            party='Independent',
            term_start=date(2021, 10, 26),
        )
        self.other_direct_rep.constituencies.add(self.constituency_other)

        self.list_rep = Representative.objects.create(
            parliament=self.parliament,
            parliament_term=self.term,
            election_mode='STATE_LIST',
            external_id='rep-list-1',
            first_name='Erika',
            last_name='Mustermann',
            party='Example Party',
            term_start=date(2021, 10, 26),
        )
        self.list_rep.constituencies.add(self.constituency_state)

        self.federal_expert_rep = Representative.objects.create(
            parliament=self.parliament,
            parliament_term=self.term,
            election_mode='STATE_LIST',
            external_id='rep-expert-1',
            first_name='Sarah',
            last_name='Schneider',
            party='SPD',
            term_start=date(2021, 10, 26),
        )
        self.federal_expert_rep.constituencies.add(self.constituency_hamburg_list)
