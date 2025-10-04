import io
import tempfile
import zipfile
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.core.management import call_command
from django.core.management.base import CommandError

from .models import (
    Constituency,
    IdentityVerification,
    Letter,
    Representative,
    Report,
    Signature,
)
from .services import AddressConstituencyMapper, IdentityVerificationService


class LetterTestBase(TestCase):
    """Common fixtures for letter-related tests."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='alice',
            password='password123',
            email='alice@example.com'
        )
        self.other_user = User.objects.create_user(
            username='bob',
            password='password123',
            email='bob@example.com'
        )

        self.federal_root = Constituency.objects.create(
            name='Deutscher Bundestag',
            level='FEDERAL',
            legislative_body='Deutscher Bundestag',
            legislative_period_start=date(2021, 10, 26),
            region='DE',
            metadata={'scope': 'national'}
        )

        self.state_constituency = Constituency.objects.create(
            name='Berlin',
            level='STATE',
            legislative_body='Abgeordnetenhaus Berlin',
            legislative_period_start=date(2021, 10, 26),
            region='Berlin',
            parent_constituency=self.federal_root,
            metadata={
                'state': 'Berlin',
                'state_code': 'BE',
                'postal_code_prefixes': ['10', '11']
            }
        )

        self.local_constituency = Constituency.objects.create(
            name='Berlin-Mitte',
            level='LOCAL',
            legislative_body='Bezirksverordnetenversammlung Berlin-Mitte',
            legislative_period_start=date(2021, 10, 26),
            region='10115',
            parent_constituency=self.state_constituency,
            metadata={
                'state': 'Berlin',
                'state_code': 'BE',
                'cities': ['berlin', 'berlin-mitte'],
                'postal_code_prefixes': ['10115', '1011', '101']
            }
        )

        self.constituency = Constituency.objects.create(
            name='Berlin Mitte (Wahlkreis 75)',
            level='FEDERAL',
            legislative_body='Deutscher Bundestag',
            legislative_period_start=date(2021, 10, 26),
            region='DE-BE-75',
            parent_constituency=self.federal_root,
            metadata={
                'state': 'Berlin',
                'state_code': 'BE',
                'wahlkreis_number': '75'
            }
        )

        self.representative = Representative.objects.create(
            constituency=self.constituency,
            first_name='Max',
            last_name='Mustermann',
            party='Independent',
            term_start=date(2021, 10, 26)
        )


class LetterCreationTests(LetterTestBase):
    """Ensure authorship actions trigger expected side effects."""

    def test_author_signature_created_with_letter(self):
        self.client.login(username='alice', password='password123')

        response = self.client.post(
            reverse('letter_create'),
            {
                'title': 'Improve Berlin public transit',
                'body': 'Please invest in better tram and train service across the district.',
                'representative': self.representative.pk,
                'tags': 'transport',
                'postal_code': '10115'
            },
            follow=True
        )

        self.assertEqual(response.status_code, 200)
        letter = Letter.objects.get()
        self.assertEqual(letter.author, self.user)
        self.assertTrue(
            Signature.objects.filter(user=self.user, letter=letter).exists()
        )

    def test_letter_form_prefills_postal_code_from_verification(self):
        IdentityVerification.objects.create(
            user=self.user,
            status='VERIFIED',
            postal_code='10115',
            city='Berlin',
            state='Berlin',
            constituency=self.constituency,
            verified_at=timezone.now()
        )

        self.client.login(username='alice', password='password123')

        response = self.client.get(reverse('letter_create'))

        self.assertEqual(response.status_code, 200)
        form = response.context['form']
        self.assertEqual(form.fields['postal_code'].initial, '10115')
        reps = list(form.fields['representative'].queryset)
        self.assertEqual(reps, [self.representative])


class ReportLetterTests(LetterTestBase):
    """Report flow should surface form and persist submissions."""

    def setUp(self):
        super().setUp()
        self.letter = Letter.objects.create(
            title='Noise pollution downtown',
            body='Late-night street noise needs regulation.',
            author=self.other_user,
            representative=self.representative,
            status='PUBLISHED'
        )

    def test_get_report_page_shows_form(self):
        self.client.login(username='alice', password='password123')

        response = self.client.get(reverse('report_letter', args=[self.letter.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Submit report')

    def test_post_creates_report_and_redirects(self):
        self.client.login(username='alice', password='password123')

        response = self.client.post(
            reverse('report_letter', args=[self.letter.pk]),
            {
                'reason': 'SPAM',
                'description': 'Promotes unrelated content.'
            }
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Report.objects.filter(letter=self.letter, reporter=self.user, reason='SPAM').exists()
        )


class AnalyzeTitleSuggestionsTests(LetterTestBase):
    """Similar letter suggestions should surface matching titles."""

    def setUp(self):
        super().setUp()
        self.existing_letter = Letter.objects.create(
            title='Universities need funding',
            body='We should increase investments into universities across the country.',
            author=self.other_user,
            representative=self.representative,
            status='PUBLISHED'
        )

    def test_similar_letter_displayed_for_matching_title(self):
        response = self.client.post(
            reverse('analyze_title'),
            {'title': 'Universities'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('Universities need funding', response.content.decode())


class ConstituencyMappingTests(LetterTestBase):
    """Address mapper should resolve German constituencies from address data."""

    def setUp(self):
        super().setUp()
        self.alt_state = Constituency.objects.create(
            name='Bayern',
            level='STATE',
            legislative_body='Landtag Bayern',
            legislative_period_start=date(2018, 10, 5),
            region='Bayern',
            parent_constituency=self.federal_root,
            metadata={'state': 'Bayern', 'state_code': 'BY', 'postal_code_prefixes': ['80', '81', '82']}
        )

    def _mock_geocode(self):
        return {
            'latitude': 52.5208,
            'longitude': 13.4095,
            'raw': {},
            'address': {
                'city': 'Berlin',
                'postcode': '10115',
                'state': 'Berlin'
            }
        }

    @patch('letters.services.AddressConstituencyMapper.geocode_address')
    def test_map_address_returns_federal_wahlkreis(self, mock_geocode):
        from .services import AddressConstituencyMapper

        mock_geocode.return_value = self._mock_geocode()

        constituency = AddressConstituencyMapper.map_address_to_constituency(
            'Unter den Linden 1',
            '10115',
            'Berlin',
            'Berlin'
        )

        self.assertEqual(constituency, self.constituency)

    @patch('letters.services.AddressConstituencyMapper.geocode_address')
    def test_get_constituencies_exposes_all_levels(self, mock_geocode):
        from .services import AddressConstituencyMapper

        mock_geocode.return_value = self._mock_geocode()

        matches = AddressConstituencyMapper.get_constituencies_for_address(
            'Unter den Linden 1',
            '10115',
            'Berlin',
            'Berlin'
        )

        self.assertEqual(matches['local'], self.local_constituency)
        self.assertEqual(matches['state'], self.state_constituency)
        self.assertEqual(matches['federal'], self.constituency)

    @patch('letters.services.AddressConstituencyMapper.geocode_address')
    def test_constituencies_from_postal_code(self, mock_geocode):
        mock_geocode.return_value = self._mock_geocode()

        matches = AddressConstituencyMapper.constituencies_from_postal_code('10115')

        self.assertEqual(matches['federal'], self.constituency)
        self.assertEqual(matches['state'], self.state_constituency)
        self.assertEqual(matches['local'], self.local_constituency)


class IdentityVerificationServiceTests(LetterTestBase):
    """Identity verification should persist constituency linkage."""

    @patch('letters.services.AddressConstituencyMapper.get_constituencies_for_address')
    def test_complete_verification_links_user_to_wahlkreis(self, mock_get_constituencies):
        mock_get_constituencies.return_value = {
            'federal': self.constituency,
            'state': self.state_constituency,
            'local': self.local_constituency,
        }

        verification_data = {
            'street_address': 'Unter den Linden 1',
            'postal_code': '10115',
            'city': 'Berlin',
            'state': 'Berlin',
        }

        verification = IdentityVerificationService.complete_verification(
            self.user,
            verification_data
        )

        self.assertIsNotNone(verification)
        self.assertEqual(verification.constituency, self.constituency)
        self.assertEqual(verification.postal_code, '10115')


class LetterSignatureSummaryTests(LetterTestBase):
    """Letter detail highlights constituent and verified signature counts."""

    def setUp(self):
        super().setUp()
        self.alt_state = Constituency.objects.create(
            name='Bayern',
            level='STATE',
            legislative_body='Landtag Bayern',
            legislative_period_start=date(2018, 10, 5),
            region='Bayern',
            parent_constituency=self.federal_root,
            metadata={'state': 'Bayern', 'state_code': 'BY', 'postal_code_prefixes': ['80', '81', '82']}
        )
        self.other_constituency = Constituency.objects.create(
            name='München',
            level='LOCAL',
            legislative_body='Stadtrat München',
            legislative_period_start=date(2020, 5, 1),
            region='80331',
            parent_constituency=self.alt_state,
            metadata={
                'state': 'Bayern',
                'state_code': 'BY',
                'cities': ['münchen', 'munich'],
                'postal_code_prefixes': ['80331', '803']
            }
        )
        self.other_representative = Representative.objects.create(
            constituency=self.other_constituency,
            first_name='Erika',
            last_name='Mustermann',
            party='Independent',
            term_start=date(2020, 5, 1)
        )

        self.letter = Letter.objects.create(
            title='Invest in public transport',
            body='We need better tram coverage across Mitte.',
            author=self.other_user,
            representative=self.representative,
            status='PUBLISHED'
        )

        IdentityVerification.objects.create(
            user=self.user,
            provider='stub',
            status='VERIFIED',
            street_address='Unter den Linden 1',
            postal_code='10115',
            city='Berlin',
            state='Berlin',
            constituency=self.constituency,
            verified_at=timezone.now()
        )

        IdentityVerification.objects.create(
            user=self.other_user,
            provider='stub',
            status='VERIFIED',
            street_address='Marienplatz 1',
            postal_code='80331',
            city='München',
            state='Bayern',
            constituency=self.other_constituency,
            verified_at=timezone.now()
        )

        self.third_user = User.objects.create_user(
            username='charlie',
            password='password123',
            email='charlie@example.com'
        )

        Signature.objects.create(user=self.user, letter=self.letter)
        Signature.objects.create(user=self.other_user, letter=self.letter)
        Signature.objects.create(user=self.third_user, letter=self.letter)

    def test_letter_detail_contains_signature_breakdown(self):
        response = self.client.get(reverse('letter_detail', args=[self.letter.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['constituent_signature_count'], 1)
        self.assertEqual(response.context['other_verified_signature_count'], 1)
        self.assertEqual(response.context['unverified_signature_count'], 1)
        html = response.content.decode()
        self.assertIn('<strong>1</strong> constituent', html)
        self.assertIn('<strong>1</strong> other verified', html)
        self.assertIn('<strong>1</strong> unverified', html)
        self.assertIn('✓ Verified Constituent', html)
        self.assertIn('✓ Verified</span>', html)

    def test_state_list_constituent_logic(self):
        self.other_representative.metadata = {
            'constituency_scope': 'state',
            'list_state_normalized': 'Bayern',
        }
        self.other_representative.save(update_fields=['metadata'])

        letter = Letter.objects.create(
            title='State policy',
            body='Testing state list logic.',
            author=self.other_user,
            representative=self.other_representative,
            status='PUBLISHED'
        )

        Signature.objects.create(user=self.user, letter=letter)
        Signature.objects.create(user=self.other_user, letter=letter)

        constituent, other_verified, unverified = letter.signature_breakdown()
        self.assertEqual(constituent, 1)
        self.assertEqual(other_verified, 1)
        self.assertEqual(unverified, 0)

    def test_federal_list_marks_all_verified_constituents(self):
        self.representative.metadata = {
            'constituency_scope': 'federal'
        }
        self.representative.save(update_fields=['metadata'])

        constituent, other_verified, unverified = self.letter.signature_breakdown()
        self.assertEqual(constituent, 2)
        self.assertEqual(other_verified, 0)
        self.assertEqual(unverified, 1)


class FetchWahlkreisDataCommandTests(TestCase):
    """Ensure wahlkreis geo command downloads and writes data."""

    @patch('letters.management.commands.fetch_wahlkreis_data.requests.get')
    def test_fetch_simple_geojson(self, mock_get):
        mock_response = MagicMock()
        mock_response.content = b'{"type":"FeatureCollection","features":[]}'
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / 'wahl.geojson'
            call_command(
                'fetch_wahlkreis_data',
                '--url',
                'https://example.com/wahl.geojson',
                '--output',
                str(output_path),
                '--force',
            )

            self.assertTrue(output_path.exists())
            self.assertIn('FeatureCollection', output_path.read_text(encoding='utf-8'))

    @patch('letters.management.commands.fetch_wahlkreis_data.requests.get')
    def test_fetch_zip_geojson(self, mock_get):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('wk.geojson', '{"type":"FeatureCollection","features":[]}')
        buffer.seek(0)

        mock_response = MagicMock()
        mock_response.content = buffer.getvalue()
        mock_response.headers = {'Content-Type': 'application/zip'}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / 'wahl.geojson'
            call_command(
                'fetch_wahlkreis_data',
                '--url',
                'https://example.com/wahl.zip',
                '--output',
                str(output_path),
                '--force',
            )

            self.assertTrue(output_path.exists())

    @patch('letters.management.commands.fetch_wahlkreis_data.requests.get')
    def test_fetch_zip_missing_member(self, mock_get):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('readme.txt', 'no geojson here')
        buffer.seek(0)

        mock_response = MagicMock()
        mock_response.content = buffer.getvalue()
        mock_response.headers = {'Content-Type': 'application/zip'}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / 'wahl.geojson'
            with self.assertRaises(CommandError):
                call_command(
                    'fetch_wahlkreis_data',
                    '--url',
                    'https://example.com/wahl.zip',
                    '--output',
                    str(output_path),
                    '--force',
                )
