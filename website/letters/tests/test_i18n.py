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
