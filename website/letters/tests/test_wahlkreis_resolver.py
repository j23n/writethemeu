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

        # Mock Wahlkreis lookup - returns (wkr_nr, wkr_name, land_name)
        mock_wahlkreis_locate.return_value = (75, 'Berlin-Mitte', 'Berlin')

        resolver = WahlkreisResolver()
        result = resolver.resolve(
            street='Unter den Linden 1',
            postal_code='10117',
            city='Berlin'
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
