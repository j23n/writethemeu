from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import LetterForm
from .models import (
    Constituency,
    IdentityVerification,
    Letter,
    Parliament,
    ParliamentTerm,
    Representative,
    Signature,
    Tag,
    TopicArea,
)
from .services import ConstituencySuggestionService, IdentityVerificationService


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


class LetterCreationTests(ParliamentFixtureMixin, TestCase):
    """Ensure primary author and signature flows remain intact."""

    def test_author_signature_created_with_letter(self):
        self.client.login(username='alice', password='password123')

        response = self.client.post(
            reverse('letter_create'),
            {
                'title': 'Improve Berlin public transit',
                'body': 'We need better U-Bahn coverage in Mitte.',
                'representative': self.direct_rep.pk,
                'tags': 'verkehr',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        letter = Letter.objects.get()
        self.assertEqual(letter.author, self.user)
        self.assertEqual(letter.representative, self.direct_rep)
        self.assertTrue(Signature.objects.filter(user=self.user, letter=letter).exists())


class LetterFormFilteringTests(ParliamentFixtureMixin, TestCase):
    """Profile-linked constituencies should surface relevant representatives."""

    def test_letter_form_filters_representatives_by_profile_constituencies(self):
        form = LetterForm(
            data={
                'title': 'Test letter',
                'body': 'Content',
                'representative': self.direct_rep.pk,
                'tags': '',
            },
            user=self.user,
        )

        queryset = list(form.fields['representative'].queryset)
        self.assertIn(self.direct_rep, queryset)
        self.assertIn(self.list_rep, queryset)


class IdentityVerificationTests(ParliamentFixtureMixin, TestCase):
    """Identity verifications should link back to the new constituency model."""

    def test_complete_verification_links_constituency(self):
        verification = IdentityVerificationService.complete_verification(
            self.user,
            {
                'provider': 'stub',
                'postal_code': '10115',
                'city': 'Berlin',
                'state': 'Berlin',
                'country': 'DE',
            },
        )

        self.assertIsNotNone(verification)
        self.assertEqual(verification.constituency, self.constituency_state)
        self.assertEqual(verification.federal_constituency, self.constituency_state)
        self.assertIsNone(verification.state_constituency)
        self.assertEqual(verification.parliament, self.parliament)
        self.assertEqual(verification.verification_type, 'THIRD_PARTY')
        self.assertTrue(verification.is_third_party)
        self.assertTrue(self.list_rep.qualifies_as_constituent(verification))

    def test_representative_constituent_matching(self):
        verification = IdentityVerification.objects.create(
            user=self.user,
            status='VERIFIED',
            postal_code='10115',
            city='Berlin',
            state='Berlin',
            country='DE',
            constituency=self.constituency_direct,
            federal_constituency=self.constituency_direct,
            verification_type='THIRD_PARTY',
            verified_at=timezone.now(),
        )

        self.assertTrue(self.direct_rep.qualifies_as_constituent(verification))
        self.assertTrue(self.list_rep.qualifies_as_constituent(verification))

    def test_self_declare_links_constituencies(self):
        verification = IdentityVerificationService.self_declare(
            self.user,
            federal_constituency=self.constituency_direct,
            state_constituency=self.state_constituency_direct,
        )

        self.assertEqual(verification.status, 'SELF_DECLARED')
        self.assertEqual(verification.verification_type, 'SELF_DECLARED')
        self.assertTrue(verification.is_self_declared)
        self.assertIn(self.constituency_direct, verification.get_constituencies())
        self.assertIn(self.state_constituency_direct, verification.get_constituencies())
        self.assertTrue(self.direct_rep.qualifies_as_constituent(verification))


class SuggestionServiceTests(ParliamentFixtureMixin, TestCase):
    """Validate recommendation logic for letter drafting."""

    def setUp(self):
        super().setUp()
        self.direct_rep.focus_areas = 'Verkehr, Infrastruktur'
        self.direct_rep.save()

        self.transport_topic = TopicArea.objects.create(
            name='Verkehrspolitik',
            slug='verkehrspolitik',
            description='ÖPNV, Busse und Bahnen',
            primary_level='STATE',
            competency_type='STATE',
            keywords='verkehr, nahverkehr, bus, bahn'
        )
        self.transport_tag = Tag.objects.create(name='Verkehr', slug='verkehr')
        self.uni_topic = TopicArea.objects.create(
            name='Hochschulpolitik',
            slug='hochschulpolitik',
            description='Universitäten, Hochschulen, Forschung',
            primary_level='STATE',
            competency_type='STATE',
            keywords='universität, universitäten, hochschule, hochschulen'
        )

    def test_suggestions_use_postal_code_and_keywords(self):
        result = ConstituencySuggestionService.suggest_from_concern(
            'Mehr Verkehr und ÖPNV in Berlin Mitte',
            user_location={'constituencies': [self.constituency_direct.id, self.constituency_state.id]}
        )

        self.assertIn(self.direct_rep, result['representatives'])
        self.assertEqual(result['representatives'][0], self.direct_rep)
        self.assertIn(self.transport_topic, result['matched_topics'])
        self.assertIn(self.transport_tag, result['suggested_tags'])
        self.assertIn('Berlin', result['explanation'])

        for rep in result['representatives']:
            if rep == self.direct_rep:
                self.assertEqual(rep.suggested_constituency, self.constituency_direct)

        direct_reps = result['direct_representatives']
        self.assertIn(self.direct_rep, direct_reps)
        self.assertIn(self.list_rep, direct_reps)
        self.assertNotIn(self.other_direct_rep, direct_reps)

    def test_state_topic_prefers_state_representatives(self):
        bavaria_parliament = Parliament.objects.create(
            name='Bayerischer Landtag',
            level='STATE',
            legislative_body='Landtag',
            region='Bayern',
            metadata={'source': 'test'},
        )
        bavaria_term = ParliamentTerm.objects.create(
            parliament=bavaria_parliament,
            name='19. Wahlperiode',
            start_date=date(2023, 10, 8),
            metadata={'source': 'test'},
        )
        bavaria_constituency = Constituency.objects.create(
            parliament_term=bavaria_term,
            name='München-Süd (Stimmkreis)',
            scope='STATE_DISTRICT',
            metadata={'state': 'Bayern'},
        )
        bavaria_list_constituency = Constituency.objects.create(
            parliament_term=bavaria_term,
            name='CSU Landesliste Bayern',
            scope='STATE_LIST',
            metadata={'state': 'Bayern'},
        )

        state_rep_direct = Representative.objects.create(
            parliament=bavaria_parliament,
            parliament_term=bavaria_term,
            election_mode='DIRECT',
            external_id='state-direct-1',
            first_name='Anna',
            last_name='Aigner',
            party='CSU',
            term_start=date(2023, 10, 8),
        )
        state_rep_direct.constituencies.add(bavaria_constituency)

        state_rep_list = Representative.objects.create(
            parliament=bavaria_parliament,
            parliament_term=bavaria_term,
            election_mode='STATE_LIST',
            external_id='state-list-1',
            first_name='Heinz',
            last_name='Huber',
            party='CSU',
            term_start=date(2023, 10, 8),
        )
        state_rep_list.constituencies.add(bavaria_list_constituency)

        self.uni_topic.representatives.add(state_rep_direct, state_rep_list)

        result = ConstituencySuggestionService.suggest_from_concern(
            'Universitäten sind richtig toll',
            user_location={'constituencies': [bavaria_constituency.id, bavaria_list_constituency.id]},
        )

        suggested_ids = {rep.id for rep in result['representatives']}
        self.assertIn(state_rep_direct.id, suggested_ids)
        self.assertIn(state_rep_list.id, suggested_ids)
        self.assertIn(self.uni_topic, result['matched_topics'])
        direct_ids = {rep.id for rep in result['direct_representatives']}
        self.assertEqual(direct_ids, {state_rep_direct.id, state_rep_list.id})
        self.assertNotIn(self.direct_rep.id, suggested_ids)
