# Accurate Constituency Matching Implementation Plan

> **For Claude:** Use `${CLAUDE_PLUGIN_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Replace PLZ prefix heuristic with accurate address-based constituency matching using OSM Nominatim geocoding and GeoJSON point-in-polygon lookup.

**Architecture:** Two-layer approach: (1) AddressGeocoder service converts full German addresses to lat/lng coordinates via OSM Nominatim API with database caching, (2) WahlkreisLocator service uses shapely to perform point-in-polygon queries against Bundestag GeoJSON boundaries. PLZ prefix fallback remains for partial data.

**Tech Stack:** Django 5.x, shapely 2.x, requests, OSM Nominatim API, GeoJSON

---

## Task 1: Database Model for Geocoding Cache

**Files:**
- Create: `website/letters/models.py` (add new model)
- Create: `website/letters/migrations/0012_geocodecache.py` (auto-generated)
- Test: `website/letters/tests.py`

**Step 1: Write the failing test**

Add to `website/letters/tests.py`:

```python
class GeocodeCache Tests(TestCase):
    """Test geocoding cache model."""

    def test_cache_stores_and_retrieves_coordinates(self):
        from .models import GeocodeCache

        cache_entry = GeocodeCache.objects.create(
            address_hash='test_hash_123',
            street='Unter den Linden 77',
            postal_code='10117',
            city='Berlin',
            latitude=52.5170365,
            longitude=13.3888599,
        )

        retrieved = GeocodeCache.objects.get(address_hash='test_hash_123')
        self.assertEqual(retrieved.latitude, 52.5170365)
        self.assertEqual(retrieved.longitude, 13.3888599)
        self.assertEqual(retrieved.street, 'Unter den Linden 77')
```

**Step 2: Run test to verify it fails**

Run: `uv run python manage.py test letters.tests.GeocodeCacheTests -v`
Expected: FAIL with "No module named 'GeocodeCache'"

**Step 3: Add GeocodeCache model**

Add to `website/letters/models.py` after the existing models:

```python
class GeocodeCache(models.Model):
    """Cache geocoding results to minimize API calls."""

    address_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SHA256 hash of normalized address for fast lookup"
    )
    street = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=10, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, default='DE')

    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    success = models.BooleanField(
        default=True,
        help_text="False if geocoding failed, to avoid repeated failed lookups"
    )
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Geocode Cache Entry"
        verbose_name_plural = "Geocode Cache Entries"
        ordering = ['-created_at']

    def __str__(self):
        if self.latitude and self.longitude:
            return f"{self.city} ({self.latitude}, {self.longitude})"
        return f"{self.city} (failed)"
```

**Step 4: Create migration**

Run: `uv run python manage.py makemigrations letters`
Expected: Migration 0012_geocodecache.py created

**Step 5: Run migration**

Run: `uv run python manage.py migrate`
Expected: "Applying letters.0012_geocodecache... OK"

**Step 6: Run test to verify it passes**

Run: `uv run python manage.py test letters.tests.GeocodeCacheTests -v`
Expected: PASS

**Step 7: Commit**

```bash
git add website/letters/models.py website/letters/migrations/0012_geocodecache.py website/letters/tests.py
git commit -m "feat: add GeocodeCache model for address geocoding results"
```

---

## Task 2: OSM Nominatim API Client

**Files:**
- Modify: `website/letters/services.py` (add AddressGeocoder class)
- Test: `website/letters/tests.py`

**Step 1: Write the failing test**

Add to `website/letters/tests.py`:

```python
from unittest.mock import patch, MagicMock


class AddressGeocoderTests(TestCase):
    """Test OSM Nominatim address geocoding."""

    def test_geocode_returns_coordinates_for_valid_address(self):
        from .services import AddressGeocoder

        # Mock the Nominatim API response
        mock_response = MagicMock()
        mock_response.json.return_value = [{
            'lat': '52.5170365',
            'lon': '13.3888599',
            'display_name': 'Unter den Linden 77, Mitte, Berlin, 10117, Deutschland'
        }]
        mock_response.status_code = 200

        with patch('requests.get', return_value=mock_response):
            result = AddressGeocoder.geocode(
                street='Unter den Linden 77',
                postal_code='10117',
                city='Berlin'
            )

        self.assertIsNotNone(result)
        lat, lng = result
        self.assertAlmostEqual(lat, 52.5170365, places=5)
        self.assertAlmostEqual(lng, 13.3888599, places=5)

    def test_geocode_caches_results(self):
        from .services import AddressGeocoder
        from .models import GeocodeCache

        mock_response = MagicMock()
        mock_response.json.return_value = [{
            'lat': '52.5170365',
            'lon': '13.3888599',
        }]
        mock_response.status_code = 200

        with patch('requests.get', return_value=mock_response) as mock_get:
            # First call should hit API
            result1 = AddressGeocoder.geocode(
                street='Unter den Linden 77',
                postal_code='10117',
                city='Berlin'
            )

            # Second call should use cache
            result2 = AddressGeocoder.geocode(
                street='Unter den Linden 77',
                postal_code='10117',
                city='Berlin'
            )

            # API should only be called once
            self.assertEqual(mock_get.call_count, 1)
            self.assertEqual(result1, result2)

            # Verify cache entry exists
            self.assertTrue(
                GeocodeCache.objects.filter(
                    city='Berlin',
                    postal_code='10117'
                ).exists()
            )
```

**Step 2: Run test to verify it fails**

Run: `uv run python manage.py test letters.tests.AddressGeocoderTests -v`
Expected: FAIL with "No module named 'AddressGeocoder'"

**Step 3: Implement AddressGeocoder service**

Add to `website/letters/services.py` after the existing classes:

```python
import hashlib
import time
from typing import Optional, Tuple


class AddressGeocoder:
    """Geocode German addresses using OSM Nominatim API."""

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    USER_AGENT = "WriteThem.eu/1.0 (https://writethem.eu; contact@writethem.eu)"
    REQUEST_TIMEOUT = 10
    RATE_LIMIT_DELAY = 1.0  # seconds between requests

    _last_request_time = 0

    @classmethod
    def geocode(
        cls,
        street: str,
        postal_code: str,
        city: str,
        country: str = 'DE'
    ) -> Optional[Tuple[float, float]]:
        """
        Geocode a German address to lat/lng coordinates.

        Args:
            street: Street address (e.g., "Unter den Linden 77")
            postal_code: German postal code (e.g., "10117")
            city: City name (e.g., "Berlin")
            country: Country code (default: 'DE')

        Returns:
            Tuple of (latitude, longitude) or None if geocoding fails
        """
        from .models import GeocodeCache

        # Normalize inputs
        street = (street or '').strip()
        postal_code = (postal_code or '').strip()
        city = (city or '').strip()
        country = (country or 'DE').upper()

        if not city:
            logger.warning("City is required for geocoding")
            return None

        # Generate cache key
        address_string = f"{street}|{postal_code}|{city}|{country}".lower()
        address_hash = hashlib.sha256(address_string.encode()).hexdigest()

        # Check cache first
        cached = GeocodeCache.objects.filter(address_hash=address_hash).first()
        if cached:
            if cached.success and cached.latitude and cached.longitude:
                logger.debug(f"Cache hit for {city}: ({cached.latitude}, {cached.longitude})")
                return (cached.latitude, cached.longitude)
            elif not cached.success:
                logger.debug(f"Cache hit for {city}: previous failure")
                return None

        # Rate limiting
        cls._rate_limit()

        # Build query
        query_parts = []
        if street:
            query_parts.append(street)
        if postal_code:
            query_parts.append(postal_code)
        query_parts.append(city)
        query_parts.append(country)

        query = ', '.join(query_parts)

        params = {
            'q': query,
            'format': 'json',
            'limit': 1,
            'addressdetails': 1,
            'countrycodes': country.lower(),
        }

        headers = {
            'User-Agent': cls.USER_AGENT
        }

        try:
            logger.info(f"Geocoding address: {query}")
            response = requests.get(
                cls.NOMINATIM_URL,
                params=params,
                headers=headers,
                timeout=cls.REQUEST_TIMEOUT
            )
            response.raise_for_status()

            results = response.json()

            if not results:
                logger.warning(f"No geocoding results for: {query}")
                cls._cache_failure(address_hash, street, postal_code, city, country, "No results")
                return None

            # Extract coordinates
            result = results[0]
            latitude = float(result['lat'])
            longitude = float(result['lon'])

            # Cache success
            GeocodeCache.objects.update_or_create(
                address_hash=address_hash,
                defaults={
                    'street': street,
                    'postal_code': postal_code,
                    'city': city,
                    'country': country,
                    'latitude': latitude,
                    'longitude': longitude,
                    'success': True,
                    'error_message': '',
                }
            )

            logger.info(f"Geocoded {city} to ({latitude}, {longitude})")
            return (latitude, longitude)

        except requests.RequestException as e:
            error_msg = f"Nominatim API error: {e}"
            logger.error(error_msg)
            cls._cache_failure(address_hash, street, postal_code, city, country, error_msg)
            return None
        except (KeyError, ValueError, TypeError) as e:
            error_msg = f"Invalid geocoding response: {e}"
            logger.error(error_msg)
            cls._cache_failure(address_hash, street, postal_code, city, country, error_msg)
            return None

    @classmethod
    def _rate_limit(cls):
        """Ensure we don't exceed Nominatim rate limits (1 req/sec)."""
        import time
        current_time = time.time()
        elapsed = current_time - cls._last_request_time

        if elapsed < cls.RATE_LIMIT_DELAY:
            time.sleep(cls.RATE_LIMIT_DELAY - elapsed)

        cls._last_request_time = time.time()

    @classmethod
    def _cache_failure(
        cls,
        address_hash: str,
        street: str,
        postal_code: str,
        city: str,
        country: str,
        error_message: str
    ):
        """Cache a failed geocoding attempt to avoid repeated failures."""
        from .models import GeocodeCache

        GeocodeCache.objects.update_or_create(
            address_hash=address_hash,
            defaults={
                'street': street,
                'postal_code': postal_code,
                'city': city,
                'country': country,
                'latitude': None,
                'longitude': None,
                'success': False,
                'error_message': error_message,
            }
        )
```

**Step 4: Run test to verify it passes**

Run: `uv run python manage.py test letters.tests.AddressGeocoderTests -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add website/letters/services.py website/letters/tests.py
git commit -m "feat: add OSM Nominatim address geocoding service with caching"
```

---

## Task 3: Download and Prepare GeoJSON Data

**Files:**
- Modify: `website/letters/management/commands/fetch_wahlkreis_data.py` (already exists)
- Create: `website/letters/data/wahlkreise.geojson` (downloaded data)

**Step 1: Test existing download command**

Run: `uv run python manage.py fetch_wahlkreis_data --help`
Expected: Shows command help text

**Step 2: Download full Bundestag GeoJSON**

Run: `uv run python manage.py fetch_wahlkreis_data --output=website/letters/data/wahlkreise.geojson --force`
Expected: "Saved Wahlkreis data to website/letters/data/wahlkreise.geojson"

**Step 3: Verify GeoJSON structure**

Run: `uv run python -c "import json; data = json.load(open('website/letters/data/wahlkreise.geojson')); print(f'Loaded {len(data[\"features\"])} constituencies')"`
Expected: "Loaded 299 constituencies" (or similar)

**Step 4: Add GeoJSON to gitignore**

Add to `.gitignore`:
```
# Large GeoJSON data files
website/letters/data/*.geojson
!website/letters/data/wahlkreise_sample.geojson
```

**Step 5: Commit gitignore update**

```bash
git add .gitignore
git commit -m "chore: add GeoJSON files to gitignore"
```

**Step 6: Document download in README**

Add to README.md setup instructions:
```markdown
### Download Constituency Boundaries

Download the Bundestag constituency boundaries:

\`\`\`bash
uv run python manage.py fetch_wahlkreis_data
\`\`\`

This downloads ~2MB of GeoJSON data for accurate constituency matching.
```

**Step 7: Commit documentation**

```bash
git add README.md
git commit -m "docs: add constituency data download instructions"
```

---

## Task 4: WahlkreisLocator Service with Shapely

**Files:**
- Modify: `website/letters/services.py` (add WahlkreisLocator class)
- Test: `website/letters/tests.py`

**Step 1: Write the failing test**

Add to `website/letters/tests.py`:

```python
class WahlkreisLocatorTests(TestCase):
    """Test GeoJSON point-in-polygon constituency lookup."""

    def setUp(self):
        super().setUp()
        # Create test parliament and constituencies
        self.parliament = Parliament.objects.create(
            name='Deutscher Bundestag',
            level='FEDERAL',
            legislative_body='Bundestag',
            region='DE',
        )
        self.term = ParliamentTerm.objects.create(
            parliament=self.parliament,
            name='20. Wahlperiode',
            start_date=date(2021, 10, 26),
        )
        # Berlin-Mitte constituency
        self.constituency_mitte = Constituency.objects.create(
            parliament_term=self.term,
            name='Berlin-Mitte',
            scope='FEDERAL_DISTRICT',
            external_id='75',  # Real Wahlkreis ID
            metadata={'state': 'Berlin'},
        )

    def test_find_constituency_for_berlin_coordinates(self):
        from .services import WahlkreisLocator

        # Coordinates for Unter den Linden, Berlin-Mitte
        latitude = 52.5170365
        longitude = 13.3888599

        result = WahlkreisLocator.find_constituency(latitude, longitude)

        self.assertIsNotNone(result)
        self.assertEqual(result.external_id, '75')  # Berlin-Mitte
        self.assertEqual(result.scope, 'FEDERAL_DISTRICT')

    def test_returns_none_for_coordinates_outside_germany(self):
        from .services import WahlkreisLocator

        # Coordinates in Paris
        latitude = 48.8566
        longitude = 2.3522

        result = WahlkreisLocator.find_constituency(latitude, longitude)

        self.assertIsNone(result)
```

**Step 2: Run test to verify it fails**

Run: `uv run python manage.py test letters.tests.WahlkreisLocatorTests -v`
Expected: FAIL with "No module named 'WahlkreisLocator'"

**Step 3: Implement WahlkreisLocator service**

Add to `website/letters/services.py`:

```python
from pathlib import Path
from shapely.geometry import Point, shape
from typing import Optional, List, Dict, Any


class WahlkreisLocator:
    """Locate Bundestag constituency from lat/lng using GeoJSON boundaries."""

    _geojson_data: Optional[Dict[str, Any]] = None
    _geometries: Optional[List[tuple]] = None

    GEOJSON_PATH = Path(__file__).parent / 'data' / 'wahlkreise.geojson'

    @classmethod
    def _load_geojson(cls):
        """Load GeoJSON data into memory (called once at startup)."""
        if cls._geometries is not None:
            return

        if not cls.GEOJSON_PATH.exists():
            logger.warning(f"GeoJSON file not found: {cls.GEOJSON_PATH}")
            logger.warning("Run: python manage.py fetch_wahlkreis_data")
            cls._geometries = []
            return

        try:
            with open(cls.GEOJSON_PATH, 'r', encoding='utf-8') as f:
                cls._geojson_data = json.load(f)

            # Pre-process geometries for faster lookup
            cls._geometries = []
            for feature in cls._geojson_data.get('features', []):
                geometry = shape(feature['geometry'])
                properties = feature.get('properties', {})

                # Extract Wahlkreis ID from properties
                wahlkreis_id = properties.get('WKR_NR') or properties.get('id')
                wahlkreis_name = properties.get('WKR_NAME') or properties.get('name')

                if wahlkreis_id:
                    cls._geometries.append((
                        str(wahlkreis_id),
                        wahlkreis_name,
                        geometry
                    ))

            logger.info(f"Loaded {len(cls._geometries)} constituencies from GeoJSON")

        except Exception as e:
            logger.error(f"Failed to load GeoJSON: {e}")
            cls._geometries = []

    @classmethod
    def find_constituency(
        cls,
        latitude: float,
        longitude: float
    ) -> Optional[Constituency]:
        """
        Find the Bundestag constituency containing the given coordinates.

        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees

        Returns:
            Constituency object or None if not found
        """
        cls._load_geojson()

        if not cls._geometries:
            logger.warning("No GeoJSON data loaded")
            return None

        point = Point(longitude, latitude)  # Note: shapely uses (x, y) = (lon, lat)

        # Find which polygon contains this point
        for wahlkreis_id, wahlkreis_name, geometry in cls._geometries:
            if geometry.contains(point):
                logger.debug(f"Found constituency: {wahlkreis_name} (ID: {wahlkreis_id})")

                # Look up in database
                constituency = Constituency.objects.filter(
                    external_id=wahlkreis_id,
                    scope='FEDERAL_DISTRICT'
                ).first()

                if constituency:
                    return constituency
                else:
                    logger.warning(
                        f"Constituency {wahlkreis_id} found in GeoJSON but not in database"
                    )
                    return None

        logger.debug(f"No constituency found for coordinates ({latitude}, {longitude})")
        return None

    @classmethod
    def clear_cache(cls):
        """Clear cached GeoJSON data (useful for testing)."""
        cls._geojson_data = None
        cls._geometries = None
```

**Step 4: Add shapely to requirements**

Check if shapely is in requirements:
Run: `grep shapely pyproject.toml || grep shapely requirements.txt`

If not found, add to pyproject.toml dependencies:
```toml
dependencies = [
    "django>=5.0",
    "shapely>=2.0",
    # ... other deps
]
```

**Step 5: Install shapely**

Run: `uv sync`
Expected: "Resolved X packages in Yms"

**Step 6: Run test to verify it passes**

Run: `uv run python manage.py test letters.tests.WahlkreisLocatorTests -v`
Expected: PASS (2 tests)

**Step 7: Commit**

```bash
git add website/letters/services.py website/letters/tests.py pyproject.toml
git commit -m "feat: add GeoJSON point-in-polygon constituency lookup"
```

---

## Task 5: Integration - Update ConstituencyLocator

**Files:**
- Modify: `website/letters/services.py` (update ConstituencyLocator class)
- Test: `website/letters/tests.py`

**Step 1: Write integration test**

Add to `website/letters/tests.py`:

```python
class ConstituencyLocatorIntegrationTests(TestCase):
    """Test integrated address → constituency lookup."""

    def setUp(self):
        super().setUp()
        self.parliament = Parliament.objects.create(
            name='Deutscher Bundestag',
            level='FEDERAL',
            legislative_body='Bundestag',
            region='DE',
        )
        self.term = ParliamentTerm.objects.create(
            parliament=self.parliament,
            name='20. Wahlperiode',
            start_date=date(2021, 10, 26),
        )
        self.constituency_mitte = Constituency.objects.create(
            parliament_term=self.term,
            name='Berlin-Mitte',
            scope='FEDERAL_DISTRICT',
            external_id='75',
            metadata={'state': 'Berlin'},
        )

    @patch('letters.services.AddressGeocoder.geocode')
    def test_locate_uses_address_geocoding(self, mock_geocode):
        from .services import ConstituencyLocator

        # Mock geocoding to return Berlin-Mitte coordinates
        mock_geocode.return_value = (52.5170365, 13.3888599)

        result = ConstituencyLocator.locate_from_address(
            street='Unter den Linden 77',
            postal_code='10117',
            city='Berlin'
        )

        self.assertIsNotNone(result.federal)
        self.assertEqual(result.federal.external_id, '75')

        # Verify geocoder was called
        mock_geocode.assert_called_once_with(
            street='Unter den Linden 77',
            postal_code='10117',
            city='Berlin',
            country='DE'
        )

    def test_locate_falls_back_to_plz_prefix(self):
        from .services import ConstituencyLocator

        # Test with just PLZ (no full address)
        result = ConstituencyLocator.locate('10117')

        # Should return Berlin-based constituency using old heuristic
        self.assertIsNotNone(result.federal)
```

**Step 2: Run test to verify it fails**

Run: `uv run python manage.py test letters.tests.ConstituencyLocatorIntegrationTests -v`
Expected: FAIL with "No method named 'locate_from_address'"

**Step 3: Add locate_from_address method**

Modify `ConstituencyLocator` class in `website/letters/services.py`:

```python
class ConstituencyLocator:
    """Enhanced mapping from addresses/postal codes to constituencies."""

    # ... existing STATE_BY_PLZ_PREFIX dict ...

    @classmethod
    def locate_from_address(
        cls,
        street: str,
        postal_code: str,
        city: str,
        country: str = 'DE'
    ) -> LocatedConstituencies:
        """
        Locate constituency from full address using geocoding.

        This is the preferred method for accurate constituency matching.
        Falls back to PLZ prefix if geocoding fails.
        """
        # Try accurate geocoding first
        coordinates = AddressGeocoder.geocode(street, postal_code, city, country)

        if coordinates:
            latitude, longitude = coordinates

            # Use GeoJSON lookup for federal constituency
            federal_constituency = WahlkreisLocator.find_constituency(latitude, longitude)

            if federal_constituency:
                # Also try to determine state from the federal constituency
                state_name = (federal_constituency.metadata or {}).get('state')
                state_constituency = None

                if state_name:
                    normalized_state = normalize_german_state(state_name)
                    state_constituency = cls._match_state(normalized_state)

                return LocatedConstituencies(
                    federal=federal_constituency,
                    state=state_constituency,
                    local=None
                )

        # Fallback to PLZ prefix heuristic
        logger.info(f"Falling back to PLZ prefix lookup for {postal_code}")
        return cls.locate(postal_code)

    @classmethod
    def locate(cls, postal_code: str) -> LocatedConstituencies:
        """
        Legacy PLZ prefix-based lookup.

        Use locate_from_address() for accurate results.
        This method kept for backwards compatibility and fallback.
        """
        # ... existing implementation unchanged ...
```

**Step 4: Run test to verify it passes**

Run: `uv run python manage.py test letters.tests.ConstituencyLocatorIntegrationTests -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add website/letters/services.py website/letters/tests.py
git commit -m "feat: integrate address geocoding into ConstituencyLocator"
```

---

## Task 6: Update ConstituencySuggestionService to Use Address

**Files:**
- Modify: `website/letters/services.py` (update _resolve_location method)
- Test: `website/letters/tests.py`

**Step 1: Write test for address-based suggestion**

Add to `website/letters/tests.py`:

```python
class SuggestionServiceAddressTests(ParliamentFixtureMixin, TestCase):
    """Test suggestions with full address input."""

    @patch('letters.services.AddressGeocoder.geocode')
    def test_suggestions_with_full_address(self, mock_geocode):
        from .services import ConstituencySuggestionService

        # Mock geocoding
        mock_geocode.return_value = (52.5170365, 13.3888599)

        result = ConstituencySuggestionService.suggest_from_concern(
            'Mehr Investitionen in den ÖPNV',
            user_location={
                'street': 'Unter den Linden 77',
                'postal_code': '10117',
                'city': 'Berlin',
            }
        )

        self.assertIsNotNone(result['constituencies'])
        self.assertTrue(len(result['representatives']) > 0)
```

**Step 2: Run test to verify it fails**

Run: `uv run python manage.py test letters.tests.SuggestionServiceAddressTests -v`
Expected: FAIL (address not being used)

**Step 3: Update _resolve_location to handle addresses**

Modify `ConstituencySuggestionService._resolve_location` in `website/letters/services.py`:

```python
@classmethod
def _resolve_location(cls, user_location: Dict[str, str]) -> LocationContext:
    """Resolve user location from various input formats."""

    # Check if full address is provided
    street = (user_location.get('street') or '').strip()
    postal_code = (user_location.get('postal_code') or '').strip()
    city = (user_location.get('city') or '').strip()

    constituencies: List[Constituency] = []

    # Priority 1: Explicitly provided constituency IDs
    provided_constituencies = user_location.get('constituencies')
    if provided_constituencies:
        iterable = provided_constituencies if isinstance(provided_constituencies, (list, tuple, set)) else [provided_constituencies]
        for item in iterable:
            constituency = None
            if isinstance(item, Constituency):
                constituency = item
            else:
                try:
                    constituency_id = int(item)
                except (TypeError, ValueError):
                    constituency_id = None
                if constituency_id:
                    constituency = Constituency.objects.filter(id=constituency_id).first()
            if constituency and all(c.id != constituency.id for c in constituencies):
                constituencies.append(constituency)

    # Priority 2: Full address geocoding
    if not constituencies and city:
        logger.info(f"Using address geocoding for: {city}")
        located = ConstituencyLocator.locate_from_address(street, postal_code, city)
        constituencies.extend(
            constituency
            for constituency in (located.local, located.state, located.federal)
            if constituency
        )

    # Priority 3: PLZ-only fallback
    elif not constituencies and postal_code:
        logger.info(f"Using PLZ fallback for: {postal_code}")
        located = ConstituencyLocator.locate(postal_code)
        constituencies.extend(
            constituency
            for constituency in (located.local, located.state, located.federal)
            if constituency
        )
    else:
        located = LocatedConstituencies(None, None, None)

    # Determine state
    explicit_state = normalize_german_state(user_location.get('state')) if user_location.get('state') else None
    inferred_state = None
    for constituency in constituencies:
        metadata_state = (constituency.metadata or {}).get('state') if constituency.metadata else None
        if metadata_state:
            inferred_state = normalize_german_state(metadata_state)
            if inferred_state:
                break

    state = explicit_state or inferred_state

    return LocationContext(
        postal_code=postal_code or None,
        state=state,
        constituencies=constituencies,
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run python manage.py test letters.tests.SuggestionServiceAddressTests -v`
Expected: PASS

**Step 5: Commit**

```bash
git add website/letters/services.py website/letters/tests.py
git commit -m "feat: support full address in suggestion service"
```

---

## Task 7: Update Profile View to Collect Full Address

**Files:**
- Modify: `website/letters/forms.py` (update verification form)
- Modify: `website/letters/templates/letters/profile.html`
- Test: `website/letters/tests.py`

**Step 1: Write test for address collection**

Add to `website/letters/tests.py`:

```python
class ProfileAddressCollectionTests(TestCase):
    """Test profile form collects full address."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='password123',
            email='test@example.com'
        )

    def test_profile_form_has_address_fields(self):
        from .forms import SelfDeclaredVerificationForm

        form = SelfDeclaredVerificationForm()

        self.assertIn('street', form.fields)
        self.assertIn('postal_code', form.fields)
        self.assertIn('city', form.fields)
```

**Step 2: Run test to verify it fails**

Run: `uv run python manage.py test letters.tests.ProfileAddressCollectionTests -v`
Expected: FAIL (fields don't exist)

**Step 3: Add address fields to form**

Modify `website/letters/forms.py` to add address fields to the verification form:

```python
class SelfDeclaredVerificationForm(forms.Form):
    """Form for self-declared constituency verification."""

    street = forms.CharField(
        max_length=255,
        required=False,
        label=_("Street and Number"),
        help_text=_("Optional: Improves constituency matching accuracy"),
        widget=forms.TextInput(attrs={
            'placeholder': _('Unter den Linden 77'),
            'class': 'form-control'
        })
    )

    postal_code = forms.CharField(
        max_length=10,
        required=True,
        label=_("Postal Code"),
        widget=forms.TextInput(attrs={
            'placeholder': '10117',
            'class': 'form-control'
        })
    )

    city = forms.CharField(
        max_length=100,
        required=True,
        label=_("City"),
        widget=forms.TextInput(attrs={
            'placeholder': 'Berlin',
            'class': 'form-control'
        })
    )

    federal_constituency = forms.ModelChoiceField(
        queryset=Constituency.objects.filter(scope='FEDERAL_DISTRICT'),
        required=False,
        label=_("Federal Constituency (optional)"),
        help_text=_("Leave blank for automatic detection"),
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    state_constituency = forms.ModelChoiceField(
        queryset=Constituency.objects.filter(scope__in=['STATE_DISTRICT', 'STATE_LIST']),
        required=False,
        label=_("State Constituency (optional)"),
        help_text=_("Leave blank for automatic detection"),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
```

**Step 4: Update template to show address fields**

Modify `website/letters/templates/letters/profile.html` to show the new fields in the verification form section.

**Step 5: Update view to use address for verification**

Modify the `complete_verification` or equivalent view in `website/letters/views.py` to use the address fields:

```python
def complete_verification(request):
    if request.method == 'POST':
        form = SelfDeclaredVerificationForm(request.POST)
        if form.is_valid():
            street = form.cleaned_data.get('street', '')
            postal_code = form.cleaned_data['postal_code']
            city = form.cleaned_data['city']

            # Use address-based lookup if full address provided
            if city:
                located = ConstituencyLocator.locate_from_address(
                    street, postal_code, city
                )
            else:
                located = ConstituencyLocator.locate(postal_code)

            federal = form.cleaned_data.get('federal_constituency') or located.federal
            state = form.cleaned_data.get('state_constituency') or located.state

            IdentityVerificationService.self_declare(
                request.user,
                federal_constituency=federal,
                state_constituency=state,
            )

            messages.success(request, _('Your constituency has been saved.'))
            return redirect('profile')
    else:
        form = SelfDeclaredVerificationForm()

    return render(request, 'letters/complete_verification.html', {'form': form})
```

**Step 6: Run test to verify it passes**

Run: `uv run python manage.py test letters.tests.ProfileAddressCollectionTests -v`
Expected: PASS

**Step 7: Test manually in browser**

1. Run dev server: `uv run python manage.py runserver`
2. Navigate to /profile/verify/
3. Verify address fields are visible
4. Submit form with full address
5. Check that constituency is correctly detected

**Step 8: Commit**

```bash
git add website/letters/forms.py website/letters/templates/letters/profile.html website/letters/views.py website/letters/tests.py
git commit -m "feat: collect full address for accurate constituency matching"
```

---

## Task 8: Add Management Command to Test Matching

**Files:**
- Create: `website/letters/management/commands/test_address_matching.py`

**Step 1: Create test command**

Create `website/letters/management/commands/test_address_matching.py`:

```python
from django.core.management.base import BaseCommand
from letters.services import AddressGeocoder, WahlkreisLocator, ConstituencyLocator


class Command(BaseCommand):
    help = "Test address matching with sample German addresses"

    TEST_ADDRESSES = [
        # Berlin
        ("Unter den Linden 77", "10117", "Berlin"),
        ("Pariser Platz 1", "10117", "Berlin"),

        # Munich
        ("Marienplatz 8", "80331", "München"),
        ("Leopoldstraße 1", "80802", "München"),

        # Hamburg
        ("Rathausmarkt 1", "20095", "Hamburg"),
        ("Jungfernstieg 1", "20095", "Hamburg"),

        # Cologne
        ("Rathausplatz 2", "50667", "Köln"),

        # Frankfurt
        ("Römerberg 27", "60311", "Frankfurt am Main"),
    ]

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Testing Address Matching\n"))

        for street, plz, city in self.TEST_ADDRESSES:
            self.stdout.write(f"\n{street}, {plz} {city}")
            self.stdout.write("-" * 60)

            # Test geocoding
            coords = AddressGeocoder.geocode(street, plz, city)
            if coords:
                lat, lng = coords
                self.stdout.write(f"  Coordinates: {lat:.6f}, {lng:.6f}")

                # Test constituency lookup
                constituency = WahlkreisLocator.find_constituency(lat, lng)
                if constituency:
                    self.stdout.write(self.style.SUCCESS(
                        f"  ✓ Constituency: {constituency.name} (ID: {constituency.external_id})"
                    ))
                else:
                    self.stdout.write(self.style.WARNING("  ⚠ No constituency found"))
            else:
                self.stdout.write(self.style.ERROR("  ✗ Geocoding failed"))

            # Small delay to respect rate limits
            import time
            time.sleep(1.1)

        self.stdout.write("\n" + self.style.SUCCESS("Testing complete!"))
```

**Step 2: Run test command**

Run: `uv run python manage.py test_address_matching`
Expected: Shows results for 8 test addresses

**Step 3: Review results and fix any issues**

Check that:
- All addresses geocode successfully
- Constituencies are found for each address
- Results match expected Wahlkreise

**Step 4: Commit**

```bash
git add website/letters/management/commands/test_address_matching.py
git commit -m "feat: add management command to test address matching"
```

---

## Task 9: Performance Optimization and Monitoring

**Files:**
- Modify: `website/letters/services.py` (add metrics/monitoring)
- Create: `website/letters/middleware.py` (optional)

**Step 1: Add logging for matching performance**

Add to `WahlkreisLocator.find_constituency`:

```python
import time

@classmethod
def find_constituency(cls, latitude: float, longitude: float) -> Optional[Constituency]:
    start_time = time.time()

    cls._load_geojson()

    # ... existing implementation ...

    elapsed = time.time() - start_time
    logger.info(f"Constituency lookup took {elapsed*1000:.1f}ms")

    return result
```

**Step 2: Add cache warming on startup**

Add Django app ready hook to pre-load GeoJSON:

Modify `website/letters/apps.py`:

```python
from django.apps import AppConfig


class LettersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'letters'

    def ready(self):
        """Pre-load GeoJSON data on startup."""
        from .services import WahlkreisLocator
        WahlkreisLocator._load_geojson()
```

**Step 3: Test performance**

Run: `uv run python -m django shell`

```python
from letters.services import WahlkreisLocator
import time

# Test lookup performance
start = time.time()
result = WahlkreisLocator.find_constituency(52.5170365, 13.3888599)
elapsed = time.time() - start

print(f"Lookup took {elapsed*1000:.1f}ms")
print(f"Found: {result.name if result else 'None'}")
```

Expected: < 50ms per lookup

**Step 4: Commit**

```bash
git add website/letters/services.py website/letters/apps.py
git commit -m "perf: optimize constituency lookup with startup cache warming"
```

---

## Task 10: Documentation and README

**Files:**
- Modify: `README.md`
- Create: `docs/matching-algorithm.md`

**Step 1: Document matching algorithm**

Create `docs/matching-algorithm.md`:

```markdown
# Constituency Matching Algorithm

## Overview

WriteThem.eu uses a two-stage process to match users to their correct Bundestag constituency:

1. **Address Geocoding**: Convert user's address to latitude/longitude coordinates
2. **Point-in-Polygon Lookup**: Find which constituency polygon contains those coordinates

## Stage 1: Address Geocoding

We use OpenStreetMap's Nominatim API to convert addresses to coordinates.

### Process:
1. User provides: Street, Postal Code, City
2. System checks cache (GeocodeCache table) for previous results
3. If not cached, query Nominatim API with rate limiting (1 req/sec)
4. Cache result (success or failure) to minimize API calls
5. Return (latitude, longitude) or None

### Fallback:
If geocoding fails or user only provides postal code, fall back to PLZ prefix heuristic (maps first 2 digits to state).

## Stage 2: Point-in-Polygon Lookup

We use official Bundestag constituency boundaries (GeoJSON format) with shapely for geometric queries.

### Process:
1. Load GeoJSON with 299 Bundestag constituencies on startup
2. Create shapely Point from coordinates
3. Check which constituency Polygon contains the point
4. Look up Constituency object in database by external_id
5. Return Constituency or None

### Performance:
- GeoJSON loaded once at startup (~2MB in memory)
- Lookup typically takes 10-50ms
- No external API calls required

## Data Sources

- **Constituency Boundaries**: [dknx01/wahlkreissuche](https://github.com/dknx01/wahlkreissuche) (Open Data)
- **Geocoding**: [OpenStreetMap Nominatim](https://nominatim.openstreetmap.org/) (Open Data)
- **Representative Data**: [Abgeordnetenwatch API](https://www.abgeordnetenwatch.de/api)

## Accuracy

This approach provides constituency-accurate matching (exact Wahlkreis), significantly more precise than PLZ-based heuristics which only provide state-level accuracy.

### Known Limitations:
- Requires valid German address
- Dependent on OSM geocoding quality
- Rate limited to 1 request/second (public API)
```

**Step 2: Update README with setup instructions**

Add to `README.md`:

```markdown
## Setup: Constituency Matching

WriteThem.eu uses accurate address-based constituency matching. Setup requires two steps:

### 1. Download Constituency Boundaries

```bash
uv run python manage.py fetch_wahlkreis_data
```

This downloads ~2MB of GeoJSON data containing official Bundestag constituency boundaries.

### 2. Test Matching

Test the matching system with sample addresses:

```bash
uv run python manage.py test_address_matching
```

You should see successful geocoding and constituency detection for major German cities.

### Configuration

Set in your environment or settings:

```python
# Optional: Use self-hosted Nominatim (recommended for production)
NOMINATIM_URL = 'https://your-nominatim-server.com/search'

# Optional: Custom GeoJSON path
CONSTITUENCY_BOUNDARIES_PATH = '/path/to/wahlkreise.geojson'
```

See `docs/matching-algorithm.md` for technical details.
```

**Step 3: Commit**

```bash
git add README.md docs/matching-algorithm.md
git commit -m "docs: document constituency matching algorithm"
```

---

## Plan Complete

**Total Implementation Time: ~5-8 hours** (experienced developer, TDD approach)

**Testing Checklist:**
- [ ] All unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing with 10+ real addresses
- [ ] Performance < 100ms end-to-end
- [ ] Geocoding cache reducing API calls

**Next Steps:**
Run full test suite:
```bash
uv run python manage.py test letters
```

Expected: All tests pass (20+ existing tests + ~15 new tests = 35+ total)

**Deployment Notes:**
- Download GeoJSON as part of deployment process
- Consider self-hosted Nominatim for production (no rate limits)
- Monitor geocoding cache hit rate
- Set up alerts for geocoding failures

---

This plan implements **Week 1-2, Track 1 (Days 1-5)** from the MVP roadmap. After completing this, proceed to Track 2 (UX Polish) tasks.
