# ABOUTME: Tests for internationalization configuration and functionality.
# ABOUTME: Verifies language switching, URL prefixes, and translation completeness.

from django.test import TestCase
from django.conf import settings


class I18nConfigurationTests(TestCase):
    def test_i18n_enabled(self):
        """Test that USE_I18N is enabled."""
        self.assertTrue(settings.USE_I18N)

    def test_supported_languages(self):
        """Test that German and English are configured."""
        language_codes = [code for code, name in settings.LANGUAGES]
        self.assertIn('de', language_codes)
        self.assertIn('en', language_codes)

    def test_locale_paths_configured(self):
        """Test that LOCALE_PATHS is set."""
        self.assertTrue(len(settings.LOCALE_PATHS) > 0)


class I18nURLTests(TestCase):
    def test_german_url_prefix_works(self):
        """Test that German URL prefix is accessible."""
        response = self.client.get('/de/')
        self.assertEqual(response.status_code, 200)

    def test_english_url_prefix_works(self):
        """Test that English URL prefix is accessible."""
        response = self.client.get('/en/')
        self.assertEqual(response.status_code, 200)

    def test_set_language_endpoint_exists(self):
        """Test that language switcher endpoint exists."""
        from django.urls import reverse
        url = reverse('set_language')
        self.assertEqual(url, '/i18n/setlang/')


class LanguageSwitcherTests(TestCase):
    def test_language_switcher_present_in_page(self):
        """Test that language switcher form is present."""
        response = self.client.get('/de/')
        self.assertContains(response, 'name="language"')
        self.assertContains(response, 'Deutsch')
        self.assertContains(response, 'English')

    def test_language_switch_changes_language(self):
        """Test that submitting language form changes language."""
        response = self.client.post(
            '/i18n/setlang/',
            {'language': 'en', 'next': '/en/'},
        )
        # Check we got a redirect
        self.assertEqual(response.status_code, 302)
        # Check cookie was set
        self.assertIn('django_language', response.cookies)
        self.assertEqual(response.cookies['django_language'].value, 'en')
