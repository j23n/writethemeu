from io import StringIO
from django.test import TestCase
from django.core.management import call_command, load_command_class
from unittest.mock import patch, MagicMock
from letters.models import Parliament, ParliamentTerm, Constituency


class TestSyncWahlkreiseCommand(TestCase):

    @patch('letters.management.commands.sync_wahlkreise.AbgeordnetenwatchAPI')
    def test_command_syncs_from_api_only(self, mock_api_class):
        """Test that command syncs from API without GeoJSON-based DB updates."""
        # Mock class method responses
        mock_api_class.get_parliaments.return_value = [
            {'id': 111, 'label': 'Bundestag'}
        ]
        mock_api_class.get_parliament_periods.return_value = [
            {'id': 222, 'label': '2025-2029'}
        ]
        mock_api_class.get_constituencies.return_value = [
            {'id': 1, 'number': 1, 'name': 'Flensburg', 'label': '1 - Flensburg'}
        ]
        mock_api_class.get_electoral_lists.return_value = []

        out = StringIO()
        call_command('sync_wahlkreise', stdout=out)

        output = out.getvalue()
        self.assertIn('Syncing constituencies from', output)
        self.assertTrue('Created' in output or 'Updated' in output)

        # Verify constituency was created from API
        self.assertTrue(Constituency.objects.filter(external_id='1').exists())
        constituency = Constituency.objects.get(external_id='1')
        self.assertEqual(constituency.list_id, '001')  # Should be set from API

    def test_command_has_no_deprecated_flags(self):
        """Test that deprecated flags are removed."""
        command = load_command_class('letters', 'sync_wahlkreise')
        parser = command.create_parser('manage.py', 'sync_wahlkreise')

        # Get list of all option strings
        option_strings = []
        for action in parser._actions:
            option_strings.extend(action.option_strings)

        # Verify deprecated flags are removed
        self.assertNotIn('--state', option_strings)
        self.assertNotIn('--all-states', option_strings)
        self.assertNotIn('--enrich-from-geojson', option_strings)
        self.assertNotIn('--api-sync', option_strings)

    @patch('letters.management.commands.sync_wahlkreise.AbgeordnetenwatchAPI')
    def test_api_sync_sets_list_id_federal(self, mock_api_class):
        """Test that federal constituency list_id is set from API."""
        from letters.management.commands.sync_wahlkreise import Command

        command = Command()

        parliament_data = {'id': 111, 'label': 'Bundestag'}
        period_data = {'id': 222, 'label': '2025-2029'}

        # Mock constituency data from API
        mock_api_class.get_constituencies.return_value = [
            {'id': 1, 'number': 1, 'name': 'Flensburg', 'label': '1 - Flensburg'},
            {'id': 42, 'number': 42, 'name': 'München', 'label': '42 - München'},
            {'id': 299, 'number': 299, 'name': 'Rosenheim', 'label': '299 - Rosenheim'},
        ]
        mock_api_class.get_electoral_lists.return_value = []

        stats = command._sync_constituencies_from_api(parliament_data, period_data, 'FEDERAL')

        # Verify list_id format for federal: 3-digit zero-padded
        c1 = Constituency.objects.get(external_id='1')
        self.assertEqual(c1.list_id, '001')

        c42 = Constituency.objects.get(external_id='42')
        self.assertEqual(c42.list_id, '042')

        c299 = Constituency.objects.get(external_id='299')
        self.assertEqual(c299.list_id, '299')

    @patch('letters.management.commands.sync_wahlkreise.AbgeordnetenwatchAPI')
    def test_api_sync_sets_list_id_state(self, mock_api_class):
        """Test that state constituency list_id is set from API with state code."""
        from letters.management.commands.sync_wahlkreise import Command

        # Create Bayern parliament first
        parliament = Parliament.objects.create(
            name='Landtag Bayern',
            level='STATE',
            region='Bayern',
            legislative_body='Landtag Bayern',
            metadata={'api_id': 112}
        )
        term = ParliamentTerm.objects.create(
            parliament=parliament,
            name='Bayern 2023-2028',
            metadata={'period_id': 333}
        )

        command = Command()
        parliament_data = {'id': 112, 'label': 'Landtag Bayern'}
        period_data = {'id': 333, 'label': 'Bayern 2023-2028'}

        mock_api_class.get_constituencies.return_value = [
            {'id': 5001, 'number': 101, 'name': 'München-Land', 'label': '101 - München-Land'},
        ]
        mock_api_class.get_electoral_lists.return_value = []

        stats = command._sync_constituencies_from_api(parliament_data, period_data, 'STATE')

        # Verify list_id format for state: STATE_CODE-NNNN
        constituency = Constituency.objects.get(external_id='5001')
        self.assertEqual(constituency.list_id, 'BY-0101')
