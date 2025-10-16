# ABOUTME: Query management command to find constituency by address or postal code.
# ABOUTME: Interactive tool for testing address-based constituency matching.

from django.core.management.base import BaseCommand
from letters.services.wahlkreis import WahlkreisResolver


class Command(BaseCommand):
    help = 'Find constituency (Wahlkreis) by address or postal code'

    def add_arguments(self, parser):
        parser.add_argument(
            '--street',
            type=str,
            help='Street name and number'
        )
        parser.add_argument(
            '--postal-code',
            type=str,
            help='Postal code (PLZ)',
            required=True
        )
        parser.add_argument(
            '--city',
            type=str,
            help='City name'
        )

    def handle(self, *args, **options):
        street = options.get('street')
        postal_code = options['postal_code']
        city = options.get('city')

        try:
            # Build address string
            address_parts = []
            if street:
                address_parts.append(street)
            if postal_code:
                address_parts.append(postal_code)
            if city:
                address_parts.append(city)

            address = ', '.join(address_parts)

            # Use WahlkreisResolver to get full resolution
            resolver = WahlkreisResolver()
            result = resolver.resolve(address=address)

            if not result['federal_wahlkreis_number']:
                self.stdout.write(self.style.ERROR('Error: Could not resolve address to Wahlkreis'))
                return

            # Display results
            self.stdout.write(self.style.SUCCESS(
                f"Federal Wahlkreis: {result['federal_wahlkreis_number']}"
            ))

            if result['state_wahlkreis_number']:
                self.stdout.write(self.style.SUCCESS(
                    f"State Wahlkreis: {result['state_wahlkreis_number']}"
                ))

            constituencies = result['constituencies']
            if constituencies:
                self.stdout.write(f"\nFound {len(constituencies)} constituencies:")
                for c in constituencies:
                    self.stdout.write(f"  - {c.scope}: {c.name}")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
            return
