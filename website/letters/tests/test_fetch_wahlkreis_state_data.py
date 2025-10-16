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
        self.assertIn('URL:', output)
        self.assertIn('Total: 9 states', output)

    def test_state_field_mapping_samples(self):
        """Test that field mapping works for real samples from all 9 states."""
        # Real samples from each state's GeoJSON (single feature properties)
        state_samples = {
            'BW': {
                'raw': {"WK Name": "Stuttgart I", "Nummer": "1"},
                'expected_nr': 1,
                'expected_name': "Stuttgart I"
            },
            'BY': {
                'raw': {"SKR_NR": 101, "SKR_NAME": "München-Hadern"},
                'expected_nr': 101,
                'expected_name': "München-Hadern"
            },
            'BE': {
                'raw': {"AWK": "0101"},
                'expected_nr': 101,
                'expected_name': "0101"  # Berlin uses AWK for both
            },
            'HB': {
                'raw': {"BEZ_GEM": "Walle", "wbz": "434-03"},
                'expected_nr': '434-03',
                'expected_name': "Walle"
            },
            'NI': {
                'raw': {"WKName": "Springe", "WKNum": 34},
                'expected_nr': 34,
                'expected_name': "Springe"
            },
            'NW': {
                'raw': {"LWKNR": 1.0, "Name": "Aachen I"},
                'expected_nr': 1,
                'expected_name': "Aachen I"
            },
            'ST': {
                'raw': {"WK_Nr_21": 1, "WK_Name_21": "Salzwedel"},
                'expected_nr': 1,
                'expected_name': "Salzwedel"
            },
            'SH': {
                'raw': {"wahlkreis_nr": 1, "wahlkreis_name": "Nordfriesland-Nord"},
                'expected_nr': 1,
                'expected_name': "Nordfriesland-Nord"
            },
            'TH': {
                'raw': {"WK_ID": 25, "WK": "Erfurt II"},
                'expected_nr': 25,
                'expected_name': "Erfurt II"
            },
        }

        from letters.management.commands.sync_wahlkreise import Command
        cmd = Command()

        for state_code, sample in state_samples.items():
            # Create a minimal GeoJSON structure
            geojson_text = json.dumps({
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [0, 0]},
                    "properties": sample['raw']
                }]
            })

            # Run through normalization
            normalized = cmd._normalize_state_geojson(
                geojson_text,
                state_code,
                f"Test State {state_code}"
            )

            # Parse and verify
            data = json.loads(normalized)
            props = data['features'][0]['properties']

            # Should have normalized WKR_NR and WKR_NAME
            self.assertIn('WKR_NR', props,
                         f"{state_code}: Missing WKR_NR after normalization")
            self.assertIn('WKR_NAME', props,
                         f"{state_code}: Missing WKR_NAME after normalization")

            # Verify values match expected
            self.assertEqual(props['WKR_NR'], sample['expected_nr'],
                           f"{state_code}: WKR_NR mismatch")
            self.assertEqual(props['WKR_NAME'], sample['expected_name'],
                           f"{state_code}: WKR_NAME mismatch")

            # Standard fields should be added
            self.assertEqual(props['LAND_CODE'], state_code)
            self.assertEqual(props['LEVEL'], 'STATE')

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
                c1 = constituencies.get(list_id='BW-0001')  # 4-digit for states
                self.assertEqual(c1.name, '1 - Stuttgart I (Baden-Württemberg 2021 - 2026)')
                self.assertEqual(c1.metadata['WKR_NR'], 1)  # Should be normalized to int
                self.assertEqual(c1.metadata['WKR_NAME'], 'Stuttgart I')
                self.assertEqual(c1.metadata['LAND_CODE'], 'BW')

                # Verify second constituency
                c2 = constituencies.get(list_id='BW-0002')  # 4-digit for states
                self.assertEqual(c2.name, '2 - Stuttgart II (Baden-Württemberg 2021 - 2026)')
            finally:
                # Cleanup
                import shutil
                if Path('test_data').exists():
                    shutil.rmtree('test_data')

    def test_state_data_source_urls_accessible(self):
        """Test that all state data source URLs return 2xx status codes.

        Note: This test makes real network requests and may be slow.
        Some state servers may not support HEAD requests, so we fall back to GET with a small range.
        """
        from letters.management.commands.sync_wahlkreise import STATE_SOURCES
        import requests

        failed_states = []

        for state_code, config in STATE_SOURCES.items():
            url = config['url']
            try:
                # Try HEAD request first (faster)
                response = requests.head(url, timeout=10, allow_redirects=True)

                # Some servers return 400 for HEAD but work for GET
                if response.status_code == 400:
                    # Try a GET request with range header to minimize data transfer
                    response = requests.get(url, headers={'Range': 'bytes=0-1023'}, timeout=10, allow_redirects=True)

                # Accept 2xx status codes (and 206 Partial Content for range requests)
                if not (200 <= response.status_code < 300):
                    failed_states.append((state_code, url, response.status_code))
            except requests.RequestException as e:
                failed_states.append((state_code, url, str(e)))

        # Assert all URLs are accessible
        if failed_states:
            error_msg = "\n".join(
                f"  {code}: {url} -> {status}"
                for code, url, status in failed_states
            )
            self.fail(f"The following state data sources are not accessible:\n{error_msg}")

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
