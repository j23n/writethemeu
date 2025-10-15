"""
Management command to sync representatives from Abgeordnetenwatch API.

Uses the real Abgeordnetenwatch.de API (CC0 licensed) to sync:
- Federal level: Bundestag representatives
- State level: Landtag representatives
- Local level: Not yet available in API
"""

import logging
from django.core.management.base import BaseCommand
from letters.services import RepresentativeSyncService

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

        try:
            stats = RepresentativeSyncService.sync(level=level, state=state_filter, dry_run=dry_run)
            for key, value in stats.items():
                self.stdout.write(self.style.SUCCESS(f"  {key.replace('_', ' ').title()}: {value}"))
            self.stdout.write(self.style.SUCCESS('Sync completed successfully'))
        except Exception:
            logger.exception("Sync failed")
            raise
