# ABOUTME: Integration tests for state-level Wahlkreise data workflow.
# ABOUTME: Tests end-to-end: fetch command, file creation, locator loading, and lookup.

from django.test import TestCase
from django.core.management import call_command
from django.conf import settings
from pathlib import Path
from unittest.mock import patch, Mock
import json
import tempfile
import shutil

from letters.services.geocoding import WahlkreisLocator


class StateDataIntegrationTest(TestCase):
    """Test complete state data workflow from fetch to lookup."""

    def setUp(self):
        """Create temporary data directory."""
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir)

        # Create minimal federal data
        federal_data = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[9.0, 48.7], [9.5, 48.7], [9.5, 49.0], [9.0, 49.0], [9.0, 48.7]]]
                },
                "properties": {
                    "WKR_NR": 258,
                    "WKR_NAME": "Stuttgart I",
                    "LAND_NAME": "Baden-Württemberg"
                }
            }]
        }

        self.federal_path = self.data_dir / 'wahlkreise_federal.geojson'
        self.federal_path.write_text(json.dumps(federal_data))

    def tearDown(self):
        """Clean up temporary directory."""
        if Path(self.tmpdir).exists():
            shutil.rmtree(self.tmpdir)

    @patch('requests.get')
    def test_full_workflow_fetch_and_locate(self, mock_get):
        """Test: fetch state data -> load in locator -> find constituency."""

        # Mock BW state data download
        # BW uses 'geojson_zip' format, so we need to create a ZIP file
        state_data = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[9.0, 48.7], [9.5, 48.7], [9.5, 49.0], [9.0, 49.0], [9.0, 48.7]]]
                },
                "properties": {
                    "WKR_NR": "1",
                    "WKR_NAME": "Stuttgart I"
                }
            }]
        }

        # Create a proper ZIP file containing GeoJSON
        import io
        import zipfile
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('wahlkreise_bw.geojson', json.dumps(state_data))
        zip_content = zip_buffer.getvalue()

        mock_response = Mock()
        mock_response.content = zip_content
        mock_response.headers = {}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Step 1: Fetch state data
        with self.settings(CONSTITUENCY_BOUNDARIES_PATH=str(self.federal_path)):
            call_command('fetch_wahlkreis_data', '--state', 'BW', '--force', stdout=Mock())

        # Verify file was created
        state_file = self.data_dir / 'wahlkreise_bw.geojson'
        self.assertTrue(state_file.exists())

        # Verify normalization happened
        saved_data = json.loads(state_file.read_text())
        feature = saved_data['features'][0]
        self.assertEqual(feature['properties']['LAND_CODE'], 'BW')
        self.assertEqual(feature['properties']['LEVEL'], 'STATE')

        # Step 2: Load in WahlkreisLocator
        locator = WahlkreisLocator(geojson_path=str(self.federal_path))

        # Verify state data was loaded
        self.assertIn('BW', locator.state_constituencies)

        # Step 3: Test detailed locate
        result = locator._locate_detailed(48.8, 9.2)

        self.assertIsNotNone(result)
        self.assertIsNotNone(result['federal'])
        self.assertIsNotNone(result['state'])

        # Verify federal result
        self.assertEqual(result['federal']['wkr_nr'], 258)
        self.assertEqual(result['federal']['wkr_name'], 'Stuttgart I')

        # Verify state result
        self.assertEqual(result['state']['wkr_nr'], 1)
        self.assertEqual(result['state']['wkr_name'], 'Stuttgart I')
        self.assertEqual(result['state']['land_code'], 'BW')

        # Step 4: Verify backward compatibility - public API still works
        public_result = locator.locate(48.8, 9.2)

        self.assertIsNotNone(public_result)
        self.assertEqual(public_result[0], 258)  # wkr_nr
        self.assertEqual(public_result[1], 'Stuttgart I')  # wkr_name
        self.assertEqual(public_result[2], 'Baden-Württemberg')  # land_name
