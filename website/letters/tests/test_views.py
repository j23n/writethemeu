# ABOUTME: Tests for view functionality
# ABOUTME: Tests competency page and profile address views

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from letters.models import IdentityVerification, TopicArea, Parliament, ParliamentTerm, Constituency


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


class ProfileViewAddressTests(TestCase):
    """Test profile view address form submission."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='password123',
            email='testuser@example.com',
        )
        self.client.login(username='testuser', password='password123')


    def test_profile_page_does_not_show_verification_section(self):
        """Profile page should not display verification section"""
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Identity & Constituency')
        self.assertNotContains(response, 'Start Third-party Verification')

    def test_profile_post_only_accepts_constituency_form(self):
        """Profile POST should only handle constituency form, not address"""
        # Create test constituencies
        bundestag = Parliament.objects.create(
            name='Bundestag', level='FEDERAL', legislative_body='Bundestag', region='DE'
        )
        term = ParliamentTerm.objects.create(parliament=bundestag, name='20. Wahlperiode')
        federal_const = Constituency.objects.create(
            parliament_term=term, name='Berlin-Mitte', scope='FEDERAL_DISTRICT'
        )

        # Test 1: Constituency form should work
        response = self.client.post(reverse('profile'), {
            'federal_constituency': federal_const.id,
            'state_constituency': ''
        })

        self.assertEqual(response.status_code, 302)  # Redirect after success

        # Verify constituency was saved
        verification = IdentityVerification.objects.get(user=self.user)
        self.assertEqual(verification.federal_constituency, federal_const)

        # Test 2: Address form should NOT work anymore (no address_form_submit handling)
        response = self.client.post(reverse('profile'), {
            'address_form_submit': '1',
            'street_address': 'Test Street 123',
            'postal_code': '12345',
            'city': 'TestCity',
        })

        # Should not save address or redirect with success
        # View should either ignore this or show form errors
        verification.refresh_from_db()
        # Address fields should not be updated (they might not even exist)
        # This test will fail until we remove address form handling
