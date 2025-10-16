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

