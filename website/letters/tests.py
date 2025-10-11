from datetime import date

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from pathlib import Path
from tempfile import TemporaryDirectory

from .forms import LetterForm
from .models import (
    Committee,
    CommitteeMembership,
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
from .services import ConstituencySuggestionService, IdentityVerificationService, RepresentativeSyncService
from .templatetags import markdown_extras


class AccountRegistrationTests(TestCase):
    """Ensure registration uses double opt-in and activation flow works."""

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_registration_requires_email_confirmation(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newbie',
                'email': 'newbie@example.com',
                'first_name': 'New',
                'last_name': 'User',
                'password1': 'SupersafePassword123',
                'password2': 'SupersafePassword123',
            },
            follow=True,
        )

        self.assertRedirects(response, reverse('registration_pending'))
        self.assertTemplateUsed(response, 'letters/account_activation_sent.html')

        user = User.objects.get(username='newbie')
        self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 1)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        activation_response = self.client.get(
            reverse('activate_account', args=[uid, token]),
            follow=True,
        )

        self.assertRedirects(activation_response, reverse('login'))
        user.refresh_from_db()
        self.assertTrue(user.is_active)


class AccountDeletionTests(TestCase):
    """Deleting an account removes signatures but keeps authored letters."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username='deleteme',
            password='password123',
            email='deleteme@example.com',
        )

        self.other_user = User.objects.create_user(
            username='other',
            password='password123',
            email='other@example.com',
        )

        self.parliament = Parliament.objects.create(
            name='Bundestag',
            level='FEDERAL',
            legislative_body='Bundestag',
            region='DE',
        )
        self.term = ParliamentTerm.objects.create(
            parliament=self.parliament,
            name='20. Wahlperiode',
        )
        self.constituency = Constituency.objects.create(
            parliament_term=self.term,
            name='Berlin-Mitte',
            scope='FEDERAL_DISTRICT',
        )
        self.representative = Representative.objects.create(
            parliament=self.parliament,
            parliament_term=self.term,
            election_mode='DIRECT',
            external_id='rep-del-test',
            first_name='Alex',
            last_name='Muster',
            party='Partei',
        )
        self.representative.constituencies.add(self.constituency)

        self.letter = Letter.objects.create(
            title='Keep parks clean',
            body='Please invest in clean parks.',
            author=self.user,
            representative=self.representative,
        )
        Signature.objects.create(user=self.user, letter=self.letter)
        Signature.objects.create(user=self.other_user, letter=self.letter)

    def test_account_deletion_preserves_letters_and_removes_signatures(self):
        self.client.login(username='deleteme', password='password123')

        response = self.client.post(reverse('delete_account'), follow=True)

        self.assertRedirects(response, reverse('letter_list'))
        self.assertFalse(User.objects.filter(username='deleteme').exists())

        letter = Letter.objects.get(pk=self.letter.pk)
        self.assertIsNone(letter.author)
        self.assertFalse(Signature.objects.filter(user__username='deleteme').exists())
        # Other signatures should remain intact
        self.assertTrue(Signature.objects.filter(user__username='other', letter=letter).exists())


class PasswordResetFlowTests(TestCase):
    """Users can request a password reset and set a new password via the emailed token."""

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(
            username='resetuser',
            password='OldPassword123',
            email='reset@example.com',
        )

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_password_reset_email_and_confirm(self):
        response = self.client.post(
            reverse('password_reset'),
            {'email': 'reset@example.com'},
            follow=True,
        )

        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertTemplateUsed(response, 'letters/password_reset_done.html')
        self.assertEqual(len(mail.outbox), 1)

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)

        reset_confirm_url = reverse('password_reset_confirm', args=[uid, token])

        # Django requires a GET request first which redirects to a set-password URL
        get_response = self.client.get(reset_confirm_url, follow=True)

        # Extract the actual set-password URL from the redirect
        set_password_url = get_response.redirect_chain[-1][0]

        # Now POST the new password to the set-password URL
        response = self.client.post(
            set_password_url,
            {'new_password1': 'NewPassword456', 'new_password2': 'NewPassword456'},
            follow=True,
        )

        self.assertRedirects(response, reverse('password_reset_complete'))
        self.assertTemplateUsed(response, 'letters/password_reset_complete.html')

        login_success = self.client.login(username='resetuser', password='NewPassword456')
        self.assertTrue(login_success)


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
        self.uni_topic.representatives.add(self.direct_rep)
        self.social_topic = TopicArea.objects.create(
            name='Sozialversicherung',
            slug='sozialversicherung',
            description='Gesetzliche Sozialversicherung, Rente, Pflege, Krankenversicherung',
            primary_level='FEDERAL',
            competency_type='EXCLUSIVE',
            keywords='sozialversicherung, rente, pflegeversicherung'
        )

        self.federal_committee = Committee.objects.create(
            name='Ausschuss für Arbeit und Soziales',
            parliament_term=self.term,
        )
        self.federal_committee.topic_areas.add(self.social_topic)
        CommitteeMembership.objects.create(
            representative=self.federal_expert_rep,
            committee=self.federal_committee,
            role='member'
        )
        self.federal_expert_rep.topic_areas.add(self.social_topic)

        self.state_committee = Committee.objects.create(
            name='Wissenschaftsausschuss',
            parliament_term=self.state_term,
        )
        self.state_committee.topic_areas.add(self.uni_topic)
        CommitteeMembership.objects.create(
            representative=self.state_rep_list,
            committee=self.state_committee,
            role='member'
        )
        self.state_rep_list.topic_areas.add(self.uni_topic)

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
        self.assertNotIn(self.list_rep, direct_reps)  # list_rep is STATE_LIST, not DIRECT
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

        other_state_parliament = Parliament.objects.create(
            name='Landtag Nordrhein-Westfalen',
            level='STATE',
            legislative_body='Landtag NRW',
            region='Nordrhein-Westfalen',
            metadata={'source': 'test'},
        )
        other_state_term = ParliamentTerm.objects.create(
            parliament=other_state_parliament,
            name='18. Wahlperiode NRW',
            start_date=date(2022, 5, 31),
            metadata={'source': 'test'},
        )
        other_state_constituency = Constituency.objects.create(
            parliament_term=other_state_term,
            name='Düsseldorf II',
            scope='STATE_DISTRICT',
            metadata={'state': 'Nordrhein-Westfalen'},
        )
        other_state_list_constituency = Constituency.objects.create(
            parliament_term=other_state_term,
            name='Landesliste NRW',
            scope='STATE_LIST',
            metadata={'state': 'Nordrhein-Westfalen'},
        )
        other_state_direct = Representative.objects.create(
            parliament=other_state_parliament,
            parliament_term=other_state_term,
            election_mode='DIRECT',
            external_id='state-direct-nrw',
            first_name='Klara',
            last_name='Kruse',
            party='SPD',
            term_start=date(2022, 5, 31),
        )
        other_state_direct.constituencies.add(other_state_constituency)
        other_state_list = Representative.objects.create(
            parliament=other_state_parliament,
            parliament_term=other_state_term,
            election_mode='STATE_LIST',
            external_id='state-list-nrw',
            first_name='Lars',
            last_name='Lemke',
            party='CDU',
            term_start=date(2022, 5, 31),
        )
        other_state_list.constituencies.add(other_state_list_constituency)

        self.uni_topic.representatives.add(
            state_rep_direct,
            state_rep_list,
            other_state_direct,
            other_state_list,
        )

        result = ConstituencySuggestionService.suggest_from_concern(
            'Universitäten sind richtig toll',
            user_location={
                'constituencies': [
                    bavaria_constituency.id,
                    bavaria_list_constituency.id,
                    other_state_constituency.id,
                ],
                'state': 'Bayern',
            },
        )

        suggested_ids = {rep.id for rep in result['representatives']}
        self.assertIn(state_rep_direct.id, suggested_ids)
        self.assertIn(state_rep_list.id, suggested_ids)
        self.assertIn(self.uni_topic, result['matched_topics'])
        direct_ids = {rep.id for rep in result['direct_representatives']}
        self.assertEqual(direct_ids, {state_rep_direct.id})  # Only DIRECT election mode
        self.assertNotIn(self.direct_rep.id, suggested_ids)
        self.assertNotIn(other_state_direct.id, suggested_ids)
        self.assertNotIn(other_state_list.id, suggested_ids)
        expert_ids = {rep.id for rep in result['expert_representatives']}
        self.assertNotIn(self.direct_rep.id, expert_ids)

    def test_federal_topic_prefers_federal_representatives(self):
        self.social_topic.representatives.add(self.direct_rep, self.list_rep)

        result = ConstituencySuggestionService.suggest_from_concern(
            'Sozialversicherung reformieren',
            user_location={'constituencies': [self.constituency_direct.id, self.constituency_state.id]},
        )

        suggested_ids = {rep.id for rep in result['representatives']}
        self.assertIn(self.direct_rep.id, suggested_ids)
        self.assertIn(self.list_rep.id, suggested_ids)
        self.assertIn(self.social_topic, result['matched_topics'])
        direct_ids = {rep.id for rep in result['direct_representatives']}
        self.assertEqual(direct_ids, {self.direct_rep.id})  # Only DIRECT election mode
        self.assertNotIn(self.state_rep_direct.id, suggested_ids)
        self.assertNotIn(self.state_rep_list.id, suggested_ids)
        expert_ids = {rep.id for rep in result['expert_representatives']}
        self.assertIn(self.federal_expert_rep.id, expert_ids)
        self.assertNotIn(self.state_rep_direct.id, expert_ids)

    def test_federal_topic_view_endpoint_filters_state_reps(self):
        self.social_topic.representatives.add(self.direct_rep, self.list_rep)
        IdentityVerificationService.self_declare(
            self.user,
            federal_constituency=self.constituency_direct,
            state_constituency=self.state_constituency_direct,
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('analyze_title'),
            {'title': 'Sozialversicherung reformieren'},
            HTTP_HX_REQUEST='true'
        )

        content = response.content.decode('utf-8')
        self.assertIn(self.direct_rep.last_name, content)
        self.assertIn(self.list_rep.last_name, content)
        self.assertNotIn(self.state_rep_direct.last_name, content)
        self.assertNotIn(self.state_rep_list.last_name, content)
        self.assertIn(self.federal_expert_rep.last_name, content)


class CompetencyPageTests(TestCase):
    """Ensure the competency overview renders topics for visitors."""

    def setUp(self):
        TopicArea.objects.all().delete()
        self.topic = TopicArea.objects.create(
            name='Testthema',
            slug='testthema',
            description='Ein Beispielthema für die Kompetenzseite.',
            primary_level='FEDERAL',
            competency_type='EXCLUSIVE',
            keywords='test, thema',
            legal_basis='Art. 73 GG',
            legal_basis_url='https://www.gesetze-im-internet.de/gg/art_73.html',
        )

    def test_competency_page_renders(self):
        response = self.client.get(reverse('competency_overview'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kompetenzen verstehen')
        self.assertContains(response, self.topic.name)


class MarkdownFilterTests(TestCase):
    """Ensure Markdown rendering converts safely and strips disallowed markup."""

    def test_markdown_bold_rendering(self):
        rendered = markdown_extras.markdownify('**Hallo Welt**')
        self.assertIn('<strong>Hallo Welt</strong>', rendered)

    def test_markdown_strips_scripts(self):
        rendered = markdown_extras.markdownify('Test <script>alert(1)</script>')
        self.assertIn('Test', rendered)
        self.assertNotIn('<script>', rendered)

    def test_markdown_ordered_list(self):
        rendered = markdown_extras.markdownify('1. Eins\n2. Zwei')
        self.assertIn('<ol', rendered)
        self.assertIn('<li>Eins</li>', rendered)
        self.assertIn('<li>Zwei</li>', rendered)


class GeocodeCacheTests(TestCase):
    """Test geocoding cache model."""

    def test_cache_stores_and_retrieves_coordinates(self):
        from .models import GeocodeCache

        cache_entry = GeocodeCache.objects.create(
            address_hash='test_hash_123',
            street='Unter den Linden 77',
            postal_code='10117',
            city='Berlin',
            latitude=52.5170365,
            longitude=13.3888599,
        )

        retrieved = GeocodeCache.objects.get(address_hash='test_hash_123')
        self.assertEqual(retrieved.latitude, 52.5170365)
        self.assertEqual(retrieved.longitude, 13.3888599)
        self.assertEqual(retrieved.street, 'Unter den Linden 77')


class AddressGeocoderTests(TestCase):
    """Test the AddressGeocoder service with OSM Nominatim API."""

    def test_successful_geocoding_with_mocked_api(self):
        """Test successful geocoding with mocked Nominatim API response."""
        from unittest.mock import patch, Mock
        from .services import AddressGeocoder

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'lat': '52.5200066',
                'lon': '13.404954',
                'display_name': 'Berlin, Germany'
            }
        ]

        with patch('requests.get', return_value=mock_response) as mock_get:
            geocoder = AddressGeocoder()
            lat, lon, success, error = geocoder.geocode(
                street='Unter den Linden 77',
                postal_code='10117',
                city='Berlin'
            )

            self.assertTrue(success)
            self.assertIsNone(error)
            self.assertAlmostEqual(lat, 52.5200066, places=6)
            self.assertAlmostEqual(lon, 13.404954, places=6)

            # Verify the request was made correctly
            mock_get.assert_called_once()
            call_args = mock_get.call_args
            self.assertIn('nominatim.openstreetmap.org', call_args[0][0])
            self.assertEqual(call_args[1]['headers']['User-Agent'], 'WriteThem.eu/0.1 (civic engagement platform)')

    def test_cache_hit_no_api_call(self):
        """Test that cache hits don't make API calls."""
        from unittest.mock import patch
        from .models import GeocodeCache
        from .services import AddressGeocoder
        import hashlib

        # Create a cache entry
        address_string = 'Unter den Linden 77|10117|Berlin|DE'
        address_hash = hashlib.sha256(address_string.encode('utf-8')).hexdigest()

        GeocodeCache.objects.create(
            address_hash=address_hash,
            street='Unter den Linden 77',
            postal_code='10117',
            city='Berlin',
            country='DE',
            latitude=52.5200066,
            longitude=13.404954,
            success=True
        )

        with patch('requests.get') as mock_get:
            geocoder = AddressGeocoder()
            lat, lon, success, error = geocoder.geocode(
                street='Unter den Linden 77',
                postal_code='10117',
                city='Berlin'
            )

            self.assertTrue(success)
            self.assertIsNone(error)
            self.assertAlmostEqual(lat, 52.5200066, places=6)
            self.assertAlmostEqual(lon, 13.404954, places=6)

            # Verify NO API call was made
            mock_get.assert_not_called()

    def test_failed_geocoding_cached(self):
        """Test that failed geocoding attempts are cached."""
        from unittest.mock import patch, Mock
        from .models import GeocodeCache
        from .services import AddressGeocoder

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = []  # Empty result = not found

        with patch('requests.get', return_value=mock_response):
            geocoder = AddressGeocoder()
            lat, lon, success, error = geocoder.geocode(
                street='Nonexistent Street 999',
                postal_code='99999',
                city='Nowhere'
            )

            self.assertFalse(success)
            self.assertIsNotNone(error)
            self.assertIsNone(lat)
            self.assertIsNone(lon)

            # Verify the failure was cached
            import hashlib
            address_string = 'Nonexistent Street 999|99999|Nowhere|DE'
            address_hash = hashlib.sha256(address_string.encode('utf-8')).hexdigest()

            cache_entry = GeocodeCache.objects.get(address_hash=address_hash)
            self.assertFalse(cache_entry.success)
            self.assertEqual(cache_entry.error_message, error)

    def test_api_error_handling(self):
        """Test that API errors are handled gracefully."""
        from unittest.mock import patch
        from .services import AddressGeocoder
        import requests

        with patch('requests.get', side_effect=requests.RequestException('API Error')):
            geocoder = AddressGeocoder()
            lat, lon, success, error = geocoder.geocode(
                street='Test Street',
                postal_code='12345',
                city='Test City'
            )

            self.assertFalse(success)
            self.assertIsNotNone(error)
            self.assertIsNone(lat)
            self.assertIsNone(lon)
            self.assertIn('API Error', error)


class RepresentativeMetadataExtractionTests(TestCase):

    def setUp(self):
        self.service = RepresentativeSyncService(dry_run=True)

    def test_extract_biography_prefers_profile(self):
        politician = {
            'profile': {'short_description': '<p>Kurzvita</p>'},
            'description': 'Langtext'
        }
        bio = self.service._extract_biography(politician)
        self.assertEqual(bio, 'Kurzvita')

    def test_extract_focus_topics_merges_sources(self):
        politician = {
            'politician_topics': [{'label': 'Bildung'}, {'topic': {'label': 'Forschung'}}],
            'activity': {'topics': [{'label': 'Forschung'}, {'label': 'Kultur'}]}
        }
        topics = self.service._extract_focus_topics(politician)
        self.assertTrue({'Bildung', 'Forschung', 'Kultur'}.issubset(set(topics)))

    def test_extract_links_filters_empty_entries(self):
        politician = {
            'links': [
                {'label': 'Website', 'url': 'https://example.org'},
                {'type': 'Twitter', 'url': 'https://twitter.com/example'},
                {'label': 'Ohne URL'}
            ]
        }
        links = self.service._extract_links(politician)
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0]['label'], 'Website')

    def test_ensure_photo_reference_sets_existing_path(self):
        with TemporaryDirectory() as tmp:
            with override_settings(MEDIA_ROOT=tmp, MEDIA_URL='/media/'):
                service = RepresentativeSyncService(dry_run=True)
                parliament = Parliament.objects.create(
                    name='Testparlament',
                    level='FEDERAL',
                    legislative_body='Bundestag',
                    region='DE'
                )
                term = ParliamentTerm.objects.create(
                    parliament=parliament,
                    name='Testperiode',
                    start_date=date(2024, 1, 1)
                )
                rep = Representative.objects.create(
                    parliament=parliament,
                    parliament_term=term,
                    election_mode='DIRECT',
                    external_id='999',
                    first_name='Test',
                    last_name='Person',
                    is_active=True
                )
                media_dir = Path(tmp) / 'representatives'
                media_dir.mkdir(parents=True, exist_ok=True)
                (media_dir / '999.jpg').write_bytes(b'fake')

                service._ensure_photo_reference(rep)
                rep.refresh_from_db()
                self.assertEqual(rep.photo_path, 'representatives/999.jpg')


class GeoJSONDataTests(TestCase):
    """Test that official Bundestag constituency GeoJSON data is available and valid."""

    def test_geojson_file_exists(self):
        """Verify the wahlkreise.geojson file exists in the data directory."""
        from pathlib import Path
        from django.conf import settings

        geojson_path = Path(settings.BASE_DIR) / 'letters' / 'data' / 'wahlkreise.geojson'
        self.assertTrue(geojson_path.exists(), f"GeoJSON file not found at {geojson_path}")

    def test_geojson_is_valid_and_loadable(self):
        """Verify the GeoJSON file is valid JSON and has expected structure."""
        import json
        from pathlib import Path
        from django.conf import settings

        geojson_path = Path(settings.BASE_DIR) / 'letters' / 'data' / 'wahlkreise.geojson'

        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertEqual(data['type'], 'FeatureCollection')
        self.assertIn('features', data)
        self.assertIsInstance(data['features'], list)

    def test_geojson_contains_all_constituencies(self):
        """Verify the GeoJSON contains all 299 Bundestag constituencies."""
        import json
        from pathlib import Path
        from django.conf import settings

        geojson_path = Path(settings.BASE_DIR) / 'letters' / 'data' / 'wahlkreise.geojson'

        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertEqual(len(data['features']), 299)

    def test_geojson_features_have_required_properties(self):
        """Verify each feature has required properties: WKR_NR, WKR_NAME, LAND_NR, LAND_NAME."""
        import json
        from pathlib import Path
        from django.conf import settings

        geojson_path = Path(settings.BASE_DIR) / 'letters' / 'data' / 'wahlkreise.geojson'

        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Check first feature
        if len(data['features']) > 0:
            feature = data['features'][0]
            self.assertEqual(feature['type'], 'Feature')
            self.assertIn('properties', feature)
            self.assertIn('geometry', feature)

            properties = feature['properties']
            self.assertIn('WKR_NR', properties)
            self.assertIn('WKR_NAME', properties)
            self.assertIn('LAND_NR', properties)
            self.assertIn('LAND_NAME', properties)

            # Verify geometry type
            self.assertEqual(feature['geometry']['type'], 'Polygon')

    def test_geojson_constituency_numbers_complete(self):
        """Verify constituency numbers range from 1 to 299 with no gaps."""
        import json
        from pathlib import Path
        from django.conf import settings

        geojson_path = Path(settings.BASE_DIR) / 'letters' / 'data' / 'wahlkreise.geojson'

        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        wkr_numbers = [f['properties']['WKR_NR'] for f in data['features']]
        expected_numbers = set(range(1, 300))
        actual_numbers = set(wkr_numbers)

        self.assertEqual(actual_numbers, expected_numbers, "Constituency numbers should be 1-299 with no gaps")
