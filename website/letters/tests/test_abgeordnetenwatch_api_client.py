# ABOUTME: Test Abgeordnetenwatch API client methods.
# ABOUTME: Covers constituency and electoral list fetching with pagination.

from unittest.mock import patch
from django.test import TestCase
from letters.services.abgeordnetenwatch_api_client import AbgeordnetenwatchAPI


class GetConstituenciesTests(TestCase):
    """Test the get_constituencies method."""

    @patch('letters.services.abgeordnetenwatch_api_client.AbgeordnetenwatchAPI.fetch_paginated')
    def test_get_constituencies_fetches_with_parliament_period_filter(self, mock_fetch):
        """Test that get_constituencies calls fetch_paginated with correct params."""
        mock_fetch.return_value = [
            {'id': 14205, 'number': 299, 'name': 'Homburg'},
            {'id': 14204, 'number': 298, 'name': 'Saarlouis'},
        ]

        result = AbgeordnetenwatchAPI.get_constituencies(parliament_period_id=161)

        mock_fetch.assert_called_once_with('constituencies', {'parliament_period': 161})
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['number'], 299)

    @patch('letters.services.abgeordnetenwatch_api_client.AbgeordnetenwatchAPI.fetch_paginated')
    def test_get_electoral_lists_fetches_with_parliament_period_filter(self, mock_fetch):
        """Test that get_electoral_lists calls fetch_paginated with correct params."""
        mock_fetch.return_value = [
            {'id': 733, 'name': 'Landesliste Thüringen'},
            {'id': 732, 'name': 'Landesliste Schleswig-Holstein'},
        ]

        result = AbgeordnetenwatchAPI.get_electoral_lists(parliament_period_id=161)

        mock_fetch.assert_called_once_with('electoral-lists', {'parliament_period': 161})
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'Landesliste Thüringen')
