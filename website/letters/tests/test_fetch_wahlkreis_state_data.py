# ABOUTME: Tests for state-level Wahlkreise data fetching command.
# ABOUTME: Validates state configuration listing, fetching, and format conversion.

from io import StringIO
from unittest.mock import patch, Mock
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
import json


class FetchWahlkreisStateDataTests(TestCase):
    """Test state data fetching functionality."""

    def test_list_states_shows_all_configurations(self):
        """Test --list flag displays all 9 state configurations."""
        out = StringIO()
        call_command('sync_wahlkreise', '--list', stdout=out)

        output = out.getvalue()

        # Check header
        self.assertIn('Available State Data Sources', output)

        # Check all 9 states are listed
        expected_states = ['BW', 'BY', 'BE', 'HB', 'NI', 'NW', 'ST', 'SH', 'TH']
        for state_code in expected_states:
            self.assertIn(state_code, output)

        # Check key information is shown
        self.assertIn('Baden-Württemberg', output)
        self.assertIn('Election:', output)
        self.assertIn('Districts:', output)
        self.assertIn('License:', output)
        self.assertIn('Total: 9 states', output)

    @patch('requests.get')
    def test_fetch_single_state_geojson_direct(self, mock_get):
        """Test fetching a single state with direct GeoJSON format."""
        # Mock response for Schleswig-Holstein (GeoJSON direct)
        mock_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [10.0, 54.0]},
                    "properties": {"WKR_NR": "1", "WKR_NAME": "Test District"}
                }
            ]
        }

        mock_response = Mock()
        mock_response.content = json.dumps(mock_geojson).encode('utf-8')
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        out = StringIO()

        with self.settings(CONSTITUENCY_BOUNDARIES_PATH='test_data/wahlkreise.geojson'):
            # Create temp directory
            Path('test_data').mkdir(exist_ok=True)

            try:
                call_command('sync_wahlkreise', '--state', 'SH', '--force', stdout=out)

                output = out.getvalue()
                self.assertIn('Schleswig-Holstein', output)
                self.assertIn('Saved SH data', output)

                # Verify file was created
                output_file = Path('test_data/wahlkreise_sh.geojson')
                self.assertTrue(output_file.exists())

                # Verify normalization
                saved_data = json.loads(output_file.read_text())
                feature = saved_data['features'][0]
                self.assertEqual(feature['properties']['LAND_CODE'], 'SH')
                self.assertEqual(feature['properties']['LAND_NAME'], 'Schleswig-Holstein')
                self.assertEqual(feature['properties']['LEVEL'], 'STATE')
            finally:
                # Cleanup
                import shutil
                if Path('test_data').exists():
                    shutil.rmtree('test_data')

    @patch('requests.get')
    def test_fetch_all_states_handles_failures_gracefully(self, mock_get):
        """Test --all-states continues on failures and reports summary."""
        # Make first request succeed, second fail, third succeed
        def side_effect(*args, **kwargs):
            url = args[0]
            if 'statistik-bw' in url:  # BW succeeds
                response = Mock()
                response.content = json.dumps({
                    "type": "FeatureCollection",
                    "features": []
                }).encode('utf-8')
                response.headers = {}
                response.raise_for_status = Mock()
                return response
            else:
                # Other states fail
                raise Exception("Network error")

        mock_get.side_effect = side_effect

        out = StringIO()

        with self.settings(CONSTITUENCY_BOUNDARIES_PATH='test_data/wahlkreise.geojson'):
            Path('test_data').mkdir(exist_ok=True)

            try:
                call_command('sync_wahlkreise', '--all-states', '--force', stdout=out)

                output = out.getvalue()
                self.assertIn('Fetching all 9 states', output)
                self.assertIn('Completed:', output)
                self.assertIn('Failed states:', output)
            finally:
                import shutil
                if Path('test_data').exists():
                    shutil.rmtree('test_data')
