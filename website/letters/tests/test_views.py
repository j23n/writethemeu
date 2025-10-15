# ABOUTME: Tests for view functionality
# ABOUTME: Tests competency page and profile address views

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from letters.models import IdentityVerification, TopicArea


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

    def test_profile_view_saves_address(self):
        """Test that profile view saves address correctly."""
        response = self.client.post(
            reverse('profile'),
            {
                'address_form_submit': '1',
                'street_address': 'Unter den Linden 77',
                'postal_code': '10117',
                'city': 'Berlin',
            },
            follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse('profile'))

        # Verify address was saved
        verification = IdentityVerification.objects.get(user=self.user)
        self.assertEqual(verification.street_address, 'Unter den Linden 77')
        self.assertEqual(verification.postal_code, '10117')
        self.assertEqual(verification.city, 'Berlin')
        self.assertEqual(verification.status, 'SELF_DECLARED')
        self.assertEqual(verification.verification_type, 'SELF_DECLARED')

    def test_profile_view_updates_existing_address(self):
        """Test that profile view updates existing address."""
        # Create initial verification
        verification = IdentityVerification.objects.create(
            user=self.user,
            status='SELF_DECLARED',
            street_address='Old Street 1',
            postal_code='12345',
            city='OldCity',
        )

        response = self.client.post(
            reverse('profile'),
            {
                'address_form_submit': '1',
                'street_address': 'Unter den Linden 77',
                'postal_code': '10117',
                'city': 'Berlin',
            },
            follow=True
        )

        self.assertEqual(response.status_code, 200)

        # Verify address was updated
        verification.refresh_from_db()
        self.assertEqual(verification.street_address, 'Unter den Linden 77')
        self.assertEqual(verification.postal_code, '10117')
        self.assertEqual(verification.city, 'Berlin')

    def test_profile_view_displays_saved_address(self):
        """Test that profile view displays saved address."""
        # Create verification with address
        _ = IdentityVerification.objects.create(
            user=self.user,
            status='SELF_DECLARED',
            street_address='Unter den Linden 77',
            postal_code='10117',
            city='Berlin',
        )

        response = self.client.get(reverse('profile'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Unter den Linden 77')
        self.assertContains(response, '10117')
        self.assertContains(response, 'Berlin')
