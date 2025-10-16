from django.test import TestCase
from letters.services.representative_sync import RepresentativeSyncService
from letters.models import Parliament, ParliamentTerm, Constituency, Representative
from unittest.mock import patch


class TestSyncIntegration(TestCase):
    """Integration tests for the full sync workflow."""

    def test_constituency_linking_workflow(self):
        """Test that representatives link to constituencies by external_id."""
        # Create test data simulating what sync_wahlkreise would create
        parliament = Parliament.objects.create(
            name='Bundestag',
            level='FEDERAL',
            region='DE',
            legislative_body='Bundestag',
            metadata={'api_id': 111}
        )
        term = ParliamentTerm.objects.create(
            parliament=parliament,
            name='2025-2029',
            metadata={'period_id': 222}
        )

        # Create constituencies with external_ids
        c1 = Constituency.objects.create(
            external_id='1',
            parliament_term=term,
            name='1 - Flensburg',
            scope='FEDERAL_DISTRICT',
            list_id='001'
        )
        c_list = Constituency.objects.create(
            external_id='5001',
            parliament_term=term,
            name='Schleswig-Holstein List',
            scope='FEDERAL_STATE_LIST',
            list_id='SH-LIST'
        )

        # Simulate representative sync finding these constituencies
        service = RepresentativeSyncService(dry_run=True)

        # Test direct mandate
        electoral_direct = {
            'constituency': {'id': 1},
            'mandate_won': 'constituency'
        }
        rep1 = Representative.objects.create(
            external_id='9001',
            parliament=parliament,
            parliament_term=term,
            first_name='Anna',
            last_name='Schmidt'
        )
        constituencies = list(service._determine_constituencies(parliament, term, electoral_direct, rep1))
        self.assertEqual(len(constituencies), 1)
        self.assertEqual(constituencies[0].external_id, '1')

        # Test list seat
        electoral_list = {
            'electoral_list': {'id': 5001},
            'mandate_won': 'list'
        }
        rep2 = Representative.objects.create(
            external_id='9002',
            parliament=parliament,
            parliament_term=term,
            first_name='Max',
            last_name='Müller'
        )
        constituencies = list(service._determine_constituencies(parliament, term, electoral_list, rep2))
        self.assertEqual(len(constituencies), 1)
        self.assertEqual(constituencies[0].external_id, '5001')

    @patch('letters.services.representative_sync.logger')
    def test_missing_constituency_logs_warning(self, mock_logger):
        """Test that missing constituencies log warnings."""
        parliament = Parliament.objects.create(
            name='Bundestag',
            level='FEDERAL',
            region='DE'
        )
        term = ParliamentTerm.objects.create(
            parliament=parliament,
            name='Test'
        )

        service = RepresentativeSyncService(dry_run=True)
        rep = Representative.objects.create(
            external_id='9001',
            parliament=parliament,
            parliament_term=term,
            first_name='Test',
            last_name='Rep'
        )

        # Try to link to non-existent constituency
        electoral = {
            'constituency': {'id': 999},
            'mandate_won': 'constituency'
        }

        constituencies = list(service._determine_constituencies(parliament, term, electoral, rep))

        # Should be empty and should have logged warning
        self.assertEqual(len(constituencies), 0)
        mock_logger.warning.assert_called_once()
        # Check the formatted call args (first arg is format string, rest are values)
        call_args = mock_logger.warning.call_args[0]
        self.assertIn('external_id=%s', call_args[0])  # Format string
        self.assertEqual(call_args[1], 999)  # First format arg is the external_id
        self.assertIn('Run sync_wahlkreise first', call_args[0])
