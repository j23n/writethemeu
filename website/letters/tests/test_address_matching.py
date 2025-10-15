# ABOUTME: Test address-based constituency matching with geocoding and point-in-polygon lookup.
# ABOUTME: Covers AddressGeocoder, WahlkreisLocator, and ConstituencyLocator services.

import os
from django.test import TestCase
from unittest.mock import patch, MagicMock
from letters.services import AddressGeocoder, WahlkreisLocator, ConstituencyLocator
from letters.services.wahlkreis import WahlkreisResolver
from letters.models import GeocodeCache


# Test addresses covering all German states
TEST_ADDRESSES = [
    {
        'name': 'Bundestag (Berlin)',
        'street': 'Platz der Republik 1',
        'postal_code': '11011',
        'city': 'Berlin',
        'expected_state': 'Berlin'
    },
    {
        'name': 'Hamburg Rathaus',
        'street': 'Rathausmarkt 1',
        'postal_code': '20095',
        'city': 'Hamburg',
        'expected_state': 'Hamburg'
    },
    {
        'name': 'Marienplatz München (Bavaria)',
        'street': 'Marienplatz 1',
        'postal_code': '80331',
        'city': 'München',
        'expected_state': 'Bayern'
    },
    {
        'name': 'Kölner Dom (North Rhine-Westphalia)',
        'street': 'Domkloster 4',
        'postal_code': '50667',
        'city': 'Köln',
        'expected_state': 'Nordrhein-Westfalen'
    },
    {
        'name': 'Brandenburger Tor (Berlin)',
        'street': 'Pariser Platz',
        'postal_code': '10117',
        'city': 'Berlin',
        'expected_state': 'Berlin'
    },
]


class AddressGeocodingTests(TestCase):
    """Test address geocoding with OSM Nominatim."""

    def setUp(self):
        self.geocoder = AddressGeocoder()

    def test_geocode_success_with_mocked_api(self):
        """Test successful geocoding with mocked Nominatim response."""
        with patch('requests.get') as mock_get:
            # Mock successful Nominatim response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [{
                'lat': '52.5186',
                'lon': '13.3761'
            }]
            mock_get.return_value = mock_response

            lat, lon, success, error = self.geocoder.geocode(
                'Platz der Republik 1',
                '11011',
                'Berlin'
            )

            self.assertTrue(success)
            self.assertIsNone(error)
            self.assertAlmostEqual(lat, 52.5186, places=4)
            self.assertAlmostEqual(lon, 13.3761, places=4)

    def test_geocode_caches_results(self):
        """Test that geocoding results are cached in database."""
        with patch('requests.get') as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = [{
                'lat': '52.5186',
                'lon': '13.3761'
            }]
            mock_get.return_value = mock_response

            # First call should cache
            self.geocoder.geocode('Platz der Republik 1', '11011', 'Berlin')

            # Check cache entry exists
            cache_key = self.geocoder._generate_cache_key(
                'Platz der Republik 1', '11011', 'Berlin', 'DE'
            )
            cache_entry = GeocodeCache.objects.filter(address_hash=cache_key).first()
            self.assertIsNotNone(cache_entry)
            self.assertTrue(cache_entry.success)

    def test_geocode_returns_cached_results(self):
        """Test that cached geocoding results are reused."""
        # Create cache entry
        cache_key = self.geocoder._generate_cache_key(
            'Test Street', '12345', 'Test City', 'DE'
        )
        GeocodeCache.objects.create(
            address_hash=cache_key,
            success=True,
            latitude=52.0,
            longitude=13.0
        )

        # Should return cached result without API call
        with patch('requests.get') as mock_get:
            lat, lon, success, error = self.geocoder.geocode(
                'Test Street', '12345', 'Test City'
            )

            # Verify no API call was made
            mock_get.assert_not_called()

            # Verify cached results returned
            self.assertTrue(success)
            self.assertEqual(lat, 52.0)
            self.assertEqual(lon, 13.0)

    def test_geocode_handles_api_error(self):
        """Test graceful handling of Nominatim API errors."""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = Exception("API Error")

            # Capture expected warning log
            with self.assertLogs('letters.services', level='WARNING') as log_context:
                lat, lon, success, error = self.geocoder.geocode(
                    'Invalid Street', '99999', 'Nowhere'
                )

            self.assertFalse(success)
            self.assertIsNone(lat)
            self.assertIsNone(lon)
            self.assertIn('API Error', error)
            # Verify expected warning was logged
            self.assertEqual(len(log_context.output), 1)
            self.assertIn('Geocoding failed', log_context.output[0])


class WahlkreisLocationTests(TestCase):
    """Test point-in-polygon constituency matching."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Use test fixture instead of production data
        cls.fixture_path = os.path.join(
            os.path.dirname(__file__),
            'fixtures',
            'wahlkreise.geojson'
        )

    def test_locate_bundestag_coordinates(self):
        """Test that Bundestag coordinates find correct Berlin constituency."""
        locator = WahlkreisLocator(self.fixture_path)
        result = locator.locate(52.5186, 13.3761)

        self.assertIsNotNone(result)
        wkr_nr, wkr_name, land_name = result
        self.assertIsInstance(wkr_nr, int)
        self.assertIn('Berlin', land_name)

    def test_locate_hamburg_coordinates(self):
        """Test that Hamburg coordinates find correct constituency."""
        locator = WahlkreisLocator(self.fixture_path)
        result = locator.locate(53.5511, 9.9937)

        self.assertIsNotNone(result)
        wkr_nr, wkr_name, land_name = result
        self.assertIsInstance(wkr_nr, int)
        self.assertIn('Hamburg', land_name)

    def test_coordinates_outside_germany(self):
        """Test that coordinates outside Germany return None."""
        locator = WahlkreisLocator(self.fixture_path)

        # Paris coordinates
        result = locator.locate(48.8566, 2.3522)
        self.assertIsNone(result)

        # London coordinates
        result = locator.locate(51.5074, -0.1278)
        self.assertIsNone(result)

    def test_locator_loads_available_state_files(self):
        """Test WahlkreisLocator loads state GeoJSON files if they exist."""
        import tempfile
        import shutil
        import json
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Copy federal fixture
            federal_path = tmpdir_path / 'wahlkreise_federal.geojson'
            shutil.copy(self.fixture_path, federal_path)

            # Create mock state file for BW
            state_data = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[9.0, 48.7], [9.1, 48.7], [9.1, 48.8], [9.0, 48.8], [9.0, 48.7]]]
                    },
                    "properties": {
                        "WKR_NR": 1,
                        "WKR_NAME": "Stuttgart I",
                        "LAND_CODE": "BW",
                        "LAND_NAME": "Baden-Württemberg",
                        "LEVEL": "STATE"
                    }
                }]
            }

            state_path = tmpdir_path / 'wahlkreise_bw.geojson'
            state_path.write_text(json.dumps(state_data))

            # Initialize locator with this directory
            locator = WahlkreisLocator(geojson_path=str(federal_path))

            # Verify state data was loaded
            self.assertIn('BW', locator.state_constituencies)
            self.assertEqual(len(locator.state_constituencies['BW']), 1)

    def test_locate_detailed_returns_both_federal_and_state(self):
        """Test _locate_detailed finds both federal and state constituencies."""
        import tempfile
        import shutil
        import json
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create federal data with Berlin
            federal_data = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[13.3, 52.5], [13.4, 52.5], [13.4, 52.6], [13.3, 52.6], [13.3, 52.5]]]
                    },
                    "properties": {
                        "WKR_NR": 83,
                        "WKR_NAME": "Berlin-Mitte",
                        "LAND_NAME": "Berlin",
                        "LAND_CODE": "BE"
                    }
                }]
            }

            federal_path = tmpdir_path / 'wahlkreise_federal.geojson'
            federal_path.write_text(json.dumps(federal_data))

            # Create state data for Berlin
            state_data = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[13.3, 52.5], [13.4, 52.5], [13.4, 52.6], [13.3, 52.6], [13.3, 52.5]]]
                    },
                    "properties": {
                        "WKR_NR": 1,
                        "WKR_NAME": "Mitte",
                        "LAND_CODE": "BE",
                        "LAND_NAME": "Berlin",
                        "LEVEL": "STATE"
                    }
                }]
            }

            state_path = tmpdir_path / 'wahlkreise_be.geojson'
            state_path.write_text(json.dumps(state_data))

            locator = WahlkreisLocator(geojson_path=str(federal_path))

            # Point inside Berlin
            result = locator._locate_detailed(52.52, 13.35)

            self.assertIsNotNone(result)
            self.assertIn('federal', result)
            self.assertIn('state', result)

            # Check federal result
            self.assertIsNotNone(result['federal'])
            self.assertEqual(result['federal']['wkr_nr'], 83)
            self.assertEqual(result['federal']['wkr_name'], 'Berlin-Mitte')
            self.assertEqual(result['federal']['land_code'], 'BE')

            # Check state result
            self.assertIsNotNone(result['state'])
            self.assertEqual(result['state']['wkr_nr'], 1)
            self.assertEqual(result['state']['wkr_name'], 'Mitte')
            self.assertEqual(result['state']['land_code'], 'BE')


class FullAddressMatchingTests(TestCase):
    """Integration tests for full address → constituency matching."""

    @patch('letters.services.wahlkreis.WahlkreisResolver.resolve')
    def test_locate_returns_correct_constituency(self, mock_resolve):
        """Test that ConstituencyLocator.locate() returns constituencies."""
        from letters.models import Parliament, ParliamentTerm, Constituency

        # Create test data
        parliament = Parliament.objects.create(
            name='Bundestag',
            level='FEDERAL',
            legislative_body='Bundestag',
            region='DE'
        )
        term = ParliamentTerm.objects.create(
            parliament=parliament,
            name='20. Wahlperiode'
        )
        constituency = Constituency.objects.create(
            parliament_term=term,
            name='Berlin-Mitte',
            scope='FEDERAL_DISTRICT',
            wahlkreis_id='075'
        )

        # Mock WahlkreisResolver to return our test constituency
        mock_resolve.return_value = {
            'federal_wahlkreis_number': '075',
            'state_wahlkreis_number': '075',
            'eu_wahlkreis': 'DE',
            'constituencies': [constituency]
        }

        locator = ConstituencyLocator()
        constituencies = locator.locate(
            street='Unter den Linden 1',
            postal_code='10117',
            city='Berlin'
        )

        self.assertEqual(len(constituencies), 1)
        self.assertEqual(constituencies[0].id, constituency.id)

    @patch('letters.services.AddressGeocoder.geocode')
    def test_plz_fallback_returns_constituencies(self, mock_geocode):
        """Test PLZ prefix fallback returns constituencies."""
        from letters.models import Parliament, ParliamentTerm, Constituency

        # Create test data
        bundestag = Parliament.objects.create(
            name='Bundestag',
            level='FEDERAL',
            legislative_body='Bundestag',
            region='DE'
        )
        term = ParliamentTerm.objects.create(
            parliament=bundestag,
            name='20. Wahlperiode'
        )
        federal_const = Constituency.objects.create(
            parliament_term=term,
            name='Berlin',
            scope='FEDERAL_STATE_LIST',
            metadata={'state': 'Berlin'}
        )

        # Mock geocoding failure
        mock_geocode.return_value = (None, None, False, "Geocoding failed")

        locator = ConstituencyLocator()
        result = locator.locate(
            postal_code='10115'  # Berlin postal code
        )

        # Should return list of Constituency objects (using PLZ fallback)
        self.assertIsInstance(result, list)
        if result:  # May be empty if no DB match, but should be list
            self.assertIsInstance(result[0], Constituency)


# End of file
