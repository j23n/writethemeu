"""
Management command to sync representatives from Abgeordnetenwatch API.

Uses the real Abgeordnetenwatch.de API (CC0 licensed) to sync:
- Federal level: Bundestag representatives
- State level: Landtag representatives
- Local level: Not yet available in API
"""

import logging
from django.core.management.base import BaseCommand
from letters.services import RepresentativeDataService

logger = logging.getLogger('letters.services')


class Command(BaseCommand):
    help = 'Sync German political representatives from Abgeordnetenwatch API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--level',
            type=str,
            choices=['eu', 'federal', 'state', 'all'],
            default='federal',
            help='Which level of government to sync',
        )
        parser.add_argument(
            '--state',
            type=str,
            help='State name to filter (e.g., "Bayern", "Berlin") - only for state level',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview what would be synced without making changes',
        )

    def handle(self, *args, **options):
        level = options['level']
        state_filter = options.get('state')
        dry_run = options['dry_run']
        verbosity = options.get('verbosity', 1)

        # Configure logging based on verbosity
        if verbosity >= 3:
            logger.setLevel(logging.DEBUG)
        elif verbosity >= 2:
            logger.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.WARNING)

        # Add console handler if not already present
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(levelname)s: %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        if dry_run:
            self.stdout.write(self.style.WARNING('Running in DRY RUN mode - no changes will be saved'))

        if level in ['eu', 'all']:
            self.sync_eu(dry_run)

        if level in ['federal', 'all']:
            self.sync_federal(dry_run)

        if level in ['state', 'all']:
            self.sync_state(state_filter, dry_run)

        self.stdout.write(self.style.SUCCESS('Sync completed successfully'))

    def sync_eu(self, dry_run=False):
        """Sync European Parliament representatives (MEPs) from Abgeordnetenwatch API"""
        self.stdout.write(self.style.MIGRATE_HEADING('Syncing EU representatives (European Parliament MEPs from Germany) from Abgeordnetenwatch API...'))

        try:
            stats = RepresentativeDataService.sync_eu_representatives(dry_run=dry_run)

            self.stdout.write(self.style.SUCCESS(f'  Constituencies created: {stats["constituencies_created"]}'))
            self.stdout.write(self.style.SUCCESS(f'  Constituencies updated: {stats["constituencies_updated"]}'))
            self.stdout.write(self.style.SUCCESS(f'  Representatives created: {stats["representatives_created"]}'))
            self.stdout.write(self.style.SUCCESS(f'  Representatives updated: {stats["representatives_updated"]}'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Error syncing EU representatives: {e}'))

    def sync_federal(self, dry_run=False):
        """Sync Bundestag representatives from Abgeordnetenwatch API"""
        self.stdout.write(self.style.MIGRATE_HEADING('Syncing federal representatives (Bundestag) from Abgeordnetenwatch API...'))

        try:
            stats = RepresentativeDataService.sync_federal_representatives(dry_run=dry_run)

            self.stdout.write(self.style.SUCCESS(f'  Constituencies created: {stats["constituencies_created"]}'))
            self.stdout.write(self.style.SUCCESS(f'  Constituencies updated: {stats["constituencies_updated"]}'))
            self.stdout.write(self.style.SUCCESS(f'  Representatives created: {stats["representatives_created"]}'))
            self.stdout.write(self.style.SUCCESS(f'  Representatives updated: {stats["representatives_updated"]}'))

            # Show committee stats if available
            if 'total_committees_created' in stats:
                self.stdout.write(self.style.SUCCESS(f'  Committees created: {stats["total_committees_created"]}'))
                self.stdout.write(self.style.SUCCESS(f'  Committees updated: {stats["total_committees_updated"]}'))
                self.stdout.write(self.style.SUCCESS(f'  Committee memberships created: {stats["total_memberships_created"]}'))
                self.stdout.write(self.style.SUCCESS(f'  Committee memberships updated: {stats["total_memberships_updated"]}'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Error syncing federal representatives: {e}'))

    def sync_state(self, state_filter=None, dry_run=False):
        """Sync state parliament (Landtag) representatives from Abgeordnetenwatch API"""
        filter_msg = f' (filtered by: {state_filter})' if state_filter else ''
        self.stdout.write(self.style.MIGRATE_HEADING(f'Syncing state representatives (Landtag) from Abgeordnetenwatch API{filter_msg}...'))

        try:
            stats = RepresentativeDataService.sync_state_representatives(
                state_name=state_filter,
                dry_run=dry_run
            )

            self.stdout.write(self.style.SUCCESS(f'  Constituencies created: {stats["constituencies_created"]}'))
            self.stdout.write(self.style.SUCCESS(f'  Constituencies updated: {stats["constituencies_updated"]}'))
            self.stdout.write(self.style.SUCCESS(f'  Representatives created: {stats["representatives_created"]}'))
            self.stdout.write(self.style.SUCCESS(f'  Representatives updated: {stats["representatives_updated"]}'))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Error syncing state representatives: {e}'))
