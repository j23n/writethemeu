# ABOUTME: Tests for wahlkreis search endpoint that geocodes addresses without storing them.
# ABOUTME: Validates authentication, valid/invalid addresses, and error handling.
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse


class WahlkreisSearchTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')
        self.url = reverse('search_wahlkreis')

    def test_search_wahlkreis_requires_authentication(self):
        """Unauthenticated users cannot search"""
        self.client.logout()
        response = self.client.post(self.url, {
            'street_address': 'Platz der Republik 1',
            'postal_code': '11011',
            'city': 'Berlin'
        })
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_search_wahlkreis_with_valid_address(self):
        """Valid address returns constituency data as JSON"""
        response = self.client.post(self.url, {
            'street_address': 'Platz der Republik 1',
            'postal_code': '11011',
            'city': 'Berlin'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('success', data)
        self.assertTrue(data['success'])
        self.assertIn('wahlkreis_nr', data)
        self.assertIn('wahlkreis_name', data)

    def test_search_wahlkreis_with_invalid_address(self):
        """Invalid address returns error message"""
        response = self.client.post(self.url, {
            'street_address': 'Nonexistent Street 999',
            'postal_code': '99999',
            'city': 'Nowhere'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('success', data)
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    def test_search_wahlkreis_missing_fields(self):
        """Missing required fields returns error"""
        response = self.client.post(self.url, {
            'street_address': 'Platz der Republik 1'
            # Missing postal_code and city
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('success', data)
        self.assertFalse(data['success'])
        self.assertIn('error', data)
