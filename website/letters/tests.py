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
                'postal_code': '10115',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        letter = Letter.objects.get()
        self.assertEqual(letter.author, self.user)
        self.assertEqual(letter.representative, self.direct_rep)
        self.assertTrue(Signature.objects.filter(user=self.user, letter=letter).exists())


class LetterFormFilteringTests(ParliamentFixtureMixin, TestCase):
    """Postal code filtering should surface relevant representatives."""

    def test_letter_form_filters_representatives_by_postal_code(self):
        form = LetterForm(
            data={
                'title': 'Test letter',
                'body': 'Content',
                'representative': self.direct_rep.pk,
                'postal_code': '10115',
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
        self.assertEqual(verification.parliament, self.parliament)
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
            verified_at=timezone.now(),
        )

        self.assertTrue(self.direct_rep.qualifies_as_constituent(verification))
        self.assertTrue(self.list_rep.qualifies_as_constituent(verification))


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

    def test_suggestions_use_postal_code_and_keywords(self):
        result = ConstituencySuggestionService.suggest_from_concern(
            'Mehr Verkehr und ÖPNV in Berlin Mitte',
            user_location={'postal_code': '10115'}
        )

        self.assertIn(self.direct_rep, result['representatives'])
        self.assertEqual(result['representatives'][0], self.direct_rep)
        self.assertIn(self.transport_topic, result['matched_topics'])
        self.assertIn(self.transport_tag, result['suggested_tags'])
        self.assertIn('Berlin', result['explanation'])

        for rep in result['representatives']:
            if rep == self.direct_rep:
                self.assertEqual(rep.suggested_constituency, self.constituency_direct)
