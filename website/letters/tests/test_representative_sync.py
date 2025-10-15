# ABOUTME: Test representative synchronization service.
# ABOUTME: Covers parliament syncing, photo handling, and representative import logic.

from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from letters.services.representative_sync import RepresentativeSyncService
from letters.models import Parliament, ParliamentTerm


class SyncParliamentMethodTests(TestCase):
    """Test the _sync_parliament method that replaces _sync_federal/_sync_eu/_sync_state."""

    def setUp(self):
        """Set up test service instance."""
        self.service = RepresentativeSyncService(dry_run=True)

    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI.get_parliament_periods')
    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI.get_candidacies_mandates')
    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI.get_committees')
    def test_sync_parliament_creates_federal_parliament(self, mock_committees, mock_mandates, mock_periods):
        """Test that _sync_parliament creates federal parliament correctly."""
        # Arrange
        mock_periods.return_value = [{
            'id': 111,
            'label': '20. Wahlperiode',
            'start_date_period': '2021-10-26',
            'end_date_period': '2025-10-25',
        }]
        mock_mandates.return_value = []
        mock_committees.return_value = []

        parliament_data = {
            'id': 1,
            'label': 'Bundestag',
            'current_project': {'id': 111}
        }

        # Act
        self.service._sync_parliament(parliament_data, level='FEDERAL', region='DE', description='Bundestag')

        # Assert
        self.assertEqual(Parliament.objects.count(), 1)
        parliament = Parliament.objects.first()
        self.assertEqual(parliament.name, 'Bundestag')
        self.assertEqual(parliament.level, 'FEDERAL')
        self.assertEqual(parliament.region, 'DE')

    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI.get_parliament_periods')
    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI.get_candidacies_mandates')
    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI.get_committees')
    def test_sync_parliament_creates_eu_parliament(self, mock_committees, mock_mandates, mock_periods):
        """Test that _sync_parliament creates EU parliament correctly."""
        # Arrange
        mock_periods.return_value = [{
            'id': 222,
            'label': 'EU 2019-2024',
            'start_date_period': '2019-07-02',
            'end_date_period': '2024-07-16',
        }]
        mock_mandates.return_value = []
        mock_committees.return_value = []

        parliament_data = {
            'id': 2,
            'label': 'EU-Parlament',
            'current_project': {'id': 222}
        }

        # Act
        self.service._sync_parliament(parliament_data, level='EU', region='EU', description='EU Parliament')

        # Assert
        self.assertEqual(Parliament.objects.count(), 1)
        parliament = Parliament.objects.first()
        self.assertEqual(parliament.name, 'EU-Parlament')
        self.assertEqual(parliament.level, 'EU')
        self.assertEqual(parliament.region, 'EU')

    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI.get_parliament_periods')
    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI.get_candidacies_mandates')
    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI.get_committees')
    def test_sync_parliament_creates_state_parliament(self, mock_committees, mock_mandates, mock_periods):
        """Test that _sync_parliament creates state parliament correctly."""
        # Arrange
        mock_periods.return_value = [{
            'id': 333,
            'label': '19. Wahlperiode',
            'start_date_period': '2021-05-01',
            'end_date_period': '2026-04-30',
        }]
        mock_mandates.return_value = []
        mock_committees.return_value = []

        parliament_data = {
            'id': 3,
            'label': 'Landtag Baden-Württemberg',
            'current_project': {'id': 333}
        }

        # Act
        self.service._sync_parliament(parliament_data, level='STATE', region='BW', description='Landtag Baden-Württemberg')

        # Assert
        self.assertEqual(Parliament.objects.count(), 1)
        parliament = Parliament.objects.first()
        self.assertEqual(parliament.name, 'Landtag Baden-Württemberg')
        self.assertEqual(parliament.level, 'STATE')
        self.assertEqual(parliament.region, 'BW')


class FindPhotoUrlTests(TestCase):
    """Test the _find_photo_url method without HTML scraping fallback."""

    def setUp(self):
        """Set up test service instance."""
        self.service = RepresentativeSyncService(dry_run=True)

    def test_finds_photo_url_from_image_dict(self):
        """Test that photo URL is extracted from image dict."""
        politician = {
            'id': 123,
            'label': 'Test Person',
            'image': {
                'url': 'https://example.com/photo.jpg'
            }
        }
        result = self.service._find_photo_url(politician)
        self.assertEqual(result, 'https://example.com/photo.jpg')

    def test_finds_photo_url_from_image_original(self):
        """Test that photo URL is extracted from image original field."""
        politician = {
            'id': 123,
            'label': 'Test Person',
            'image': {
                'original': 'https://example.com/original.jpg'
            }
        }
        result = self.service._find_photo_url(politician)
        self.assertEqual(result, 'https://example.com/original.jpg')

    def test_finds_photo_url_from_image_versions(self):
        """Test that photo URL is extracted from image versions."""
        politician = {
            'id': 123,
            'label': 'Test Person',
            'image': {
                'versions': {
                    'large': 'https://example.com/large.jpg',
                    'small': {'url': 'https://example.com/small.jpg'}
                }
            }
        }
        result = self.service._find_photo_url(politician)
        self.assertIn(result, ['https://example.com/large.jpg', 'https://example.com/small.jpg'])

    def test_returns_none_when_no_image_data(self):
        """Test that None is returned when no image data exists."""
        politician = {
            'id': 123,
            'label': 'Test Person'
        }
        result = self.service._find_photo_url(politician)
        self.assertIsNone(result)

    def test_returns_none_when_no_valid_url_in_image_dict(self):
        """Test that None is returned when image dict has no valid URL."""
        politician = {
            'id': 123,
            'label': 'Test Person',
            'image': {
                'caption': 'Some caption'
            }
        }
        result = self.service._find_photo_url(politician)
        self.assertIsNone(result)

    def test_does_not_scrape_html_when_profile_url_exists(self):
        """Test that HTML scraping is not performed even when profile URL exists."""
        politician = {
            'id': 123,
            'label': 'Test Person',
            'abgeordnetenwatch_url': 'https://example.com/profile'
        }
        # Should return None without making HTTP requests
        result = self.service._find_photo_url(politician)
        self.assertIsNone(result)


# End of file
