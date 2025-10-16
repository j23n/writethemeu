# Simplify Address Resolution API Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Simplify the address → constituency resolution architecture by consolidating APIs, using single address strings instead of separate street/postal/city params, removing PLZ fallback logic, and fixing the regression where state district constituencies are not returned.

**Architecture:** Replace ConstituencyLocator with enhanced WahlkreisResolver as the single entry point. Change all geocoding to use single address strings. Make WahlkreisLocator.locate() return both federal AND state Wahlkreis data. Remove all PLZ-prefix fallback logic.

**Tech Stack:** Django, Shapely (GeoJSON), OSM Nominatim API

---

## Task 1: Update AddressGeocoder to accept single address string

**Files:**
- Modify: `website/letters/services/geocoding.py:37-101` (geocode method)
- Modify: `website/letters/services/geocoding.py:103-113` (_generate_cache_key method)
- Modify: `website/letters/services/geocoding.py:129-154` (_store_in_cache method)
- Modify: `website/letters/services/geocoding.py:167-222` (_query_nominatim method)

**Step 1: Update geocode() signature to accept address string**

In `website/letters/services/geocoding.py`, replace the `geocode` method:

```python
def geocode(
    self,
    address: str,
    country: str = 'DE'
) -> Tuple[Optional[float], Optional[float], bool, Optional[str]]:
    """
    Geocode a German address to latitude/longitude coordinates.

    Args:
        address: Full address string (e.g., "Unter den Linden 1, 10117 Berlin")
        country: Country code (default: 'DE')

    Returns:
        Tuple of (latitude, longitude, success, error_message)
        - On success: (lat, lon, True, None)
        - On failure: (None, None, False, error_message)
    """
    address = (address or '').strip()
    country = (country or 'DE').upper()

    if not address:
        return None, None, False, 'Address is required'

    address_hash = self._generate_cache_key(address, country)

    cached = self._get_from_cache(address_hash)
    if cached is not None:
        return cached

    try:
        self._apply_rate_limit()
        result = self._query_nominatim(address, country)

        if result:
            lat, lon = result
            self._store_in_cache(
                address_hash, address, country,
                lat, lon, success=True, error_message=None
            )
            return lat, lon, True, None
        else:
            error_msg = 'Address not found'
            self._store_in_cache(
                address_hash, address, country,
                None, None, success=False, error_message=error_msg
            )
            return None, None, False, error_msg

    except Exception as e:
        error_msg = f'Geocoding API error: {str(e)}'
        logger.warning('Geocoding failed for %s: %s', address, error_msg)

        self._store_in_cache(
            address_hash, address, country,
            None, None, success=False, error_message=error_msg
        )
        return None, None, False, error_msg
```

**Step 2: Update _generate_cache_key() to use address string**

```python
def _generate_cache_key(
    self,
    address: str,
    country: str
) -> str:
    """Generate SHA256 hash of normalized address for cache lookup."""
    normalized = f"{address}|{country}"
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()
```

**Step 3: Update _store_in_cache() signature**

```python
def _store_in_cache(
    self,
    address_hash: str,
    address: str,
    country: str,
    latitude: Optional[float],
    longitude: Optional[float],
    success: bool,
    error_message: Optional[str]
) -> None:
    """Store geocoding result in cache."""
    GeocodeCache.objects.update_or_create(
        address_hash=address_hash,
        defaults={
            'street': '',
            'postal_code': '',
            'city': address,
            'country': country,
            'latitude': latitude,
            'longitude': longitude,
            'success': success,
            'error_message': error_message or '',
        }
    )
```

**Step 4: Update _query_nominatim() to use address string**

```python
def _query_nominatim(
    self,
    address: str,
    country: str
) -> Optional[Tuple[float, float]]:
    """
    Query Nominatim API for address coordinates.

    Returns:
        (latitude, longitude) on success, None if not found

    Raises:
        requests.RequestException on API errors
    """
    params = {
        'q': address,
        'format': 'json',
        'addressdetails': 1,
        'limit': 1,
        'countrycodes': country.lower(),
    }

    headers = {
        'User-Agent': self.USER_AGENT
    }

    response = requests.get(
        self.NOMINATIM_ENDPOINT,
        params=params,
        headers=headers,
        timeout=10
    )
    response.raise_for_status()

    results = response.json()

    if results and len(results) > 0:
        result = results[0]
        lat = float(result['lat'])
        lon = float(result['lon'])
        return lat, lon

    return None
```

**Step 5: Commit**

```bash
git add website/letters/services/geocoding.py
git commit -m "refactor: simplify AddressGeocoder to use single address string"
```

---

## Task 2: Fix WahlkreisLocator.locate() to return both federal and state

**Files:**
- Modify: `website/letters/services/geocoding.py:213-230` (locate method)

**Step 1: Replace locate() to return _locate_detailed() result**

In `website/letters/services/geocoding.py`, replace the `locate` method:

```python
def locate(self, latitude, longitude):
    """
    Find federal and state constituencies for given coordinates.

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate

    Returns:
        dict with 'federal' and 'state' keys, each containing:
        {
            'wkr_nr': int,
            'wkr_name': str,
            'land_name': str,
            'land_code': str
        }
        or None if no federal constituency found.
    """
    result = self._locate_detailed(latitude, longitude)

    if result and result['federal']:
        return result

    return None
```

**Step 2: Commit**

```bash
git add website/letters/services/geocoding.py
git commit -m "fix: WahlkreisLocator.locate() now returns both federal and state Wahlkreise"
```

---

## Task 3: Update WahlkreisResolver to use new APIs and query state districts

**Files:**
- Modify: `website/letters/services/wahlkreis.py:45-122` (resolve method)

**Step 1: Update resolve() method signature and implementation**

In `website/letters/services/wahlkreis.py`, replace the `resolve` method:

```python
def resolve(
    self,
    address: str,
    country: str = 'DE'
) -> Dict:
    """
    Resolve address to Wahlkreis identifiers and Constituency objects.

    Args:
        address: Full address string (e.g., "Unter den Linden 1, 10117 Berlin")
        country: Country code (default: 'DE')

    Returns:
        {
            'federal_wahlkreis_number': str or None,
            'state_wahlkreis_number': str or None,
            'eu_wahlkreis': str (always 'DE'),
            'constituencies': List[Constituency]
        }
    """
    result = {
        'federal_wahlkreis_number': None,
        'state_wahlkreis_number': None,
        'eu_wahlkreis': 'DE',
        'constituencies': []
    }

    address = (address or '').strip()
    if not address:
        logger.warning("Empty address provided to WahlkreisResolver")
        return result

    # Step 1: Geocode address
    lat, lon, success, error = self.geocoder.geocode(address, country)

    if not success or lat is None or lon is None:
        logger.warning(f"Geocoding failed: {error}")
        return result

    # Step 2: Look up Wahlkreise (federal and state)
    wahlkreis_result = self.wahlkreis_locator.locate(lat, lon)

    if not wahlkreis_result:
        logger.warning(f"No Wahlkreis found for coordinates {lat}, {lon}")
        return result

    federal_data = wahlkreis_result.get('federal')
    state_data = wahlkreis_result.get('state')

    if not federal_data:
        logger.warning(f"No federal Wahlkreis found for coordinates {lat}, {lon}")
        return result

    # Extract federal Wahlkreis data
    federal_wkr_nr = federal_data['wkr_nr']
    federal_wahlkreis_number = str(federal_wkr_nr).zfill(3)
    land_name = federal_data['land_name']
    normalized_state = normalize_german_state(land_name)

    result['federal_wahlkreis_number'] = federal_wahlkreis_number

    # Extract state Wahlkreis data if available
    if state_data:
        state_wkr_nr = state_data['wkr_nr']
        state_wahlkreis_number = str(state_wkr_nr).zfill(3)
        result['state_wahlkreis_number'] = state_wahlkreis_number

    # Step 3: Find constituencies by wahlkreis_id
    constituencies = []

    # Add federal district constituency
    federal_constituencies = list(
        Constituency.objects.filter(
            wahlkreis_id=federal_wahlkreis_number,
            scope='FEDERAL_DISTRICT'
        )
    )
    constituencies.extend(federal_constituencies)

    # Add state district constituency if we have state Wahlkreis data
    if state_data:
        state_wahlkreis_number = result['state_wahlkreis_number']
        state_district_constituencies = list(
            Constituency.objects.filter(
                wahlkreis_id=state_wahlkreis_number,
                scope='STATE_DISTRICT'
            )
        )
        constituencies.extend(state_district_constituencies)

    # Add state list constituency
    if normalized_state:
        state_list_constituencies = Constituency.objects.filter(
            scope='STATE_LIST',
            metadata__state=normalized_state
        )
        constituencies.extend(state_list_constituencies)

    result['constituencies'] = constituencies

    logger.info(
        f"Resolved {address} to "
        f"Federal WK {federal_wahlkreis_number}, State WK {result['state_wahlkreis_number']}, "
        f"with {len(constituencies)} constituencies"
    )

    return result
```

**Step 2: Commit**

```bash
git add website/letters/services/wahlkreis.py
git commit -m "refactor: WahlkreisResolver uses single address string and returns state districts"
```

---

## Task 4: Remove ConstituencyLocator class

**Files:**
- Modify: `website/letters/services/constituency.py:69-288` (delete ConstituencyLocator class)
- Modify: `website/letters/services/__init__.py:7,23` (remove ConstituencyLocator export)

**Step 1: Delete the ConstituencyLocator class**

In `website/letters/services/constituency.py`, delete lines 69-288 (the entire `ConstituencyLocator` class and `LocatedConstituencies` dataclass).

**Step 2: Remove ConstituencyLocator from exports**

In `website/letters/services/__init__.py`, remove:
- Line 7: `ConstituencyLocator,` from import
- Line 23: `'ConstituencyLocator',` from __all__

**Step 3: Commit**

```bash
git add website/letters/services/constituency.py website/letters/services/__init__.py
git commit -m "refactor: remove ConstituencyLocator class"
```

---

## Task 5: Update ConstituencySuggestionService._resolve_location()

**Files:**
- Modify: `website/letters/services/constituency.py:367-431` (_resolve_location method)

**Step 1: Update _resolve_location to use WahlkreisResolver**

In `website/letters/services/constituency.py`, replace the `_resolve_location` method:

```python
@classmethod
def _resolve_location(cls, user_location: Dict[str, str]) -> LocationContext:
    # Extract address components
    postal_code = (user_location.get('postal_code') or '').strip()
    street = (user_location.get('street') or '').strip()
    city = (user_location.get('city') or '').strip()
    country = (user_location.get('country') or 'DE').upper()

    constituencies: List[Constituency] = []

    # First, check if constituencies are provided directly
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

    # If no constituencies provided, try address-based lookup
    if not constituencies and street and postal_code and city:
        from .wahlkreis import WahlkreisResolver
        resolver = WahlkreisResolver()

        # Build full address string
        address = f"{street}, {postal_code} {city}"
        result = resolver.resolve(address=address, country=country)
        constituencies = result['constituencies']

    # Determine state from various sources
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
        street=street or None,
        city=city or None,
        country=country,
    )
```

**Step 2: Commit**

```bash
git add website/letters/services/constituency.py
git commit -m "refactor: ConstituencySuggestionService uses WahlkreisResolver with address string"
```

---

## Task 6: Update views.py search_wahlkreis endpoint

**Files:**
- Modify: `website/letters/views.py:34` (update import)
- Modify: `website/letters/views.py:586-654` (search_wahlkreis function)

**Step 1: Update import statement**

In `website/letters/views.py`, replace line 34:

```python
from .services.wahlkreis import WahlkreisResolver
```

**Step 2: Update search_wahlkreis function**

Replace the `search_wahlkreis` function (lines 586-654):

```python
@login_required
@require_http_methods(["POST"])
def search_wahlkreis(request):
    """
    HTMX endpoint: Search for Wahlkreis by address.
    Returns HTML fragment with constituency data or error message.
    """
    street_address = request.POST.get('street_address', '').strip()
    postal_code = request.POST.get('postal_code', '').strip()
    city = request.POST.get('city', '').strip()

    # Validate required fields
    if not all([street_address, postal_code, city]):
        return render(request, 'letters/partials/wahlkreis_search_result.html', {
            'success': False,
            'error': 'Please provide street address, postal code, and city.'
        })

    # Build full address string
    address = f"{street_address}, {postal_code} {city}"

    # Find constituencies using WahlkreisResolver
    try:
        resolver = WahlkreisResolver()
        result = resolver.resolve(address=address, country='DE')
        constituencies = result['constituencies']

        if not constituencies:
            logger.warning(
                f'Address search found no constituencies for {address}'
            )
            return render(request, 'letters/partials/wahlkreis_search_result.html', {
                'success': False,
                'error': 'Could not find constituencies for this address. Please select manually.'
            })

        # Find federal and state constituencies
        federal_constituency = None
        state_constituency = None

        for constituency in constituencies:
            if constituency.scope == 'FEDERAL_DISTRICT' and not federal_constituency:
                federal_constituency = constituency
            elif constituency.scope in ['STATE_LIST', 'STATE_DISTRICT'] and not state_constituency:
                state_constituency = constituency

        # Get display name from metadata if available
        wahlkreis_name = 'Unknown'
        land_name = 'Unknown'

        if federal_constituency and federal_constituency.metadata:
            wahlkreis_name = federal_constituency.name
            land_name = federal_constituency.metadata.get('state', 'Unknown')

        return render(request, 'letters/partials/wahlkreis_search_result.html', {
            'success': True,
            'wahlkreis_name': wahlkreis_name,
            'land_name': land_name,
            'federal_constituency_id': federal_constituency.id if federal_constituency else None,
            'state_constituency_id': state_constituency.id if state_constituency else None,
        })

    except Exception as e:
        logger.exception('Unexpected error during wahlkreis search')
        return render(request, 'letters/partials/wahlkreis_search_result.html', {
            'success': False,
            'error': 'Search temporarily unavailable. Please select Wahlkreise manually.'
        })
```

**Step 3: Commit**

```bash
git add website/letters/views.py
git commit -m "refactor: search_wahlkreis uses WahlkreisResolver with address string"
```

---

## Task 7: Update management command query_representatives.py

**Files:**
- Modify: `website/letters/management/commands/query_representatives.py:6-7` (update imports)
- Modify: `website/letters/management/commands/query_representatives.py:45-84` (handle function)

**Step 1: Update imports**

In `website/letters/management/commands/query_representatives.py`, replace lines 6-7:

```python
from letters.services.wahlkreis import WahlkreisResolver
```

**Step 2: Update handle() method**

Replace the address handling section (lines 53-84):

```python
try:
    # Use WahlkreisResolver if address provided
    if postal_code or (street and city):
        # Build address string
        address_parts = []
        if street:
            address_parts.append(street)
        if postal_code:
            address_parts.append(postal_code)
        if city:
            address_parts.append(city)

        address = ', '.join(address_parts)

        resolver = WahlkreisResolver()
        result = resolver.resolve(address=address)

        if result['federal_wahlkreis_number']:
            self.stdout.write(self.style.SUCCESS(
                f"Found Wahlkreise: "
                f"Federal={result['federal_wahlkreis_number']}, "
                f"State={result['state_wahlkreis_number']}, "
                f"EU={result['eu_wahlkreis']}"
            ))

        constituencies = result['constituencies']

        if not constituencies:
            self.stdout.write('No constituencies found for this location')
            return

        # Get representatives from constituencies
        representatives = []
        for constituency in constituencies:
            reps = list(constituency.representatives.filter(is_active=True))
            representatives.extend(reps)

        # Remove duplicates
        seen = set()
        unique_reps = []
        for rep in representatives:
            if rep.id not in seen:
                seen.add(rep.id)
                unique_reps.append(rep)
        representatives = unique_reps

        if not representatives:
            self.stdout.write('No active representatives found for these constituencies')
            return

        # Filter by topics if provided
        if topics_str:
            topic_keywords = [t.strip() for t in topics_str.split(',')]
            filtered_reps = []
            for rep in representatives:
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

            committees = list(rep.committees.all()[:3])
            if committees:
                committee_names = ', '.join([c.name for c in committees])
                self.stdout.write(f'  Committees: {committee_names}')

    # Use topic-based search if only topics provided
    elif topics_str:
        self.stdout.write('Topic-based representative search not yet implemented')
        self.stdout.write('Please provide at least an address for location-based search')

    else:
        self.stderr.write(self.style.ERROR(
            'Error: Please provide an address (street, postal code, and/or city) or --topics'
        ))

except Exception as e:
    self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
    return
```

**Step 3: Commit**

```bash
git add website/letters/management/commands/query_representatives.py
git commit -m "refactor: query_representatives uses WahlkreisResolver with address string"
```

---

## Task 8: Update management command query_wahlkreis.py

**Files:**
- Modify: `website/letters/management/commands/query_wahlkreis.py:5` (update imports)
- Modify: `website/letters/management/commands/query_wahlkreis.py:29-66` (handle function)

**Step 1: Update imports**

In `website/letters/management/commands/query_wahlkreis.py`, replace line 5:

```python
from letters.services import AddressGeocoder, WahlkreisLocator
from letters.services.wahlkreis import WahlkreisResolver
```

**Step 2: Update handle() method to use WahlkreisResolver**

Replace lines 29-66:

```python
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
```

**Step 3: Commit**

```bash
git add website/letters/management/commands/query_wahlkreis.py
git commit -m "refactor: query_wahlkreis uses WahlkreisResolver with address string"
```

---

## Task 9: Update tests for new API

**Files:**
- Modify: `website/letters/tests/test_wahlkreis_resolver.py:53-86`
- Modify: `website/letters/tests/test_address_matching.py` (entire file)

**Step 1: Update test_wahlkreis_resolver.py**

In `website/letters/tests/test_wahlkreis_resolver.py`, replace the test at lines 53-86:

```python
@patch('letters.services.wahlkreis.AddressGeocoder.geocode')
@patch('letters.services.wahlkreis.WahlkreisLocator.locate')
def test_resolve_returns_wahlkreis_identifiers_and_constituencies(
    self, mock_wahlkreis_locate, mock_geocode
):
    """Test that resolve() returns Wahlkreis IDs and matching constituencies"""
    # Mock geocoding
    mock_geocode.return_value = (52.520, 13.405, True, None)

    # Mock Wahlkreis lookup - returns detailed result
    mock_wahlkreis_locate.return_value = {
        'federal': {
            'wkr_nr': 75,
            'wkr_name': 'Berlin-Mitte',
            'land_name': 'Berlin',
            'land_code': 'BE'
        },
        'state': None
    }

    resolver = WahlkreisResolver()
    result = resolver.resolve(
        address='Unter den Linden 1, 10117 Berlin'
    )

    # Check structure
    self.assertIn('federal_wahlkreis_number', result)
    self.assertIn('state_wahlkreis_number', result)
    self.assertIn('eu_wahlkreis', result)
    self.assertIn('constituencies', result)

    # Check values
    self.assertEqual(result['federal_wahlkreis_number'], '075')
    self.assertEqual(result['eu_wahlkreis'], 'DE')

    # Check constituencies returned
    constituency_ids = {c.id for c in result['constituencies']}
    self.assertIn(self.federal_constituency.id, constituency_ids)
    self.assertIn(self.state_constituency.id, constituency_ids)
```

**Step 2: Add test for state district constituencies**

Add new test after the existing one:

```python
@patch('letters.services.wahlkreis.AddressGeocoder.geocode')
@patch('letters.services.wahlkreis.WahlkreisLocator.locate')
def test_resolve_returns_state_district_constituencies(
    self, mock_locate, mock_geocode
):
    """Test that resolve() returns state district constituencies when available"""
    # Create state district constituency
    state_district = Constituency.objects.create(
        parliament_term=self.state_term,
        name='Berlin-Mitte (Landtag)',
        scope='STATE_DISTRICT',
        wahlkreis_id='025',
        metadata={'state': 'Berlin'}
    )

    # Mock geocoding
    mock_geocode.return_value = (52.520, 13.405, True, None)

    # Mock Wahlkreis lookup with both federal and state
    mock_locate.return_value = {
        'federal': {
            'wkr_nr': 75,
            'wkr_name': 'Berlin-Mitte',
            'land_name': 'Berlin',
            'land_code': 'BE'
        },
        'state': {
            'wkr_nr': 25,
            'wkr_name': 'Berlin-Mitte (Landtag)',
            'land_name': 'Berlin',
            'land_code': 'BE'
        }
    }

    resolver = WahlkreisResolver()
    result = resolver.resolve(address='Unter den Linden 1, 10117 Berlin')

    # Check wahlkreis numbers
    self.assertEqual(result['federal_wahlkreis_number'], '075')
    self.assertEqual(result['state_wahlkreis_number'], '025')

    # Check all constituency types returned
    constituency_ids = {c.id for c in result['constituencies']}
    self.assertIn(self.federal_constituency.id, constituency_ids,
                 "Should include federal district")
    self.assertIn(self.state_constituency.id, constituency_ids,
                 "Should include state list")
    self.assertIn(state_district.id, constituency_ids,
                 "Should include state district")
```

**Step 3: Update test_address_matching.py**

In `website/letters/tests/test_address_matching.py`, update the imports and remove ConstituencyLocator tests:

```python
from letters.services import AddressGeocoder, WahlkreisLocator
from letters.services.wahlkreis import WahlkreisResolver
```

Remove the ConstituencyLocator test class entirely (starting around line 318).

**Step 4: Run tests**

```bash
uv run python website/manage.py test website.letters.tests.test_wahlkreis_resolver -v
```

Expected: Both tests PASS

**Step 5: Commit**

```bash
git add website/letters/tests/test_wahlkreis_resolver.py website/letters/tests/test_address_matching.py
git commit -m "test: update tests for simplified address resolution API"
```

---

## Task 10: Run full test suite

**Step 1: Run all tests**

```bash
uv run python website/manage.py test website.letters -v
```

Expected: All tests PASS

**Step 2: Verify geocoding still works**

```bash
uv run python website/manage.py query_wahlkreis --postal-code 10117 --street "Unter den Linden 1" --city "Berlin"
```

Expected: Displays federal and state Wahlkreis numbers and constituencies

**Step 3: Final commit if any fixes were needed**

```bash
git add .
git commit -m "fix: address any remaining test failures"
```

---

## Completion Checklist

- [ ] AddressGeocoder uses single address string
- [ ] WahlkreisLocator.locate() returns both federal and state
- [ ] WahlkreisResolver uses address string and queries state districts
- [ ] ConstituencyLocator class removed
- [ ] ConstituencySuggestionService uses WahlkreisResolver
- [ ] views.py search_wahlkreis uses WahlkreisResolver
- [ ] Management commands updated
- [ ] All tests passing
- [ ] Manual verification successful
