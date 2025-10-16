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
    def test_fetch_syncs_to_database_when_parliament_exists(self, mock_get):
        """Test that fetching state data creates constituencies in database."""
        # Mock response for BW (uses "Nummer" and "WK Name")
        mock_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [9.0, 48.7]},
                    "properties": {"Nummer": "1", "WK Name": "Stuttgart I"}
                },
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [9.1, 48.8]},
                    "properties": {"Nummer": "2", "WK Name": "Stuttgart II"}
                }
            ]
        }

        # Create proper ZIP file containing GeoJSON
        import io
        import zipfile
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('wahlkreise_bw.geojson', json.dumps(mock_geojson))
        zip_content = zip_buffer.getvalue()

        mock_response = Mock()
        mock_response.content = zip_content
        mock_response.headers = {}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Create Parliament and Term
        from letters.models import Parliament, ParliamentTerm, Constituency
        parliament = Parliament.objects.create(
            name='Baden-Württemberg',
            level='STATE',
            region='Baden-Württemberg',
            legislative_body='Landtag Baden-Württemberg'
        )
        term = ParliamentTerm.objects.create(
            parliament=parliament,
            name='Baden-Württemberg 2021 - 2026',
            start_date='2021-05-17',
            end_date='2026-03-13'
        )

        out = StringIO()

        with self.settings(CONSTITUENCY_BOUNDARIES_PATH='test_data/wahlkreise.geojson'):
            Path('test_data').mkdir(exist_ok=True)

            try:
                call_command('sync_wahlkreise', '--state', 'BW', '--force', stdout=out)

                output = out.getvalue()
                self.assertIn('Created 2 and updated 0 constituencies', output)

                # Verify constituencies were created
                constituencies = Constituency.objects.filter(
                    parliament_term=term,
                    scope='STATE_DISTRICT'
                )
                self.assertEqual(constituencies.count(), 2)

                # Verify first constituency
                c1 = constituencies.get(wahlkreis_id='BW-001')
                self.assertEqual(c1.name, '1 - Stuttgart I (Baden-Württemberg 2021 - 2026)')
                self.assertEqual(c1.metadata['WKR_NR'], 1)  # Should be normalized to int
                self.assertEqual(c1.metadata['WKR_NAME'], 'Stuttgart I')
                self.assertEqual(c1.metadata['LAND_CODE'], 'BW')

                # Verify second constituency
                c2 = constituencies.get(wahlkreis_id='BW-002')
                self.assertEqual(c2.name, '2 - Stuttgart II (Baden-Württemberg 2021 - 2026)')
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
