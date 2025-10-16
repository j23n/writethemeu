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

        # Step 2: Validate GeoJSON matches
        self.stdout.write(self.style.SUCCESS("\nStep 2: Validating GeoJSON matches..."))
        validation_stats = self._validate_geojson_matches()

        self.stdout.write(self.style.SUCCESS("\n✓ Sync complete!"))

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
                # Extract state code from parliament name (strip prefix like "Landtag ")
                from letters.constants import normalize_german_state, get_state_code
                name_to_normalize = parliament_name
                for prefix in ['Landtag ', 'Abgeordnetenhaus ', 'Bürgerschaft ']:
                    if name_to_normalize.startswith(prefix):
                        name_to_normalize = name_to_normalize[len(prefix):]
                        break
                state_code = get_state_code(normalize_german_state(name_to_normalize))
                if state_code and number:
                    list_id = f"{state_code}-{str(number).zfill(4)}"
                else:
                    list_id = None
            elif level == 'EU':
                scope = 'EU_AT_LARGE'
                # EU constituency is Germany-wide, use 'DE' as list_id for geocoding
                list_id = 'DE'
            else:
                continue  # Unknown level

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
                else:
                    scope = 'FEDERAL_STATE_LIST'
                # Electoral lists don't have geographic boundaries, so no list_id
                list_id = None
            elif level == 'STATE':
                if 'regional' in name_lower or 'wahlkreis' in name_lower:
                    scope = 'STATE_REGIONAL_LIST'
                else:
                    scope = 'STATE_LIST'
                # Electoral lists don't have geographic boundaries, so no list_id
                list_id = None
            elif level == 'EU':
                scope = 'EU_AT_LARGE'
                # EU electoral lists don't have geographic boundaries, so no list_id
                list_id = None
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

    def _validate_geojson_matches(self) -> dict:
        """
        Validate that all GeoJSON wahlkreise have matching constituencies in DB.

        This ensures address geocoding will always find a valid constituency.

        Returns:
            dict with validation stats:
            - 'geojson_count': int - number of wahlkreise in GeoJSON files
            - 'db_count': int - number of constituencies in DB with list_id
            - 'matched': int - wahlkreise with matching constituency
            - 'missing_in_db': list - list_ids in GeoJSON but not in DB
            - 'missing_in_geojson': list - list_ids in DB but not in GeoJSON
        """
        from pathlib import Path

        # Load federal GeoJSON
        geojson_path = Path(settings.CONSTITUENCY_BOUNDARIES_PATH)
        if not geojson_path.exists():
            self.stdout.write(self.style.WARNING(f"  GeoJSON file not found at {geojson_path}"))
            return {
                'geojson_count': 0,
                'db_count': 0,
                'matched': 0,
                'missing_in_db': [],
                'missing_in_geojson': []
            }

        # Extract list_ids from GeoJSON
        geojson_list_ids = set()
        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for feature in data.get('features', []):
                props = feature.get('properties', {})
                wkr_nr = props.get('WKR_NR')
                if wkr_nr:
                    list_id = str(wkr_nr).zfill(3)
                    geojson_list_ids.add(list_id)

        # Get list_ids from DB
        db_list_ids = set(
            Constituency.objects
            .filter(scope='FEDERAL_DISTRICT', list_id__isnull=False)
            .values_list('list_id', flat=True)
        )

        # Find mismatches
        missing_in_db = sorted(geojson_list_ids - db_list_ids)
        missing_in_geojson = sorted(db_list_ids - geojson_list_ids)
        matched = len(geojson_list_ids & db_list_ids)

        stats = {
            'geojson_count': len(geojson_list_ids),
            'db_count': len(db_list_ids),
            'matched': matched,
            'missing_in_db': missing_in_db,
            'missing_in_geojson': missing_in_geojson
        }

        # Report results
        self.stdout.write(f"  GeoJSON wahlkreise: {stats['geojson_count']}")
        self.stdout.write(f"  DB constituencies: {stats['db_count']}")
        self.stdout.write(f"  Matched: {stats['matched']}")

        if missing_in_db:
            self.stdout.write(self.style.WARNING(
                f"  Warning: {len(missing_in_db)} wahlkreise in GeoJSON but not in DB: {', '.join(missing_in_db[:10])}"
            ))

        if missing_in_geojson:
            self.stdout.write(self.style.WARNING(
                f"  Warning: {len(missing_in_geojson)} constituencies in DB but not in GeoJSON: {', '.join(missing_in_geojson[:10])}"
            ))

        if not missing_in_db and not missing_in_geojson:
            self.stdout.write(self.style.SUCCESS("  All wahlkreise have matching constituencies!"))

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
