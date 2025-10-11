"""
Management command to test address-based constituency matching.

This command tests the full pipeline:
  Address → Geocoding → Coordinates → Constituency → Representatives

Usage:
  # Test a single address
  uv run python manage.py test_matching \
    --street "Platz der Republik 1" \
    --postal-code "11011" \
    --city "Berlin"

  # Test all predefined addresses
  uv run python manage.py test_matching --test-all

  # Test specific addresses by index (1-based)
  uv run python manage.py test_matching --test-all --indices 1,5,10
"""

import time
from django.core.management.base import BaseCommand
from letters.services import AddressGeocoder, WahlkreisLocator, ConstituencyLocator
from letters.models import Representative


# Comprehensive test addresses covering all German states and various constituency types
TEST_ADDRESSES = [
    {
        'name': 'Bundestag (Berlin)',
        'street': 'Platz der Republik 1',
        'postal_code': '11011',
        'city': 'Berlin',
        'expected_state': 'Berlin'
    },
    {
        'name': 'Hamburg Rathaus',
        'street': 'Rathausmarkt 1',
        'postal_code': '20095',
        'city': 'Hamburg',
        'expected_state': 'Hamburg'
    },
    {
        'name': 'Marienplatz München (Bavaria)',
        'street': 'Marienplatz 1',
        'postal_code': '80331',
        'city': 'München',
        'expected_state': 'Bayern'
    },
    {
        'name': 'Kölner Dom (North Rhine-Westphalia)',
        'street': 'Domkloster 4',
        'postal_code': '50667',
        'city': 'Köln',
        'expected_state': 'Nordrhein-Westfalen'
    },
    {
        'name': 'Brandenburger Tor (Berlin)',
        'street': 'Pariser Platz',
        'postal_code': '10117',
        'city': 'Berlin',
        'expected_state': 'Berlin'
    },
    {
        'name': 'Römer Frankfurt (Hesse)',
        'street': 'Römerberg 27',
        'postal_code': '60311',
        'city': 'Frankfurt am Main',
        'expected_state': 'Hessen'
    },
    {
        'name': 'Schloss Neuschwanstein (Bavaria)',
        'street': 'Neuschwansteinstraße 20',
        'postal_code': '87645',
        'city': 'Schwangau',
        'expected_state': 'Bayern'
    },
    {
        'name': 'Landtag Stuttgart (Baden-Württemberg)',
        'street': 'Konrad-Adenauer-Straße 3',
        'postal_code': '70173',
        'city': 'Stuttgart',
        'expected_state': 'Baden-Württemberg'
    },
    {
        'name': 'Hannover Rathaus (Lower Saxony)',
        'street': 'Trammplatz 2',
        'postal_code': '30159',
        'city': 'Hannover',
        'expected_state': 'Niedersachsen'
    },
    {
        'name': 'Dresdner Frauenkirche (Saxony)',
        'street': 'Neumarkt',
        'postal_code': '01067',
        'city': 'Dresden',
        'expected_state': 'Sachsen'
    },
    {
        'name': 'Leipzig Hauptbahnhof (Saxony)',
        'street': 'Willy-Brandt-Platz 5',
        'postal_code': '04109',
        'city': 'Leipzig',
        'expected_state': 'Sachsen'
    },
    {
        'name': 'Erfurt Dom (Thuringia)',
        'street': 'Domstraße 1',
        'postal_code': '99084',
        'city': 'Erfurt',
        'expected_state': 'Thüringen'
    },
    {
        'name': 'Magdeburg Dom (Saxony-Anhalt)',
        'street': 'Am Dom 1',
        'postal_code': '39104',
        'city': 'Magdeburg',
        'expected_state': 'Sachsen-Anhalt'
    },
    {
        'name': 'Bremer Rathaus (Bremen)',
        'street': 'Am Markt 21',
        'postal_code': '28195',
        'city': 'Bremen',
        'expected_state': 'Bremen'
    },
    {
        'name': 'Kieler Rathaus (Schleswig-Holstein)',
        'street': 'Fleethörn 9',
        'postal_code': '24103',
        'city': 'Kiel',
        'expected_state': 'Schleswig-Holstein'
    },
    {
        'name': 'Potsdamer Stadtschloss (Brandenburg)',
        'street': 'Alter Markt',
        'postal_code': '14467',
        'city': 'Potsdam',
        'expected_state': 'Brandenburg'
    },
    {
        'name': 'Schweriner Schloss (Mecklenburg-Vorpommern)',
        'street': 'Lennéstraße 1',
        'postal_code': '19053',
        'city': 'Schwerin',
        'expected_state': 'Mecklenburg-Vorpommern'
    },
    {
        'name': 'Saarbrücker Schloss (Saarland)',
        'street': 'Schloßplatz',
        'postal_code': '66119',
        'city': 'Saarbrücken',
        'expected_state': 'Saarland'
    },
    {
        'name': 'Düsseldorf Landtag (North Rhine-Westphalia)',
        'street': 'Platz des Landtags 1',
        'postal_code': '40221',
        'city': 'Düsseldorf',
        'expected_state': 'Nordrhein-Westfalen'
    },
    {
        'name': 'Heidelberg Schloss (Baden-Württemberg)',
        'street': 'Schlosshof 1',
        'postal_code': '69117',
        'city': 'Heidelberg',
        'expected_state': 'Baden-Württemberg'
    },
]


class Command(BaseCommand):
    help = 'Test address-based constituency matching with real German addresses'

    def __init__(self):
        super().__init__()
        self.total_tests = 0
        self.successful_tests = 0
        self.failed_tests = 0
        self.cache_hits = 0
        self.total_time = 0.0
        self.lookup_times = []

    def add_arguments(self, parser):
        parser.add_argument(
            '--street',
            type=str,
            help='Street name and number for single address test'
        )
        parser.add_argument(
            '--postal-code',
            type=str,
            help='Postal code (PLZ) for single address test'
        )
        parser.add_argument(
            '--city',
            type=str,
            help='City name for single address test'
        )
        parser.add_argument(
            '--test-all',
            action='store_true',
            help='Test all predefined German addresses'
        )
        parser.add_argument(
            '--indices',
            type=str,
            help='Comma-separated indices of test addresses to run (1-based, e.g., "1,5,10")'
        )

    def handle(self, *args, **options):
        """Main command handler."""
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS('Address-Based Constituency Matching Test'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write('')

        if options['test_all']:
            # Test all or specific predefined addresses
            self.test_predefined_addresses(options.get('indices'))
        elif options['street'] and options['postal_code'] and options['city']:
            # Test single custom address
            self.test_single_address(
                name='Custom Address',
                street=options['street'],
                postal_code=options['postal_code'],
                city=options['city']
            )
        else:
            self.stdout.write(self.style.ERROR(
                'Error: Either provide --street, --postal-code, and --city for a single test, '
                'or use --test-all for predefined tests.'
            ))
            return

        # Display summary statistics
        self.display_summary()

    def test_predefined_addresses(self, indices_str=None):
        """Test predefined addresses, optionally filtering by indices."""
        addresses_to_test = TEST_ADDRESSES

        # Filter by indices if provided
        if indices_str:
            try:
                indices = [int(idx.strip()) - 1 for idx in indices_str.split(',')]
                addresses_to_test = [TEST_ADDRESSES[i] for i in indices if 0 <= i < len(TEST_ADDRESSES)]
                if not addresses_to_test:
                    self.stdout.write(self.style.ERROR('No valid indices provided'))
                    return
            except (ValueError, IndexError) as e:
                self.stdout.write(self.style.ERROR(f'Invalid indices: {e}'))
                return

        self.stdout.write(f'Testing {len(addresses_to_test)} address(es)\n')

        for i, address in enumerate(addresses_to_test, 1):
            self.stdout.write(self.style.WARNING(f'\n[{i}/{len(addresses_to_test)}] Testing: {address["name"]}'))
            self.test_single_address(**address)
            self.stdout.write('')

    def test_single_address(self, name, street, postal_code, city, expected_state=None):
        """Test a single address through the full pipeline."""
        self.total_tests += 1
        start_time = time.time()

        # Display address details
        self.stdout.write(f'  Address: {street}, {postal_code} {city}')
        if expected_state:
            self.stdout.write(f'  Expected State: {expected_state}')

        try:
            # Initialize services
            geocoder = AddressGeocoder()
            wahlkreis_locator = WahlkreisLocator()
            constituency_locator = ConstituencyLocator()

            # Step 1: Geocode address
            lat, lon, success, error = geocoder.geocode(street, postal_code, city)

            if not success:
                self.stdout.write(self.style.ERROR(f'  ✗ Geocoding failed: {error}'))
                self.failed_tests += 1
                elapsed = time.time() - start_time
                self.lookup_times.append(elapsed)
                self.stdout.write(f'  Duration: {elapsed:.2f}s')
                return

            # Check if result was cached
            from letters.models import GeocodeCache
            cache_key = geocoder._generate_cache_key(street, postal_code, city, 'DE')
            cached_entry = GeocodeCache.objects.filter(address_hash=cache_key).first()
            is_cached = cached_entry is not None
            if is_cached:
                self.cache_hits += 1

            self.stdout.write(self.style.SUCCESS(f'  ✓ Geocoded: {lat:.4f}, {lon:.4f}' + (' (cached)' if is_cached else '')))

            # Step 2: Find constituency
            constituency_result = wahlkreis_locator.locate(lat, lon)

            if not constituency_result:
                self.stdout.write(self.style.ERROR('  ✗ Constituency not found for coordinates'))
                self.failed_tests += 1
                elapsed = time.time() - start_time
                self.lookup_times.append(elapsed)
                self.stdout.write(f'  Duration: {elapsed:.2f}s')
                return

            wkr_nr, wkr_name, land_name = constituency_result
            self.stdout.write(self.style.SUCCESS(f'  ✓ Constituency: WK {wkr_nr} - {wkr_name} ({land_name})'))

            # Verify state if expected
            if expected_state and land_name:
                # Normalize state names for comparison
                from letters.constants import normalize_german_state
                normalized_expected = normalize_german_state(expected_state)
                normalized_actual = normalize_german_state(land_name)

                if normalized_expected == normalized_actual:
                    self.stdout.write(self.style.SUCCESS(f'  ✓ State matches expected: {land_name}'))
                else:
                    self.stdout.write(self.style.WARNING(
                        f'  ⚠ State mismatch: expected {expected_state}, got {land_name}'
                    ))

            # Step 3: Find representatives
            representatives = constituency_locator.locate(street=street, postal_code=postal_code, city=city)

            if representatives:
                self.stdout.write(self.style.SUCCESS(f'  ✓ Representatives found: {len(representatives)}'))
                for rep in representatives[:5]:  # Limit to first 5
                    constituency = rep.primary_constituency
                    constituency_label = constituency.name if constituency else rep.parliament.name
                    self.stdout.write(f'    - {rep.full_name} ({rep.party}) - {constituency_label}')
                if len(representatives) > 5:
                    self.stdout.write(f'    ... and {len(representatives) - 5} more')
            else:
                self.stdout.write(self.style.WARNING('  ⚠ No representatives found (database may be empty)'))

            self.successful_tests += 1

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  ✗ Error: {str(e)}'))
            self.failed_tests += 1

        # Display timing
        elapsed = time.time() - start_time
        self.lookup_times.append(elapsed)
        self.total_time += elapsed
        self.stdout.write(f'  Duration: {elapsed:.2f}s')

    def display_summary(self):
        """Display summary statistics."""
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(self.style.SUCCESS('Summary Statistics'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
        self.stdout.write(f'Total addresses tested: {self.total_tests}')
        self.stdout.write(self.style.SUCCESS(f'Successful matches: {self.successful_tests}'))
        if self.failed_tests > 0:
            self.stdout.write(self.style.ERROR(f'Failed matches: {self.failed_tests}'))
        else:
            self.stdout.write(f'Failed matches: {self.failed_tests}')

        if self.total_tests > 0:
            success_rate = (self.successful_tests / self.total_tests) * 100
            self.stdout.write(f'Success rate: {success_rate:.1f}%')

        if self.lookup_times:
            avg_time = sum(self.lookup_times) / len(self.lookup_times)
            min_time = min(self.lookup_times)
            max_time = max(self.lookup_times)
            self.stdout.write(f'Average lookup time: {avg_time:.2f}s')
            self.stdout.write(f'Min/Max lookup time: {min_time:.2f}s / {max_time:.2f}s')

        if self.total_tests > 0:
            cache_hit_rate = (self.cache_hits / self.total_tests) * 100
            self.stdout.write(f'Cache hit rate: {cache_hit_rate:.1f}% ({self.cache_hits}/{self.total_tests})')

        self.stdout.write(f'Total time: {self.total_time:.2f}s')
        self.stdout.write(self.style.SUCCESS('=' * 80))
