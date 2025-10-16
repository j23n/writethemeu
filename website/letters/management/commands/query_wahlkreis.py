# ABOUTME: Query management command to find constituency by address.
# ABOUTME: Interactive tool for testing address-based constituency matching.

from django.core.management.base import BaseCommand
from letters.services.wahlkreis import WahlkreisResolver


class Command(BaseCommand):
    help = 'Find constituency (Wahlkreis) by address'

    def add_arguments(self, parser):
        parser.add_argument(
            'address',
            type=str,
            help='Full address string (e.g., "Unter den Linden 1, 10117 Berlin")'
        )

    def handle(self, *args, **options):
        address = options['address']

        try:
            # Use WahlkreisResolver to get full resolution
            resolver = WahlkreisResolver()
            result = resolver.resolve(address=address)

            if not result['federal_wahlkreis_number']:
                self.stdout.write(self.style.ERROR('Error: Could not resolve address to Wahlkreis'))
                return

            # Display Wahlkreis information
            self.stdout.write(self.style.SUCCESS('\n=== Wahlkreis Information ==='))
            self.stdout.write(f"Federal Wahlkreis: {result['federal_wahlkreis_number']}")

            if result['state_wahlkreis_number']:
                self.stdout.write(f"State Wahlkreis:   {result['state_wahlkreis_number']}")
            else:
                self.stdout.write("State Wahlkreis:   (not available for this state)")

            self.stdout.write(f"EU Region:         {result['eu_wahlkreis']}")

            # Display constituency information
            constituencies = result['constituencies']
            if constituencies:
                self.stdout.write(self.style.SUCCESS(f'\n=== Constituencies ({len(constituencies)}) ==='))
                for c in constituencies:
                    self.stdout.write(f"\n{c.scope}:")
                    self.stdout.write(f"  Name:       {c.name}")
                    self.stdout.write(f"  Parliament: {c.parliament_term.parliament.name}")
                    self.stdout.write(f"  Term:       {c.parliament_term.name}")
                    if c.wahlkreis_id:
                        self.stdout.write(f"  WK ID:      {c.wahlkreis_id}")

                    # Show number of active representatives
                    rep_count = c.representatives.filter(is_active=True).count()
                    self.stdout.write(f"  Reps:       {rep_count} active")
            else:
                self.stdout.write(self.style.WARNING('\nNo constituencies found'))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
            import traceback
            traceback.print_exc()
            return
