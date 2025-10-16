# ABOUTME: Tests for WahlkreisResolver service that maps addresses to Wahlkreis identifiers
# ABOUTME: and then resolves those identifiers to Constituency objects.
from unittest.mock import patch, MagicMock
from django.test import TestCase

from letters.services.wahlkreis import WahlkreisResolver
from letters.models import Parliament, ParliamentTerm, Constituency


class WahlkreisResolverTests(TestCase):
    def setUp(self):
        # Create test parliament infrastructure
        self.federal_parliament = Parliament.objects.create(
            name='Bundestag',
            level='FEDERAL',
            legislative_body='Bundestag',
            region='DE'
        )
        self.federal_term = ParliamentTerm.objects.create(
            parliament=self.federal_parliament,
            name='20. Wahlperiode'
        )

        # Create a federal district constituency with wahlkreis_id
        self.federal_constituency = Constituency.objects.create(
            parliament_term=self.federal_term,
            name='Berlin-Mitte',
            scope='FEDERAL_DISTRICT',
            wahlkreis_id='075',
            metadata={'state': 'Berlin'}
        )

        # Create state parliament
        self.state_parliament = Parliament.objects.create(
            name='Abgeordnetenhaus von Berlin',
            level='STATE',
            legislative_body='Abgeordnetenhaus',
            region='BE'
        )
        self.state_term = ParliamentTerm.objects.create(
            parliament=self.state_parliament,
            name='19. Wahlperiode'
        )

        # Create state list constituency
        self.state_constituency = Constituency.objects.create(
            parliament_term=self.state_term,
            name='Berlin',
            scope='STATE_LIST',
            metadata={'state': 'Berlin'}
        )

    @patch('letters.services.wahlkreis.AddressGeocoder.geocode')
    @patch('letters.services.wahlkreis.WahlkreisLocator.locate')
    def test_resolve_returns_wahlkreis_identifiers_and_constituencies(
        self, mock_wahlkreis_locate, mock_geocode
    ):
        """Test that resolve() returns Wahlkreis IDs and matching constituencies"""
        # Mock geocoding
        mock_geocode.return_value = (52.520, 13.405, True, None)

        # Mock Wahlkreis lookup - returns detailed result
        mock_wahlkreis_locate.return_value = {
            'federal': {
                'wkr_nr': 75,
                'wkr_name': 'Berlin-Mitte',
                'land_name': 'Berlin',
                'land_code': 'BE'
            },
            'state': None
        }

        resolver = WahlkreisResolver()
        result = resolver.resolve(
            address='Unter den Linden 1, 10117 Berlin'
        )

        # Check structure
        self.assertIn('federal_wahlkreis_number', result)
        self.assertIn('state_wahlkreis_number', result)
        self.assertIn('eu_wahlkreis', result)
        self.assertIn('constituencies', result)

        # Check values
        self.assertEqual(result['federal_wahlkreis_number'], '075')
        self.assertEqual(result['eu_wahlkreis'], 'DE')

        # Check constituencies returned
        constituency_ids = {c.id for c in result['constituencies']}
        self.assertIn(self.federal_constituency.id, constituency_ids)
        self.assertIn(self.state_constituency.id, constituency_ids)

    @patch('letters.services.wahlkreis.AddressGeocoder.geocode')
    @patch('letters.services.wahlkreis.WahlkreisLocator.locate')
    def test_resolve_returns_state_district_constituencies(
        self, mock_locate, mock_geocode
    ):
        """Test that resolve() returns state district constituencies when available"""
        # Create state district constituency
        state_district = Constituency.objects.create(
            parliament_term=self.state_term,
            name='Berlin-Mitte (Landtag)',
            scope='STATE_DISTRICT',
            wahlkreis_id='025',
            metadata={'state': 'Berlin'}
        )

        # Mock geocoding
        mock_geocode.return_value = (52.520, 13.405, True, None)

        # Mock Wahlkreis lookup with both federal and state
        mock_locate.return_value = {
            'federal': {
                'wkr_nr': 75,
                'wkr_name': 'Berlin-Mitte',
                'land_name': 'Berlin',
                'land_code': 'BE'
            },
            'state': {
                'wkr_nr': 25,
                'wkr_name': 'Berlin-Mitte (Landtag)',
                'land_name': 'Berlin',
                'land_code': 'BE'
            }
        }

        resolver = WahlkreisResolver()
        result = resolver.resolve(address='Unter den Linden 1, 10117 Berlin')

        # Check wahlkreis numbers
        self.assertEqual(result['federal_wahlkreis_number'], '075')
        self.assertEqual(result['state_wahlkreis_number'], '025')

        # Check all constituency types returned
        constituency_ids = {c.id for c in result['constituencies']}
        self.assertIn(self.federal_constituency.id, constituency_ids,
                     "Should include federal district")
        self.assertIn(self.state_constituency.id, constituency_ids,
                     "Should include state list")
        self.assertIn(state_district.id, constituency_ids,
                     "Should include state district")
