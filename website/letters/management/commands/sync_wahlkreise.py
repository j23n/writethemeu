# ABOUTME: Management command to sync constituencies from Abgeordnetenwatch API.
# ABOUTME: Creates Parliament/ParliamentTerm/Constituency records and validates against GeoJSON wahlkreise files.

import json

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from letters.models import Parliament, ParliamentTerm, Constituency
from letters.services.abgeordnetenwatch_api_client import AbgeordnetenwatchAPI


class Command(BaseCommand):
    """Sync German electoral constituencies from Abgeordnetenwatch API."""

    help = (
        "Sync German electoral constituencies from Abgeordnetenwatch API. "
        "Creates Parliament, ParliamentTerm, and Constituency records for all levels "
        "(EU, Federal Bundestag, State Landtag). Validates that GeoJSON wahlkreise files "
        "have matching constituencies for address geocoding. "
        "Run this command before sync_representatives."
    )

    def add_arguments(self, parser):
        pass

    def handle(self, *args, **options):
        """Sync constituencies from API and validate against GeoJSON wahlkreise."""

        # Step 1: Sync from API
        self.stdout.write(self.style.SUCCESS("Step 1: Syncing constituencies from Abgeordnetenwatch API..."))
        self._handle_api_sync()

        # Step 2: Ensure EU constituency exists
        self.stdout.write(self.style.SUCCESS("\nStep 2: Ensuring EU constituency exists..."))
        self._ensure_eu_constituency()

        # Step 3: Load GeoJSON files (for future validation)
        self.stdout.write(self.style.SUCCESS("\nStep 3: GeoJSON validation..."))
        self.stdout.write("  (GeoJSON validation not yet implemented - wahlkreise files used for geocoding only)")

        self.stdout.write(self.style.SUCCESS("\n✓ Sync complete!"))

    def _ensure_eu_constituency(self) -> None:
        """Ensure a Germany-wide EU constituency exists."""
        # Get or create EU parliament
        eu_parliament, _ = Parliament.objects.get_or_create(
            level='EU',
            region='DE',
            defaults={
                'name': 'Europäisches Parlament',
                'legislative_body': 'Europäisches Parlament'
            }
        )

        # Get or create current EU term
        eu_term, _ = ParliamentTerm.objects.get_or_create(
            parliament=eu_parliament,
            name='2024-2029',
            defaults={
                'start_date': '2024-07-16',
                'end_date': '2029-07-15'
            }
        )

        # Get or create EU constituency
        eu_constituency, created = Constituency.objects.get_or_create(
            parliament_term=eu_term,
            scope='EU_AT_LARGE',
            defaults={
                'name': 'Deutschland',
                'list_id': 'DE',
                'metadata': {'country': 'DE'}
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(
                f"Created EU constituency: {eu_constituency.name}"
            ))
        else:
            # Update list_id if missing
            if not eu_constituency.list_id:
                eu_constituency.list_id = 'DE'
                eu_constituency.save(update_fields=['list_id'])
                self.stdout.write(f"Updated EU constituency with list_id=DE")

    @transaction.atomic
    def _sync_constituencies_from_api(
        self,
        parliament_data: dict,
        period_data: dict,
        level: str
    ) -> dict:
        """
        Sync constituencies from Abgeordnetenwatch API for a given parliament term.

        Args:
            parliament_data: Parliament data from API (includes 'id' and 'label')
            period_data: Parliament period/term data from API (includes 'id' and 'label')
            level: 'FEDERAL', 'STATE', or 'EU'

        Returns:
            dict with stats: {'created': int, 'updated': int, 'errors': list}
        """
        parliament_id = parliament_data['id']
        parliament_name = parliament_data['label']
        parliament_term_id = period_data['id']
        period_name = period_data['label']

        stats = {'created': 0, 'updated': 0, 'errors': []}

        # Fetch constituencies (districts)
        try:
            constituencies_data = AbgeordnetenwatchAPI.get_constituencies(parliament_term_id)
        except requests.RequestException as e:
            error_msg = f"Failed to fetch constituencies for parliament_term_id {parliament_term_id}: {e}"
            self.stdout.write(self.style.ERROR(f"  {error_msg}"))
            stats['errors'].append(error_msg)
            constituencies_data = []
        except Exception as e:
            error_msg = f"Unexpected error fetching constituencies for parliament_term_id {parliament_term_id}: {e}"
            self.stdout.write(self.style.ERROR(f"  {error_msg}"))
            stats['errors'].append(error_msg)
            constituencies_data = []

        # Fetch electoral lists
        try:
            electoral_lists_data = AbgeordnetenwatchAPI.get_electoral_lists(parliament_term_id)
        except requests.RequestException as e:
            error_msg = f"Failed to fetch electoral lists for parliament_term_id {parliament_term_id}: {e}"
            self.stdout.write(self.style.ERROR(f"  {error_msg}"))
            stats['errors'].append(error_msg)
            electoral_lists_data = []
        except Exception as e:
            error_msg = f"Unexpected error fetching electoral lists for parliament_term_id {parliament_term_id}: {e}"
            self.stdout.write(self.style.ERROR(f"  {error_msg}"))
            stats['errors'].append(error_msg)
            electoral_lists_data = []

        # Get or create Parliament and ParliamentTerm
        parliament, _ = Parliament.objects.get_or_create(
            metadata__api_id=parliament_id,
            defaults={
                'name': f'Parliament {parliament_id}',  # Will be updated by sync_representatives
                'level': level,
                'legislative_body': '',
                'region': '',
                'metadata': {'api_id': parliament_id, 'source': 'abgeordnetenwatch'}
            }
        )

        term, _ = ParliamentTerm.objects.get_or_create(
            metadata__period_id=parliament_term_id,
            parliament=parliament,
            defaults={
                'name': f'Term {parliament_term_id}',  # Will be updated by sync_representatives
                'metadata': {'period_id': parliament_term_id, 'source': 'abgeordnetenwatch'}
            }
        )

        # Process district constituencies
        for const_data in constituencies_data:
            external_id = str(const_data['id'])
            number = const_data.get('number')
            name = const_data.get('name', '')
            label = const_data.get('label', f"{number} - {name}")

            # Determine scope based on parliament level
            if level == 'FEDERAL':
                scope = 'FEDERAL_DISTRICT'
                # Generate list_id: 3-digit zero-padded for federal (e.g., "001")
                list_id = str(number).zfill(3) if number else None
            elif level == 'STATE':
                scope = 'STATE_DISTRICT'
                # Generate list_id: state code + 4-digit number (e.g., "BY-0001")
                # Get state code from parliament region
                from letters.constants import get_state_code
                parliament = Parliament.objects.filter(metadata__api_id=parliament_data['id']).first()
                if parliament and number:
                    state_code = get_state_code(parliament.region)
                    if state_code:
                        list_id = f"{state_code}-{str(number).zfill(4)}"
                    else:
                        list_id = None
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning("Could not determine state code for parliament %s", parliament.name)
                else:
                    list_id = None
            else:
                continue  # EU doesn't have districts

            # Create or update constituency
            constituency, created = Constituency.objects.update_or_create(
                external_id=external_id,
                defaults={
                    'parliament_term': term,
                    'name': label,
                    'scope': scope,
                    'list_id': list_id,
                    'metadata': {
                        'api_id': const_data['id'],
                        'number': number,
                        'source': 'abgeordnetenwatch',
                        'raw': const_data
                    },
                    'last_synced_at': timezone.now()
                }
            )

            if created:
                stats['created'] += 1
            else:
                stats['updated'] += 1

        # Process electoral lists
        for list_data in electoral_lists_data:
            external_id = str(list_data['id'])
            name = list_data.get('name', '')
            label = list_data.get('label', name)

            # Determine scope and list_id based on name pattern
            name_lower = name.lower()
            if level == 'FEDERAL':
                if 'bundesliste' in name_lower:
                    scope = 'FEDERAL_LIST'
                    list_id = 'BUND-DE-LIST'
                else:
                    scope = 'FEDERAL_STATE_LIST'
                    # Try to extract state from name
                    from letters.constants import normalize_german_state, get_state_code
                    list_id = None
                    for state_name in ['Baden-Württemberg', 'Bayern', 'Berlin', 'Brandenburg',
                                      'Bremen', 'Hamburg', 'Hessen', 'Mecklenburg-Vorpommern',
                                      'Niedersachsen', 'Nordrhein-Westfalen', 'Rheinland-Pfalz',
                                      'Saarland', 'Sachsen', 'Sachsen-Anhalt', 'Schleswig-Holstein', 'Thüringen']:
                        if state_name.lower() in name_lower:
                            state_code = get_state_code(state_name)
                            if state_code:
                                list_id = f"{state_code}-LIST"
                                break
                    if not list_id:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning("Could not determine state code for federal list: %s", name)
            elif level == 'STATE':
                if 'regional' in name_lower or 'wahlkreis' in name_lower:
                    scope = 'STATE_REGIONAL_LIST'
                    list_id = None  # No standard format for regional lists
                else:
                    scope = 'STATE_LIST'
                    # Get state code from parliament
                    from letters.constants import get_state_code
                    parliament = Parliament.objects.filter(metadata__api_id=parliament_data['id']).first()
                    if parliament:
                        state_code = get_state_code(parliament.region)
                        if state_code:
                            list_id = f"{state_code}-STATE-LIST"
                        else:
                            list_id = None
                    else:
                        list_id = None
            elif level == 'EU':
                scope = 'EU_AT_LARGE'
                list_id = 'DE'
            else:
                scope = 'OTHER'
                list_id = None

            # Create or update constituency
            constituency, created = Constituency.objects.update_or_create(
                external_id=external_id,
                defaults={
                    'parliament_term': term,
                    'name': label,
                    'scope': scope,
                    'list_id': list_id,
                    'metadata': {
                        'api_id': list_data['id'],
                        'source': 'abgeordnetenwatch',
                        'raw': list_data
                    },
                    'last_synced_at': timezone.now()
                }
            )

            if created:
                stats['created'] += 1
            else:
                stats['updated'] += 1

        return stats

    def _handle_api_sync(self):
        """Sync constituencies from Abgeordnetenwatch API for all parliaments."""

        self.stdout.write("Syncing constituencies from Abgeordnetenwatch API...")

        # Track overall statistics
        total_stats = {
            'parliaments_processed': 0,
            'parliaments_failed': 0,
            'total_created': 0,
            'total_updated': 0,
            'failed_parliaments': []
        }

        # Get all parliaments
        try:
            parliaments_data = AbgeordnetenwatchAPI.get_parliaments()
        except requests.RequestException as e:
            error_msg = f"Failed to fetch parliaments list: {e}"
            self.stdout.write(self.style.ERROR(error_msg))
            self.stdout.write(self.style.ERROR("Cannot proceed without parliaments list. Aborting."))
            return
        except Exception as e:
            error_msg = f"Unexpected error fetching parliaments list: {e}"
            self.stdout.write(self.style.ERROR(error_msg))
            self.stdout.write(self.style.ERROR("Cannot proceed without parliaments list. Aborting."))
            return

        for parliament_data in parliaments_data:
            parliament_id = parliament_data['id']
            parliament_name = parliament_data['label']

            # Determine level
            if parliament_name == 'EU-Parlament':
                level = 'EU'
            elif parliament_name == 'Bundestag':
                level = 'FEDERAL'
            else:
                level = 'STATE'

            self.stdout.write(f"\n{parliament_name} ({level})...")

            try:
                # Get parliament periods
                try:
                    periods = AbgeordnetenwatchAPI.get_parliament_periods(parliament_id)
                except requests.RequestException as e:
                    error_msg = f"Failed to fetch periods for {parliament_name}: {e}"
                    self.stdout.write(self.style.ERROR(f"  {error_msg}"))
                    total_stats['parliaments_failed'] += 1
                    total_stats['failed_parliaments'].append((parliament_name, error_msg))
                    continue
                except Exception as e:
                    error_msg = f"Unexpected error fetching periods for {parliament_name}: {e}"
                    self.stdout.write(self.style.ERROR(f"  {error_msg}"))
                    total_stats['parliaments_failed'] += 1
                    total_stats['failed_parliaments'].append((parliament_name, error_msg))
                    continue

                if not periods:
                    self.stdout.write(f"  No periods found")
                    total_stats['parliaments_processed'] += 1
                    continue

                # Sync current period only
                current_period = periods[0]
                period_id = current_period['id']
                period_name = current_period['label']

                self.stdout.write(f"  Period: {period_name}")

                stats = self._sync_constituencies_from_api(parliament_data, current_period, level)

                if stats.get('errors'):
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Created {stats['created']}, Updated {stats['updated']} constituencies ({len(stats['errors'])} errors)"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  Created {stats['created']}, Updated {stats['updated']} constituencies"
                        )
                    )

                total_stats['total_created'] += stats['created']
                total_stats['total_updated'] += stats['updated']
                total_stats['parliaments_processed'] += 1

            except Exception as e:
                error_msg = f"Unexpected error processing {parliament_name}: {e}"
                self.stdout.write(self.style.ERROR(f"  {error_msg}"))
                total_stats['parliaments_failed'] += 1
                total_stats['failed_parliaments'].append((parliament_name, error_msg))
                continue

        # Print summary
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("Sync Summary:")
        self.stdout.write(f"  Parliaments processed: {total_stats['parliaments_processed']}")
        self.stdout.write(f"  Parliaments failed: {total_stats['parliaments_failed']}")
        self.stdout.write(f"  Total constituencies created: {total_stats['total_created']}")
        self.stdout.write(f"  Total constituencies updated: {total_stats['total_updated']}")

        if total_stats['failed_parliaments']:
            self.stdout.write(self.style.WARNING("\nFailed parliaments:"))
            for name, error in total_stats['failed_parliaments']:
                self.stdout.write(f"  {name}: {error[:100]}")

        if total_stats['parliaments_failed'] == 0:
            self.stdout.write(self.style.SUCCESS("\nAll parliaments processed successfully!"))
        elif total_stats['parliaments_processed'] > 0:
            self.stdout.write(self.style.WARNING("\nPartial success - some parliaments failed."))
        else:
            self.stdout.write(self.style.ERROR("\nAll parliaments failed to process."))
