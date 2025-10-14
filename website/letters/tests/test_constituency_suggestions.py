# ABOUTME: Test ConstituencySuggestionService combining topics and geography.
# ABOUTME: Integration tests for letter title/address to representative suggestions.

from django.test import TestCase
from unittest.mock import patch
from letters.services import ConstituencySuggestionService


class ConstituencySuggestionTests(TestCase):
    """Test constituency suggestion combining topic and address matching."""

    @patch('letters.services.AddressGeocoder.geocode')
    def test_suggest_with_title_and_address(self, mock_geocode):
        """Test suggestions work with both title and address."""
        # Mock geocoding
        mock_geocode.return_value = (52.5186, 13.3761, True, None)

        result = ConstituencySuggestionService.suggest_from_concern(
            concern_text="We need better train connections",
            user_location={
                "street": "Platz der Republik 1",
                "postal_code": "11011",
                "city": "Berlin"
            }
        )

        self.assertIn('matched_topics', result)
        self.assertIn('suggested_level', result)
        self.assertIn('explanation', result)
        self.assertIn('representatives', result)
        self.assertIn('constituencies', result)

    def test_suggest_with_only_title(self):
        """Test suggestions work with only title (no address)."""
        result = ConstituencySuggestionService.suggest_from_concern(
            concern_text="Climate protection is important"
        )

        self.assertIn('matched_topics', result)
        self.assertIn('suggested_level', result)
        # Without address, should still suggest level and topics
        self.assertIsNotNone(result['suggested_level'])

    def test_suggest_with_only_postal_code(self):
        """Test suggestions work with only postal code."""
        result = ConstituencySuggestionService.suggest_from_concern(
            concern_text="Local infrastructure problems",
            user_location={
                "postal_code": "10115"
            }
        )

        self.assertIn('constituencies', result)
        # Should use PLZ fallback
        self.assertIsInstance(result['constituencies'], list)


# End of file
