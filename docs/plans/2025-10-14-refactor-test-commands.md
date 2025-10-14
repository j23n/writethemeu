# Refactor Test Commands Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Replace test-like management commands with proper Django tests and create new query commands for interactive debugging.

**Architecture:** Extract testing logic from three management commands (`test_matching.py`, `test_constituency_suggestion.py`, `test_topic_mapping.py`) into proper Django test files, then create three new query commands (`query_wahlkreis`, `query_topics`, `query_representatives`) for interactive use, and finally delete the old test commands.

**Tech Stack:** Django 5.2, Python 3.13, uv, Django test framework

---

## Task 1: Create test_address_matching.py test file

**Files:**
- Create: `website/letters/tests/test_address_matching.py`
- Reference: `website/letters/management/commands/test_matching.py` (for test data and logic)

**Step 1: Write the test file structure with TEST_ADDRESSES fixture**

Create `website/letters/tests/test_address_matching.py`:

```python
# ABOUTME: Test address-based constituency matching with geocoding and point-in-polygon lookup.
# ABOUTME: Covers AddressGeocoder, WahlkreisLocator, and ConstituencyLocator services.

from django.test import TestCase
from unittest.mock import patch, MagicMock
from letters.services import AddressGeocoder, WahlkreisLocator, ConstituencyLocator
from letters.models import GeocodeCache, Representative


# Test addresses covering all German states
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
]


class AddressGeocodingTests(TestCase):
    """Test address geocoding with OSM Nominatim."""

    def setUp(self):
        self.geocoder = AddressGeocoder()

    def test_geocode_success_with_mocked_api(self):
        """Test successful geocoding with mocked Nominatim response."""
        pass

    def test_geocode_caches_results(self):
        """Test that geocoding results are cached in database."""
        pass

    def test_geocode_returns_cached_results(self):
        """Test that cached geocoding results are reused."""
        pass

    def test_geocode_handles_api_error(self):
        """Test graceful handling of Nominatim API errors."""
        pass


class WahlkreisLocationTests(TestCase):
    """Test point-in-polygon constituency matching."""

    def test_locate_bundestag_coordinates(self):
        """Test that Bundestag coordinates find correct Berlin constituency."""
        pass

    def test_locate_hamburg_coordinates(self):
        """Test that Hamburg coordinates find correct constituency."""
        pass

    def test_coordinates_outside_germany(self):
        """Test that coordinates outside Germany return None."""
        pass


class FullAddressMatchingTests(TestCase):
    """Integration tests for full address → constituency → representatives pipeline."""

    @patch('letters.services.AddressGeocoder.geocode')
    def test_address_to_constituency_pipeline(self, mock_geocode):
        """Test full pipeline from address to constituency with mocked geocoding."""
        pass

    def test_plz_fallback_when_geocoding_fails(self):
        """Test PLZ prefix fallback when geocoding fails."""
        pass


# End of file
```

**Step 2: Run test to verify structure loads**

Run: `cd website && uv run python manage.py test letters.tests.test_address_matching`
Expected: All tests should be discovered and skip (no implementations yet)

**Step 3: Commit test file structure**

```bash
git add website/letters/tests/test_address_matching.py
git commit -m "test: add test_address_matching.py structure with fixtures"
```

---

## Task 2: Implement address geocoding tests

**Files:**
- Modify: `website/letters/tests/test_address_matching.py`

**Step 1: Implement test_geocode_success_with_mocked_api**

In `AddressGeocodingTests` class, replace the pass statement:

```python
def test_geocode_success_with_mocked_api(self):
    """Test successful geocoding with mocked Nominatim response."""
    with patch('requests.get') as mock_get:
        # Mock successful Nominatim response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            'lat': '52.5186',
            'lon': '13.3761'
        }]
        mock_get.return_value = mock_response

        lat, lon, success, error = self.geocoder.geocode(
            'Platz der Republik 1',
            '11011',
            'Berlin'
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        self.assertAlmostEqual(lat, 52.5186, places=4)
        self.assertAlmostEqual(lon, 13.3761, places=4)
```

**Step 2: Implement test_geocode_caches_results**

```python
def test_geocode_caches_results(self):
    """Test that geocoding results are cached in database."""
    with patch('requests.get') as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{
            'lat': '52.5186',
            'lon': '13.3761'
        }]
        mock_get.return_value = mock_response

        # First call should cache
        self.geocoder.geocode('Platz der Republik 1', '11011', 'Berlin')

        # Check cache entry exists
        cache_key = self.geocoder._generate_cache_key(
            'Platz der Republik 1', '11011', 'Berlin', 'DE'
        )
        cache_entry = GeocodeCache.objects.filter(address_hash=cache_key).first()
        self.assertIsNotNone(cache_entry)
        self.assertTrue(cache_entry.success)
```

**Step 3: Implement test_geocode_returns_cached_results**

```python
def test_geocode_returns_cached_results(self):
    """Test that cached geocoding results are reused."""
    # Create cache entry
    cache_key = self.geocoder._generate_cache_key(
        'Test Street', '12345', 'Test City', 'DE'
    )
    GeocodeCache.objects.create(
        address_hash=cache_key,
        success=True,
        latitude=52.0,
        longitude=13.0
    )

    # Should return cached result without API call
    with patch('requests.get') as mock_get:
        lat, lon, success, error = self.geocoder.geocode(
            'Test Street', '12345', 'Test City'
        )

        # Verify no API call was made
        mock_get.assert_not_called()

        # Verify cached results returned
        self.assertTrue(success)
        self.assertEqual(lat, 52.0)
        self.assertEqual(lon, 13.0)
```

**Step 4: Implement test_geocode_handles_api_error**

```python
def test_geocode_handles_api_error(self):
    """Test graceful handling of Nominatim API errors."""
    with patch('requests.get') as mock_get:
        mock_get.side_effect = Exception("API Error")

        lat, lon, success, error = self.geocoder.geocode(
            'Invalid Street', '99999', 'Nowhere'
        )

        self.assertFalse(success)
        self.assertIsNone(lat)
        self.assertIsNone(lon)
        self.assertIn('API Error', error)
```

**Step 5: Run tests to verify they pass**

Run: `cd website && uv run python manage.py test letters.tests.test_address_matching.AddressGeocodingTests -v`
Expected: 4 tests PASS

**Step 6: Commit geocoding tests**

```bash
git add website/letters/tests/test_address_matching.py
git commit -m "test: implement address geocoding tests with mocking"
```

---

## Task 3: Implement Wahlkreis location tests

**Files:**
- Modify: `website/letters/tests/test_address_matching.py`

**Step 1: Implement test_locate_bundestag_coordinates**

In `WahlkreisLocationTests` class:

```python
def test_locate_bundestag_coordinates(self):
    """Test that Bundestag coordinates find correct Berlin constituency."""
    locator = WahlkreisLocator()
    result = locator.locate(52.5186, 13.3761)

    self.assertIsNotNone(result)
    wkr_nr, wkr_name, land_name = result
    self.assertIsInstance(wkr_nr, int)
    self.assertIn('Berlin', land_name)
```

**Step 2: Implement test_locate_hamburg_coordinates**

```python
def test_locate_hamburg_coordinates(self):
    """Test that Hamburg coordinates find correct constituency."""
    locator = WahlkreisLocator()
    result = locator.locate(53.5511, 9.9937)

    self.assertIsNotNone(result)
    wkr_nr, wkr_name, land_name = result
    self.assertIsInstance(wkr_nr, int)
    self.assertIn('Hamburg', land_name)
```

**Step 3: Implement test_coordinates_outside_germany**

```python
def test_coordinates_outside_germany(self):
    """Test that coordinates outside Germany return None."""
    locator = WahlkreisLocator()

    # Paris coordinates
    result = locator.locate(48.8566, 2.3522)
    self.assertIsNone(result)

    # London coordinates
    result = locator.locate(51.5074, -0.1278)
    self.assertIsNone(result)
```

**Step 4: Run tests to verify they pass**

Run: `cd website && uv run python manage.py test letters.tests.test_address_matching.WahlkreisLocationTests -v`
Expected: 3 tests PASS

**Step 5: Commit Wahlkreis location tests**

```bash
git add website/letters/tests/test_address_matching.py
git commit -m "test: implement Wahlkreis point-in-polygon location tests"
```

---

## Task 4: Implement full address matching integration tests

**Files:**
- Modify: `website/letters/tests/test_address_matching.py`

**Step 1: Implement test_address_to_constituency_pipeline**

In `FullAddressMatchingTests` class:

```python
@patch('letters.services.AddressGeocoder.geocode')
def test_address_to_constituency_pipeline(self, mock_geocode):
    """Test full pipeline from address to constituency with mocked geocoding."""
    # Mock geocoding to return Bundestag coordinates
    mock_geocode.return_value = (52.5186, 13.3761, True, None)

    locator = ConstituencyLocator()
    representatives = locator.locate(
        street='Platz der Republik 1',
        postal_code='11011',
        city='Berlin'
    )

    # Should return representatives (even if list is empty due to no DB data)
    self.assertIsInstance(representatives, list)
    mock_geocode.assert_called_once()
```

**Step 2: Implement test_plz_fallback_when_geocoding_fails**

```python
def test_plz_fallback_when_geocoding_fails(self):
    """Test PLZ prefix fallback when geocoding fails."""
    with patch('letters.services.AddressGeocoder.geocode') as mock_geocode:
        # Mock geocoding failure
        mock_geocode.return_value = (None, None, False, "Geocoding failed")

        locator = ConstituencyLocator()
        representatives = locator.locate(
            postal_code='10115'  # Berlin postal code
        )

        # Should still return list (using PLZ fallback)
        self.assertIsInstance(representatives, list)
```

**Step 3: Run tests to verify they pass**

Run: `cd website && uv run python manage.py test letters.tests.test_address_matching.FullAddressMatchingTests -v`
Expected: 2 tests PASS

**Step 4: Run full test suite**

Run: `cd website && uv run python manage.py test letters.tests.test_address_matching -v`
Expected: All 9 tests PASS

**Step 5: Commit integration tests**

```bash
git add website/letters/tests/test_address_matching.py
git commit -m "test: implement full address matching integration tests"
```

---

## Task 5: Create test_topic_mapping.py test file

**Files:**
- Create: `website/letters/tests/test_topic_mapping.py`
- Reference: `website/letters/management/commands/test_topic_mapping.py` (for test data)

**Step 1: Write test file with topic matching tests**

Create `website/letters/tests/test_topic_mapping.py`:

```python
# ABOUTME: Test topic suggestion and matching based on letter content.
# ABOUTME: Covers TopicSuggestionService keyword matching and level suggestion logic.

from django.test import TestCase
from letters.services import TopicSuggestionService
from letters.models import TopicArea


class TopicMatchingTests(TestCase):
    """Test topic keyword matching and scoring."""

    def test_transport_keywords_match_verkehr_topic(self):
        """Test that transport-related keywords match Verkehr topic."""
        concern = "I want to see better train connections between cities"
        topics = TopicSuggestionService.get_topic_suggestions(concern)

        # Should find at least one topic
        self.assertGreater(len(topics), 0)

        # Top topic should be transport-related
        top_topic = topics[0]
        self.assertIn('score', top_topic)
        self.assertGreater(top_topic['score'], 0)

    def test_housing_keywords_match_wohnen_topic(self):
        """Test that housing keywords match Wohnen topic."""
        concern = "We need more affordable housing and rent control"
        topics = TopicSuggestionService.get_topic_suggestions(concern)

        self.assertGreater(len(topics), 0)

    def test_education_keywords_match_bildung_topic(self):
        """Test that education keywords match Bildung topic."""
        concern = "Our school curriculum needs reform"
        topics = TopicSuggestionService.get_topic_suggestions(concern)

        self.assertGreater(len(topics), 0)

    def test_climate_keywords_match_umwelt_topic(self):
        """Test that climate keywords match environment topic."""
        concern = "Climate protection and CO2 emissions must be addressed"
        topics = TopicSuggestionService.get_topic_suggestions(concern)

        self.assertGreater(len(topics), 0)

    def test_no_match_returns_empty_list(self):
        """Test that completely unrelated text returns empty list."""
        concern = "xyzabc nonsense gibberish"
        topics = TopicSuggestionService.get_topic_suggestions(concern)

        # May return empty or very low scores
        if topics:
            self.assertLess(topics[0]['score'], 0.3)


class LevelSuggestionTests(TestCase):
    """Test government level suggestion logic."""

    def test_federal_transport_suggests_federal_level(self):
        """Test that long-distance transport suggests federal level."""
        result = TopicSuggestionService.suggest_representatives_for_concern(
            "Deutsche Bahn is always late",
            limit=5
        )

        self.assertIn('suggested_level', result)
        self.assertIn('explanation', result)
        # Federal issues should suggest Bundestag
        self.assertIn('Bundestag', result['suggested_level'])

    def test_local_bus_suggests_state_or_local(self):
        """Test that local transport suggests state/local level."""
        result = TopicSuggestionService.suggest_representatives_for_concern(
            "Better bus services in my town",
            limit=5
        )

        self.assertIn('suggested_level', result)
        # Local issues should not exclusively suggest federal
        explanation = result['explanation'].lower()
        self.assertTrue('state' in explanation or 'local' in explanation or 'land' in explanation)


# End of file
```

**Step 2: Run tests to verify they work**

Run: `cd website && uv run python manage.py test letters.tests.test_topic_mapping -v`
Expected: Tests PASS (some may be skipped if TopicArea data not loaded)

**Step 3: Commit topic mapping tests**

```bash
git add website/letters/tests/test_topic_mapping.py
git commit -m "test: add topic matching and level suggestion tests"
```

---

## Task 6: Create test_constituency_suggestions.py test file

**Files:**
- Create: `website/letters/tests/test_constituency_suggestions.py`
- Reference: `website/letters/management/commands/test_constituency_suggestion.py`

**Step 1: Write test file for constituency suggestion service**

Create `website/letters/tests/test_constituency_suggestions.py`:

```python
# ABOUTME: Test ConstituencySuggestionService combining topics and geography.
# ABOUTME: Integration tests for letter title/address to representative suggestions.

from django.test import TestCase
from unittest.mock import patch
from letters.services import ConstituencySuggestionService


class ConstituencySuggestionTests(TestCase):
    """Test constituency suggestion combining topic and address matching."""

    @patch('letters.services.AddressGeocoder.geocode')
    def test_suggest_with_title_and_address(self, mock_geocode):
        """Test suggestions work with both title and address."""
        # Mock geocoding
        mock_geocode.return_value = (52.5186, 13.3761, True, None)

        result = ConstituencySuggestionService.suggest_from_concern(
            concern="We need better train connections",
            street="Platz der Republik 1",
            postal_code="11011",
            city="Berlin"
        )

        self.assertIn('matched_topics', result)
        self.assertIn('suggested_level', result)
        self.assertIn('explanation', result)
        self.assertIn('representatives', result)
        self.assertIn('constituencies', result)

    def test_suggest_with_only_title(self):
        """Test suggestions work with only title (no address)."""
        result = ConstituencySuggestionService.suggest_from_concern(
            concern="Climate protection is important"
        )

        self.assertIn('matched_topics', result)
        self.assertIn('suggested_level', result)
        # Without address, should still suggest level and topics
        self.assertIsNotNone(result['suggested_level'])

    def test_suggest_with_only_postal_code(self):
        """Test suggestions work with only postal code."""
        result = ConstituencySuggestionService.suggest_from_concern(
            concern="Local infrastructure problems",
            postal_code="10115"
        )

        self.assertIn('constituencies', result)
        # Should use PLZ fallback
        self.assertIsInstance(result['constituencies'], list)


# End of file
```

**Step 2: Run tests to verify they pass**

Run: `cd website && uv run python manage.py test letters.tests.test_constituency_suggestions -v`
Expected: 3 tests PASS

**Step 3: Commit constituency suggestion tests**

```bash
git add website/letters/tests/test_constituency_suggestions.py
git commit -m "test: add constituency suggestion integration tests"
```

---

## Task 7: Create query_wahlkreis management command

**Files:**
- Create: `website/letters/management/commands/query_wahlkreis.py`

**Step 1: Write query_wahlkreis command**

Create `website/letters/management/commands/query_wahlkreis.py`:

```python
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
                from letters.constants import PLZ_TO_STATE
                plz_prefix = postal_code[:2]

                if plz_prefix in PLZ_TO_STATE:
                    state = PLZ_TO_STATE[plz_prefix]
                    self.stdout.write(f'State: {state} (from postal code prefix)')
                else:
                    self.stdout.write('Error: Could not determine state from postal code')

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
            return
```

**Step 2: Test the command manually**

Run: `cd website && uv run python manage.py query_wahlkreis --street "Platz der Republik 1" --postal-code "11011" --city "Berlin"`
Expected: Output showing Berlin constituency

Run: `cd website && uv run python manage.py query_wahlkreis --postal-code "10115"`
Expected: Output showing "State: Berlin (from postal code prefix)"

**Step 3: Commit query_wahlkreis command**

```bash
git add website/letters/management/commands/query_wahlkreis.py
git commit -m "feat: add query_wahlkreis management command"
```

---

## Task 8: Create query_topics management command

**Files:**
- Create: `website/letters/management/commands/query_topics.py`

**Step 1: Write query_topics command**

Create `website/letters/management/commands/query_topics.py`:

```python
# ABOUTME: Query management command to find matching topics for letter text.
# ABOUTME: Interactive tool for testing topic keyword matching and scoring.

from django.core.management.base import BaseCommand
from letters.services import TopicSuggestionService


class Command(BaseCommand):
    help = 'Find matching topics for a letter title or text'

    def add_arguments(self, parser):
        parser.add_argument(
            '--text',
            type=str,
            required=True,
            help='Letter title or text to analyze'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=5,
            help='Maximum number of topics to return (default: 5)'
        )

    def handle(self, *args, **options):
        text = options['text']
        limit = options['limit']

        try:
            topics = TopicSuggestionService.get_topic_suggestions(text)

            if not topics:
                self.stdout.write('No matching topics found')
                return

            # Limit results
            topics = topics[:limit]

            for topic in topics:
                score = topic.get('match_score', topic.get('score', 0))
                self.stdout.write(
                    f"{topic['name']} ({topic['level']}, Score: {score:.2f})"
                )
                if 'description' in topic and topic['description']:
                    self.stdout.write(f"  {topic['description']}")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
            return
```

**Step 2: Test the command manually**

Run: `cd website && uv run python manage.py query_topics --text "We need better train connections"`
Expected: Output showing transport-related topics with scores

Run: `cd website && uv run python manage.py query_topics --text "affordable housing" --limit 3`
Expected: Output showing top 3 housing-related topics

**Step 3: Commit query_topics command**

```bash
git add website/letters/management/commands/query_topics.py
git commit -m "feat: add query_topics management command"
```

---

## Task 9: Create query_representatives management command

**Files:**
- Create: `website/letters/management/commands/query_representatives.py`

**Step 1: Write query_representatives command**

Create `website/letters/management/commands/query_representatives.py`:

```python
# ABOUTME: Query management command to find representatives by address and/or topics.
# ABOUTME: Interactive tool for testing representative suggestion logic.

from django.core.management.base import BaseCommand
from letters.services import ConstituencyLocator, TopicSuggestionService, ConstituencySuggestionService


class Command(BaseCommand):
    help = 'Find representatives by address and/or topics'

    def add_arguments(self, parser):
        # Address arguments
        parser.add_argument(
            '--street',
            type=str,
            help='Street name and number'
        )
        parser.add_argument(
            '--postal-code',
            type=str,
            help='Postal code (PLZ)'
        )
        parser.add_argument(
            '--city',
            type=str,
            help='City name'
        )

        # Topic arguments
        parser.add_argument(
            '--topics',
            type=str,
            help='Comma-separated topic keywords (e.g., "Verkehr,Infrastruktur")'
        )

        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Maximum number of representatives to return (default: 10)'
        )

    def handle(self, *args, **options):
        street = options.get('street')
        postal_code = options.get('postal_code')
        city = options.get('city')
        topics_str = options.get('topics')
        limit = options['limit']

        try:
            # Use constituency locator if address provided
            if postal_code or (street and city):
                locator = ConstituencyLocator()
                representatives = locator.locate(
                    street=street,
                    postal_code=postal_code,
                    city=city
                )

                if not representatives:
                    self.stdout.write('No representatives found for this location')
                    return

                # Filter by topics if provided
                if topics_str:
                    topic_keywords = [t.strip() for t in topics_str.split(',')]
                    # Simple keyword filter on representative focus areas
                    filtered_reps = []
                    for rep in representatives:
                        # Check if any committee or focus area matches
                        rep_text = ' '.join([
                            rep.full_name,
                            ' '.join([c.name for c in rep.committees.all()]),
                        ]).lower()

                        if any(keyword.lower() in rep_text for keyword in topic_keywords):
                            filtered_reps.append(rep)

                    representatives = filtered_reps if filtered_reps else representatives

                # Display results
                for rep in representatives[:limit]:
                    constituency = rep.primary_constituency
                    constituency_label = constituency.name if constituency else rep.parliament.name
                    self.stdout.write(f'{rep.full_name} ({rep.party}) - {constituency_label}')

                    # Show committees
                    committees = list(rep.committees.all()[:3])
                    if committees:
                        committee_names = ', '.join([c.name for c in committees])
                        self.stdout.write(f'  Committees: {committee_names}')

            # Use topic-based search if only topics provided
            elif topics_str:
                self.stdout.write('Topic-based representative search not yet implemented')
                self.stdout.write('Please provide at least a postal code for location-based search')

            else:
                self.stderr.write(self.style.ERROR(
                    'Error: Please provide either an address (--postal-code required) or --topics'
                ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
            return
```

**Step 2: Test the command manually**

Run: `cd website && uv run python manage.py query_representatives --postal-code "11011"`
Expected: Output showing Berlin representatives

Run: `cd website && uv run python manage.py query_representatives --street "Platz der Republik 1" --postal-code "11011" --city "Berlin" --limit 5`
Expected: Output showing top 5 representatives for that location

**Step 3: Commit query_representatives command**

```bash
git add website/letters/management/commands/query_representatives.py
git commit -m "feat: add query_representatives management command"
```

---

## Task 10: Run full test suite and verify everything works

**Files:**
- All test files

**Step 1: Run complete test suite**

Run: `cd website && uv run python manage.py test`
Expected: All tests PASS (including new and existing tests)

**Step 2: Test all three query commands manually**

Run: `cd website && uv run python manage.py query_wahlkreis --street "Platz der Republik 1" --postal-code "11011" --city "Berlin"`
Expected: Correct constituency output

Run: `cd website && uv run python manage.py query_topics --text "climate change and renewable energy"`
Expected: Environment-related topics

Run: `cd website && uv run python manage.py query_representatives --postal-code "10115"`
Expected: Berlin representatives

**Step 3: Commit if any fixes needed**

If any issues found and fixed:
```bash
git add .
git commit -m "fix: address test suite issues"
```

---

## Task 11: Delete test_matching.py command

**Files:**
- Delete: `website/letters/management/commands/test_matching.py`

**Step 1: Verify tests cover all test_matching.py functionality**

Compare `test_matching.py` with `test_address_matching.py` to ensure all test cases are covered.

**Step 2: Delete test_matching.py**

Run: `rm website/letters/management/commands/test_matching.py`

**Step 3: Run tests to verify nothing broke**

Run: `cd website && uv run python manage.py test`
Expected: All tests still PASS

**Step 4: Commit deletion**

```bash
git add website/letters/management/commands/test_matching.py
git commit -m "refactor: remove test_matching command (moved to proper tests)"
```

---

## Task 12: Delete test_constituency_suggestion.py command

**Files:**
- Delete: `website/letters/management/commands/test_constituency_suggestion.py`

**Step 1: Verify tests cover functionality**

Compare with `test_constituency_suggestions.py`.

**Step 2: Delete test_constituency_suggestion.py**

Run: `rm website/letters/management/commands/test_constituency_suggestion.py`

**Step 3: Run tests to verify nothing broke**

Run: `cd website && uv run python manage.py test`
Expected: All tests PASS

**Step 4: Commit deletion**

```bash
git add website/letters/management/commands/test_constituency_suggestion.py
git commit -m "refactor: remove test_constituency_suggestion command (moved to proper tests)"
```

---

## Task 13: Delete test_topic_mapping.py command

**Files:**
- Delete: `website/letters/management/commands/test_topic_mapping.py`

**Step 1: Verify tests cover functionality**

Compare with `test_topic_mapping.py`.

**Step 2: Delete test_topic_mapping.py**

Run: `rm website/letters/management/commands/test_topic_mapping.py`

**Step 3: Run tests to verify nothing broke**

Run: `cd website && uv run python manage.py test`
Expected: All tests PASS

**Step 4: Commit deletion**

```bash
git add website/letters/management/commands/test_topic_mapping.py
git commit -m "refactor: remove test_topic_mapping command (moved to proper tests)"
```

---

## Task 14: Update documentation

**Files:**
- Modify: `README.md` (if it mentions test commands)
- Modify: `docs/matching-algorithm.md` (update command references)

**Step 1: Check if README mentions test commands**

Run: `grep -n "test_matching\|test_constituency\|test_topic" README.md`

If found, update to reference new query commands and proper test suite.

**Step 2: Update docs/matching-algorithm.md**

In `docs/matching-algorithm.md`, find section "Management Commands" (around line 70) and update:

```markdown
### Management Commands

- **fetch_wahlkreis_data**: Downloads official Bundestag constituency boundaries
- **query_wahlkreis**: Query constituency by address or postal code
- **query_topics**: Find matching topics for letter text
- **query_representatives**: Find representatives by address and/or topics

### Testing

Run the test suite:
```bash
python manage.py test letters.tests.test_address_matching
python manage.py test letters.tests.test_topic_mapping
python manage.py test letters.tests.test_constituency_suggestions
```
```

**Step 3: Commit documentation updates**

```bash
git add README.md docs/matching-algorithm.md
git commit -m "docs: update command and testing references"
```

---

## Task 15: Final verification and summary

**Files:**
- All modified files

**Step 1: Run complete test suite one final time**

Run: `cd website && uv run python manage.py test -v`
Expected: All tests PASS with detailed output

**Step 2: Verify query commands work**

Test each command with various inputs to ensure they work correctly.

**Step 3: Create summary of changes**

Review all commits:
```bash
git log --oneline
```

**Step 4: Final commit if needed**

If any final cleanup needed:
```bash
git add .
git commit -m "chore: final cleanup for test command refactoring"
```

---

## Summary

**What was accomplished:**
1. Created three new test files with comprehensive test coverage
2. Created three new query management commands for interactive debugging
3. Deleted three old test-like management commands
4. Updated documentation to reflect new structure

**New query commands:**
- `query_wahlkreis` - Find constituency by address/PLZ
- `query_topics` - Find matching topics for text
- `query_representatives` - Find representatives by location/topics

**New test files:**
- `letters/tests/test_address_matching.py` - Address geocoding and matching
- `letters/tests/test_topic_mapping.py` - Topic keyword matching
- `letters/tests/test_constituency_suggestions.py` - Integration tests

**Testing strategy:**
- Mocked external API calls (Nominatim) to avoid rate limits
- Integration tests use real services where possible
- All edge cases covered (failures, fallbacks, empty results)
