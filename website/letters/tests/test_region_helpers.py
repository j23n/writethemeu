from django.test import TestCase
from letters.constants import normalize_german_state, get_state_code


class NormalizeGermanStateTests(TestCase):
    """Test that normalize_german_state handles all variants."""

    def test_normalizes_bavaria_variant(self):
        """Test Bavaria is normalized to Bayern."""
        self.assertEqual(normalize_german_state('Bavaria'), 'Bayern')

    def test_keeps_canonical_baden_wurttemberg(self):
        """Test Baden-Württemberg is unchanged."""
        self.assertEqual(normalize_german_state('Baden-Württemberg'), 'Baden-Württemberg')

    def test_normalizes_lowercase_berlin(self):
        """Test berlin is normalized to Berlin."""
        self.assertEqual(normalize_german_state('berlin'), 'Berlin')

    def test_returns_none_for_none(self):
        """Test None input returns None."""
        self.assertIsNone(normalize_german_state(None))

    def test_returns_none_for_empty_string(self):
        """Test empty string returns None."""
        self.assertIsNone(normalize_german_state(''))


class GetStateCodeTests(TestCase):
    """Test that get_state_code returns correct codes."""

    def test_gets_code_for_bayern(self):
        """Test Bayern returns BY."""
        self.assertEqual(get_state_code('Bayern'), 'BY')

    def test_gets_code_for_bavaria_variant(self):
        """Test Bavaria returns BY."""
        self.assertEqual(get_state_code('Bavaria'), 'BY')

    def test_gets_code_for_baden_wurttemberg(self):
        """Test Baden-Württemberg returns BW."""
        self.assertEqual(get_state_code('Baden-Württemberg'), 'BW')

    def test_gets_code_for_berlin(self):
        """Test Berlin returns BE."""
        self.assertEqual(get_state_code('Berlin'), 'BE')

    def test_returns_none_for_none(self):
        """Test None input returns None."""
        self.assertIsNone(get_state_code(None))

    def test_returns_none_for_invalid_state(self):
        """Test invalid state returns None."""
        self.assertIsNone(get_state_code('Invalid'))
