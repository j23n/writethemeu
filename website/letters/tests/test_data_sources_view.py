# ABOUTME: Tests for data sources attribution page.
# ABOUTME: Validates that all state sources are listed with proper license info.

from django.test import TestCase
from django.urls import reverse


class DataSourcesViewTests(TestCase):
    """Test the data sources attribution page."""

    def test_data_sources_page_loads(self):
        """Test the data sources page is accessible."""
        response = self.client.get(reverse('data_sources'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'letters/data_sources.html')

    def test_page_lists_all_available_states(self):
        """Test all 9 states with data are listed."""
        response = self.client.get(reverse('data_sources'))

        content = response.content.decode()

        # Check all state names appear
        expected_states = [
            'Baden-Württemberg',
            'Bavaria',
            'Berlin',
            'Bremen',
            'Lower Saxony',
            'North Rhine-Westphalia',
            'Saxony-Anhalt',
            'Schleswig-Holstein',
            'Thuringia'
        ]

        for state_name in expected_states:
            self.assertIn(state_name, content)

    def test_page_shows_license_information(self):
        """Test license and attribution info is displayed."""
        response = self.client.get(reverse('data_sources'))

        content = response.content.decode()

        # Check license types appear
        self.assertIn('Datenlizenz Deutschland', content)
        self.assertIn('CC BY', content)

        # Check attribution appears
        self.assertIn('©', content)
        self.assertIn('Statistisches Landesamt', content)

    def test_page_lists_unavailable_states(self):
        """Test that states without data are also mentioned."""
        response = self.client.get(reverse('data_sources'))

        content = response.content.decode()

        # Should mention states without direct downloads
        unavailable_states = ['Brandenburg', 'Hesse', 'Mecklenburg-Vorpommern']

        for state in unavailable_states:
            self.assertIn(state, content)
