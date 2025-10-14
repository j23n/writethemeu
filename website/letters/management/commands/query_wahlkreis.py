# ABOUTME: Query management command to find constituency by address or postal code.
# ABOUTME: Interactive tool for testing address-based constituency matching.

from django.core.management.base import BaseCommand
from letters.services import AddressGeocoder, WahlkreisLocator, ConstituencyLocator


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
            # Try full address geocoding if all parts provided
            if street and city:
                geocoder = AddressGeocoder()
                lat, lon, success, error = geocoder.geocode(street, postal_code, city)

                if not success:
                    self.stdout.write(self.style.ERROR(f'Error: Could not geocode address: {error}'))
                    return

                locator = WahlkreisLocator()
                result = locator.locate(lat, lon)

                if not result:
                    self.stdout.write('No constituency found for these coordinates')
                    return

                wkr_nr, wkr_name, land_name = result
                self.stdout.write(f'WK {wkr_nr:03d} - {wkr_name} ({land_name})')

            # Fallback to PLZ prefix lookup
            else:
                plz_prefix = postal_code[:2]
                state_name = ConstituencyLocator.STATE_BY_PLZ_PREFIX.get(plz_prefix)

                if state_name:
                    self.stdout.write(f'State: {state_name} (from postal code prefix)')
                else:
                    self.stdout.write('Error: Could not determine state from postal code')

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
            return
