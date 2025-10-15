# Wahlkreis-Constituency Separation Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Separate geographic Wahlkreise (electoral districts) from parliamentary Constituencies to support multiple parliament levels per address.

**Architecture:** An address maps to 3 Wahlkreise (EU/Federal/State), stored as identifiers on IdentityVerification. Each Wahlkreis then maps to one or more Constituencies (including state-level list constituencies). Constituency model gains `wahlkreis_id` field; IdentityVerification switches from 3 ForeignKeys to 1 ManyToMany + 3 Wahlkreis identifier fields.

**Tech Stack:** Django ORM, GeoPy/Shapely for geocoding, GeoJSON for Wahlkreis boundaries

---

## Task 1: Add wahlkreis_id field to Constituency model

**Files:**
- Modify: `website/letters/models.py:80-113`

**Step 1: Add wahlkreis_id field to Constituency model**

In the Constituency model (line ~80), add the new field after the `scope` field:

```python
wahlkreis_id = models.CharField(
    max_length=20,
    null=True,
    blank=True,
    help_text=_('Geographic Wahlkreis identifier (e.g., WKR_NR from GeoJSON)')
)
```

**Step 2: Verify model syntax**

Run: `uv run python manage.py check`
Expected: No errors

**Step 3: Commit the model change**

```bash
git add website/letters/models.py
git commit -m "feat: add wahlkreis_id field to Constituency model"
```

---

## Task 2: Add Wahlkreis fields to IdentityVerification model

**Files:**
- Modify: `website/letters/models.py:488-634`

**Step 1: Add Wahlkreis identifier fields**

In the IdentityVerification model (after line ~520, before `verification_data`), add:

```python
# Wahlkreis identifiers (geographic electoral districts)
federal_wahlkreis_number = models.CharField(
    max_length=10,
    null=True,
    blank=True,
    help_text=_('Federal Wahlkreis number (1-299)')
)
state_wahlkreis_number = models.CharField(
    max_length=10,
    null=True,
    blank=True,
    help_text=_('State-specific Wahlkreis identifier')
)
eu_wahlkreis = models.CharField(
    max_length=10,
    default='DE',
    help_text=_('EU Wahlkreis (always DE for Germany)')
)
```

**Step 2: Add constituencies ManyToMany field**

After the Wahlkreis fields, add:

```python
# All applicable constituencies for this verification
constituencies = models.ManyToManyField(
    Constituency,
    blank=True,
    related_name='verified_residents_all'
)
```

**Step 3: Verify model syntax**

Run: `uv run python manage.py check`
Expected: No errors

**Step 4: Commit the changes**

```bash
git add website/letters/models.py
git commit -m "feat: add Wahlkreis fields and constituencies M2M to IdentityVerification"
```

---

## Task 3: Create migration for model changes

**Files:**
- Create: `website/letters/migrations/NNNN_add_wahlkreis_fields.py` (Django will generate number)

**Step 1: Generate migration**

Run: `uv run python manage.py makemigrations letters -n add_wahlkreis_fields`
Expected: Creates new migration file

**Step 2: Review the migration**

Read the generated migration file to ensure it:
- Adds `wahlkreis_id` to Constituency
- Adds `federal_wahlkreis_number`, `state_wahlkreis_number`, `eu_wahlkreis` to IdentityVerification
- Adds `constituencies` M2M to IdentityVerification

**Step 3: Run the migration**

Run: `uv run python manage.py migrate`
Expected: Migration applies successfully

**Step 4: Commit the migration**

```bash
git add website/letters/migrations/
git commit -m "feat: migrate Wahlkreis and Constituency model changes"
```

---

## Task 4: Update IdentityVerification.get_constituencies() method

**Files:**
- Modify: `website/letters/models.py:612-621`

**Step 1: Update get_constituencies() to use M2M**

Replace the existing `get_constituencies()` method (lines ~612-621) with:

```python
def get_constituencies(self) -> List[Constituency]:
    """Return all constituencies linked via the M2M relationship."""
    return list(self.constituencies.all())
```

**Step 2: Update link_constituency() method**

Replace the existing `link_constituency()` method (lines ~581-598) with:

```python
def link_constituency(self, constituency: Constituency) -> None:
    """Add a constituency to this verification's M2M relationship."""
    if not constituency:
        return
    self.constituencies.add(constituency)
    self._update_parliament_links()
```

**Step 3: Update _update_parliament_links() to work with M2M**

The method at lines ~600-606 should work as-is since it calls `get_constituencies()`.

**Step 4: Verify syntax**

Run: `uv run python manage.py check`
Expected: No errors

**Step 5: Commit the changes**

```bash
git add website/letters/models.py
git commit -m "refactor: update IdentityVerification to use constituencies M2M"
```

---

## Task 5: Create WahlkreisResolver service

**Files:**
- Create: `website/letters/services/wahlkreis.py`

**Step 1: Write test for WahlkreisResolver.resolve()**

Create: `website/letters/tests/test_wahlkreis_resolver.py`

```python
# ABOUTME: Tests for WahlkreisResolver service that maps addresses to Wahlkreis identifiers
# ABOUTME: and then resolves those identifiers to Constituency objects.
from unittest.mock import patch, MagicMock
from django.test import TestCase

from letters.services.wahlkreis import WahlkreisResolver
from letters.models import Parliament, ParliamentTerm, Constituency


class WahlkreisResolverTests(TestCase):
    def setUp(self):
        # Create test parliament infrastructure
        self.federal_parliament = Parliament.objects.create(
            name='Bundestag',
            level='FEDERAL',
            legislative_body='Bundestag',
            region='DE'
        )
        self.federal_term = ParliamentTerm.objects.create(
            parliament=self.federal_parliament,
            name='20. Wahlperiode'
        )

        # Create a federal district constituency with wahlkreis_id
        self.federal_constituency = Constituency.objects.create(
            parliament_term=self.federal_term,
            name='Berlin-Mitte',
            scope='FEDERAL_DISTRICT',
            wahlkreis_id='075',
            metadata={'state': 'Berlin'}
        )

        # Create state parliament
        self.state_parliament = Parliament.objects.create(
            name='Abgeordnetenhaus von Berlin',
            level='STATE',
            legislative_body='Abgeordnetenhaus',
            region='BE'
        )
        self.state_term = ParliamentTerm.objects.create(
            parliament=self.state_parliament,
            name='19. Wahlperiode'
        )

        # Create state list constituency
        self.state_constituency = Constituency.objects.create(
            parliament_term=self.state_term,
            name='Berlin',
            scope='STATE_LIST',
            metadata={'state': 'Berlin'}
        )

    @patch('letters.services.wahlkreis.AddressGeocoder.geocode')
    @patch('letters.services.wahlkreis.WahlkreisLocator.locate')
    def test_resolve_returns_wahlkreis_identifiers_and_constituencies(
        self, mock_wahlkreis_locate, mock_geocode
    ):
        """Test that resolve() returns Wahlkreis IDs and matching constituencies"""
        # Mock geocoding
        mock_geocode.return_value = (52.520, 13.405, True, None)

        # Mock Wahlkreis lookup - returns (wkr_nr, wkr_name, land_name)
        mock_wahlkreis_locate.return_value = (75, 'Berlin-Mitte', 'Berlin')

        resolver = WahlkreisResolver()
        result = resolver.resolve(
            street='Unter den Linden 1',
            postal_code='10117',
            city='Berlin'
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

**Step 2: Run test to verify it fails**

Run: `uv run python manage.py test letters.tests.test_wahlkreis_resolver -v`
Expected: ImportError (wahlkreis module doesn't exist yet)

**Step 3: Create WahlkreisResolver service**

Create: `website/letters/services/wahlkreis.py`

```python
# ABOUTME: Service for resolving addresses to Wahlkreis identifiers and Constituency objects.
# ABOUTME: Separates geographic Wahlkreise from parliamentary Constituencies.

from typing import Dict, List, Optional
import logging

from django.db.models import Q

from ..models import Constituency
from ..constants import normalize_german_state
from .geocoding import AddressGeocoder, WahlkreisLocator

logger = logging.getLogger('letters.services')


class WahlkreisResolver:
    """
    Resolve addresses to Wahlkreis identifiers and Constituency objects.

    Process:
    1. Geocode address → coordinates
    2. Look up Wahlkreis from GeoJSON → get federal/state Wahlkreis IDs
    3. Query Constituency objects by wahlkreis_id
    4. Add state-level list constituencies for the user's state
    """

    def __init__(self):
        self._geocoder = None
        self._wahlkreis_locator = None

    @property
    def geocoder(self):
        """Lazy-load AddressGeocoder."""
        if self._geocoder is None:
            self._geocoder = AddressGeocoder()
        return self._geocoder

    @property
    def wahlkreis_locator(self):
        """Lazy-load WahlkreisLocator."""
        if self._wahlkreis_locator is None:
            self._wahlkreis_locator = WahlkreisLocator()
        return self._wahlkreis_locator

    def resolve(
        self,
        street: Optional[str] = None,
        postal_code: Optional[str] = None,
        city: Optional[str] = None,
        country: str = 'DE'
    ) -> Dict:
        """
        Resolve address to Wahlkreis identifiers and Constituency objects.

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

        if not (street and postal_code and city):
            logger.warning("Incomplete address provided to WahlkreisResolver")
            return result

        # Step 1: Geocode address
        lat, lon, success, error = self.geocoder.geocode(street, postal_code, city, country)

        if not success or lat is None or lon is None:
            logger.warning(f"Geocoding failed: {error}")
            return result

        # Step 2: Look up Wahlkreis
        wahlkreis_result = self.wahlkreis_locator.locate(lat, lon)

        if not wahlkreis_result:
            logger.warning(f"No Wahlkreis found for coordinates {lat}, {lon}")
            return result

        wkr_nr, wkr_name, land_name = wahlkreis_result

        # Normalize to 3-digit string
        federal_wahlkreis_number = str(wkr_nr).zfill(3)
        result['federal_wahlkreis_number'] = federal_wahlkreis_number

        # For state, we use the same number for now (TODO: get actual state Wahlkreis)
        result['state_wahlkreis_number'] = federal_wahlkreis_number

        normalized_state = normalize_german_state(land_name)

        # Step 3: Find constituencies by wahlkreis_id
        constituencies = list(
            Constituency.objects.filter(
                wahlkreis_id=federal_wahlkreis_number,
                scope='FEDERAL_DISTRICT'
            )
        )

        # Step 4: Add state-level list constituencies
        if normalized_state:
            state_constituencies = Constituency.objects.filter(
                scope='STATE_LIST',
                metadata__state=normalized_state
            )
            constituencies.extend(state_constituencies)

        result['constituencies'] = constituencies

        logger.info(
            f"Resolved {street}, {postal_code} {city} to "
            f"Wahlkreis {federal_wahlkreis_number} with {len(constituencies)} constituencies"
        )

        return result
```

**Step 4: Run test to verify it passes**

Run: `uv run python manage.py test letters.tests.test_wahlkreis_resolver::WahlkreisResolverTests::test_resolve_returns_wahlkreis_identifiers_and_constituencies -v`
Expected: PASS

**Step 5: Commit the changes**

```bash
git add website/letters/services/wahlkreis.py website/letters/tests/test_wahlkreis_resolver.py
git commit -m "feat: add WahlkreisResolver service"
```

---

## Task 6: Update sync_wahlkreise command to populate wahlkreis_id

**Files:**
- Modify: `website/letters/management/commands/sync_wahlkreise.py:115-228`

**Step 1: Add method to sync constituencies with wahlkreis_id**

After the `_sync_constituencies_to_db()` method (around line 228), add a new method to update wahlkreis_id from GeoJSON:

```python
def _update_wahlkreis_ids(self, geojson_data: dict) -> int:
    """Update wahlkreis_id field on existing constituencies from GeoJSON."""
    updated_count = 0

    for feature in geojson_data.get('features', []):
        properties = feature.get('properties', {})
        wkr_nr = properties.get('WKR_NR')

        if not wkr_nr:
            continue

        # Normalize to 3-digit string
        wahlkreis_id = str(wkr_nr).zfill(3)

        # Find constituencies by metadata WKR_NR
        constituencies = Constituency.objects.filter(
            metadata__WKR_NR=wkr_nr,
            scope='FEDERAL_DISTRICT'
        )

        for constituency in constituencies:
            if constituency.wahlkreis_id != wahlkreis_id:
                constituency.wahlkreis_id = wahlkreis_id
                constituency.save(update_fields=['wahlkreis_id'])
                updated_count += 1
                self.stdout.write(
                    f"Updated {constituency.name} with wahlkreis_id={wahlkreis_id}"
                )

    return updated_count
```

**Step 2: Call the new method from handle()**

In the `handle()` method, after the `_sync_constituencies_to_db()` call (around line 117), add:

```python
# Update wahlkreis_id on existing constituencies
self.stdout.write("Updating wahlkreis_id fields on constituencies...")
updated = self._update_wahlkreis_ids(geojson_data)
self.stdout.write(self.style.SUCCESS(f"Updated {updated} constituencies with wahlkreis_id"))
```

**Step 3: Verify syntax**

Run: `uv run python manage.py check`
Expected: No errors

**Step 4: Commit the changes**

```bash
git add website/letters/management/commands/sync_wahlkreise.py
git commit -m "feat: populate wahlkreis_id when syncing Wahlkreise"
```

---

## Task 7: Create EU constituency in sync_wahlkreise

**Files:**
- Modify: `website/letters/management/commands/sync_wahlkreise.py:115-120`

**Step 1: Add method to create EU constituency**

After the `_update_wahlkreis_ids()` method, add:

```python
def _ensure_eu_constituency(self) -> None:
    """Ensure a Germany-wide EU constituency exists."""
    from letters.models import Parliament, ParliamentTerm, Constituency

    # Get or create EU parliament
    eu_parliament, _ = Parliament.objects.get_or_create(
        level='EU',
        region='DE',
        defaults={
            'name': 'Europäisches Parlament',
            'legislative_body': 'Europäisches Parlament'
        }
    )

    # Get or create current EU term
    eu_term, _ = ParliamentTerm.objects.get_or_create(
        parliament=eu_parliament,
        name='2024-2029',
        defaults={
            'start_date': '2024-07-16',
            'end_date': '2029-07-15'
        }
    )

    # Get or create EU constituency
    eu_constituency, created = Constituency.objects.get_or_create(
        parliament_term=eu_term,
        scope='EU_AT_LARGE',
        defaults={
            'name': 'Deutschland',
            'wahlkreis_id': 'DE',
            'metadata': {'country': 'DE'}
        }
    )

    if created:
        self.stdout.write(self.style.SUCCESS(
            f"Created EU constituency: {eu_constituency.name}"
        ))
    else:
        # Update wahlkreis_id if missing
        if not eu_constituency.wahlkreis_id:
            eu_constituency.wahlkreis_id = 'DE'
            eu_constituency.save(update_fields=['wahlkreis_id'])
            self.stdout.write(f"Updated EU constituency with wahlkreis_id=DE")
```

**Step 2: Call from handle()**

In the `handle()` method, before the constituency sync (around line 115), add:

```python
# Ensure EU constituency exists
self.stdout.write("Ensuring EU constituency exists...")
self._ensure_eu_constituency()
```

**Step 3: Verify syntax**

Run: `uv run python manage.py check`
Expected: No errors

**Step 4: Commit the changes**

```bash
git add website/letters/management/commands/sync_wahlkreise.py
git commit -m "feat: ensure EU constituency exists when syncing Wahlkreise"
```

---

## Task 8: Update ConstituencyLocator to use WahlkreisResolver

**Files:**
- Modify: `website/letters/services/constituency.py:107-186`

**Step 1: Write test for updated locate() method**

Modify: `website/letters/tests/test_address_matching.py` (around line 200)

Add import at top:
```python
from letters.services.wahlkreis import WahlkreisResolver
```

Update the test `test_locate_returns_constituencies_not_representatives` to:

```python
@patch('letters.services.wahlkreis.WahlkreisResolver.resolve')
def test_locate_returns_correct_constituency(self, mock_resolve):
    """Test that ConstituencyLocator.locate() returns constituencies."""
    from letters.models import Parliament, ParliamentTerm, Constituency

    # Create test data
    parliament = Parliament.objects.create(
        name='Bundestag',
        level='FEDERAL',
        legislative_body='Bundestag',
        region='DE'
    )
    term = ParliamentTerm.objects.create(
        parliament=parliament,
        name='20. Wahlperiode'
    )
    constituency = Constituency.objects.create(
        parliament_term=term,
        name='Berlin-Mitte',
        scope='FEDERAL_DISTRICT',
        wahlkreis_id='075'
    )

    # Mock WahlkreisResolver to return our test constituency
    mock_resolve.return_value = {
        'federal_wahlkreis_number': '075',
        'state_wahlkreis_number': '075',
        'eu_wahlkreis': 'DE',
        'constituencies': [constituency]
    }

    locator = ConstituencyLocator()
    constituencies = locator.locate(
        street='Unter den Linden 1',
        postal_code='10117',
        city='Berlin'
    )

    self.assertEqual(len(constituencies), 1)
    self.assertEqual(constituencies[0].id, constituency.id)
```

**Step 2: Run test to verify it fails**

Run: `uv run python manage.py test letters.tests.test_address_matching::FullAddressMatchingTests::test_locate_returns_correct_constituency -v`
Expected: FAIL (locate() doesn't use WahlkreisResolver yet)

**Step 3: Update ConstituencyLocator.locate() implementation**

Replace the `locate()` method (lines ~107-186) with:

```python
def locate(
    self,
    street: Optional[str] = None,
    postal_code: Optional[str] = None,
    city: Optional[str] = None,
    country: str = 'DE'
) -> List[Constituency]:
    """
    Locate constituencies by address or postal code.

    Args:
        street: Street name and number (optional)
        postal_code: Postal code / PLZ (optional)
        city: City name (optional)
        country: Country code (default: 'DE')

    Returns:
        List of Constituency objects for the located area

    Strategy:
    1. If full address provided (street + postal_code + city):
       - Use WahlkreisResolver to get Wahlkreis identifiers and constituencies
       - Return constituencies
    2. Fallback to PLZ-prefix matching if:
       - No street provided
       - WahlkreisResolver returns no constituencies
    """
    from .wahlkreis import WahlkreisResolver

    street = (street or '').strip()
    postal_code = (postal_code or '').strip()
    city = (city or '').strip()

    # Try full address-based lookup if we have all components
    if street and postal_code and city:
        try:
            resolver = WahlkreisResolver()
            result = resolver.resolve(street, postal_code, city, country)

            if result['constituencies']:
                logger.info(
                    "Address resolved to %d constituencies via WahlkreisResolver",
                    len(result['constituencies'])
                )
                return result['constituencies']

            logger.warning(
                "WahlkreisResolver found no constituencies, falling back to PLZ"
            )
        except Exception as e:
            logger.warning(
                "Error during WahlkreisResolver lookup for %s, %s %s: %s",
                street, postal_code, city, e
            )

    # Fallback to PLZ-based lookup
    if postal_code:
        return self._locate_by_plz(postal_code)

    # No parameters provided
    return []
```

**Step 4: Run test to verify it passes**

Run: `uv run python manage.py test letters.tests.test_address_matching::FullAddressMatchingTests::test_locate_returns_correct_constituency -v`
Expected: PASS

**Step 5: Commit the changes**

```bash
git add website/letters/services/constituency.py website/letters/tests/test_address_matching.py
git commit -m "refactor: use WahlkreisResolver in ConstituencyLocator.locate()"
```

---

## Task 9: Update identity verification service to use new structure

**Files:**
- Modify: `website/letters/services/identity.py`

**Step 1: Read existing identity service**

Run: `cat website/letters/services/identity.py | head -100`

Look for where constituencies are linked to verifications.

**Step 2: Update verification service to store Wahlkreis IDs and link constituencies**

Find the method that links constituencies (likely in `IdentityVerificationService`). Update it to:

1. Use `WahlkreisResolver` to get Wahlkreis identifiers and constituencies
2. Store Wahlkreis identifiers on the verification
3. Add all returned constituencies to the M2M relationship

Example implementation (adapt based on actual service structure):

```python
def link_address_to_verification(
    self,
    verification: IdentityVerification,
    street: str,
    postal_code: str,
    city: str,
    country: str = 'DE'
) -> bool:
    """Link address to verification via Wahlkreis resolution."""
    from .wahlkreis import WahlkreisResolver

    resolver = WahlkreisResolver()
    result = resolver.resolve(street, postal_code, city, country)

    if not result['constituencies']:
        return False

    # Store Wahlkreis identifiers
    verification.federal_wahlkreis_number = result['federal_wahlkreis_number']
    verification.state_wahlkreis_number = result['state_wahlkreis_number']
    verification.eu_wahlkreis = result['eu_wahlkreis']

    # Clear existing constituencies and add new ones
    verification.constituencies.clear()
    for constituency in result['constituencies']:
        verification.constituencies.add(constituency)

    verification.save()
    return True
```

**Step 3: Find and update tests for identity service**

Look for tests in `website/letters/tests/test_identity_verification.py` or similar.

Update tests to verify:
- Wahlkreis fields are populated
- constituencies M2M is populated

**Step 4: Run identity verification tests**

Run: `uv run python manage.py test letters.tests.test_identity_verification -v`
Expected: All tests pass

**Step 5: Commit the changes**

```bash
git add website/letters/services/identity.py website/letters/tests/test_identity_verification.py
git commit -m "refactor: update identity verification to use Wahlkreis fields"
```

---

## Task 10: Address PR review comments

**Files:**
- Modify: `website/letters/management/commands/query_representatives.py:65`
- Modify: `website/pyproject.toml`
- Modify: `website/letters/services/constituency.py:129`
- Modify: `website/letters/tests/test_address_matching.py:200-202`
- Modify: `website/letters/tests/test_wahlkreis_search.py:47,59`

**Step 1: Move Representative import to top**

In `query_representatives.py`, move the import statement from line 65 to the top of the file with other imports.

**Step 2: Add pyshp as dev dependency**

Run: `cd website && uv add --dev pyshp`

**Step 3: Update constituency.py docstring terminology**

Change line 129 from "Use WahlkreisLocator to find constituency" to "Use WahlkreisLocator to find Wahlkreis"

**Step 4: Move imports and rename test**

In `test_address_matching.py`:
- Move the imports from inside the test (line 202) to the top of the file
- Rename `test_locate_returns_constituencies_not_representatives` to `test_locate_returns_correct_constituency`

**Step 5: Investigate HTTP status codes for wahlkreis search**

Read the wahlkreis search view to understand what it currently returns. Check if invalid addresses should return 404 instead of 200.

Run: `cat website/letters/views.py | grep -A 30 "search_wahlkreis"`

Based on findings, update tests in `test_wahlkreis_search.py` if needed.

**Step 6: Review EU representative qualification logic**

Read the comment at `website/letters/models.py:247` about EU representatives.

The comment says: "EU representatives can represent a FEDERAL_LIST or STATE_LIST Constituency."

Update the logic at lines 246-247 and 264-265 to properly handle EU representative qualification based on constituency types.

**Step 7: Run all tests**

Run: `uv run python manage.py test letters -v`
Expected: All tests pass

**Step 8: Commit the changes**

```bash
git add website/letters/management/commands/query_representatives.py \
        website/pyproject.toml \
        website/letters/services/constituency.py \
        website/letters/tests/test_address_matching.py \
        website/letters/tests/test_wahlkreis_search.py \
        website/letters/models.py
git commit -m "fix: address PR review comments"
```

---

## Task 11: Run full test suite and verify

**Files:**
- All test files

**Step 1: Run complete test suite**

Run: `uv run python manage.py test letters -v`
Expected: All tests pass

**Step 2: Check for any migration issues**

Run: `uv run python manage.py makemigrations --check --dry-run`
Expected: No unapplied migrations

**Step 3: Test sync_wahlkreise command**

Run: `uv run python manage.py sync_wahlkreise --help`
Expected: Command help displays correctly

**Step 4: If all tests pass, commit any final fixes**

```bash
git add .
git commit -m "chore: final test fixes and verification"
```

---

## Task 12: Update documentation

**Files:**
- Create: `docs/architecture/wahlkreis-constituency-separation.md`

**Step 1: Create architecture documentation**

```markdown
# Wahlkreis-Constituency Separation

## Overview

This architecture separates **geographic Wahlkreise** (electoral districts) from **parliamentary Constituencies** to support the fact that a single address maps to multiple parliament levels.

## Concepts

### Wahlkreis (Electoral District)
- Geographic region used for elections
- An address has exactly 3 Wahlkreise:
  - EU Wahlkreis (all of Germany = 'DE')
  - Federal Wahlkreis (Bundestag, 1-299)
  - State Wahlkreis (Landtag, varies by state)

### Constituency
- Parliamentary representation unit for a specific term
- Usually maps 1:1 to a Wahlkreis (direct mandate winner)
- Can be different (e.g., state-level list when no direct mandate won)

## Data Model

### IdentityVerification
Stores Wahlkreis identifiers:
- `federal_wahlkreis_number`: CharField (e.g., "075")
- `state_wahlkreis_number`: CharField (state-specific)
- `eu_wahlkreis`: CharField (always "DE")

Links to constituencies:
- `constituencies`: ManyToMany to Constituency

### Constituency
Links to geographic Wahlkreis:
- `wahlkreis_id`: CharField (e.g., "075" for Berlin-Mitte)

## Address Resolution Flow

1. **Geocode** address → coordinates
2. **Look up Wahlkreis** from GeoJSON → federal/state Wahlkreis numbers
3. **Store identifiers** on IdentityVerification
4. **Query Constituencies** where wahlkreis_id matches
5. **Add state-level constituencies** (STATE_LIST) for user's state
6. **Store all** in constituencies M2M

## Services

### WahlkreisResolver
Resolves addresses to Wahlkreis identifiers and Constituency objects.

### ConstituencyLocator
Uses WahlkreisResolver for address-based lookups, with PLZ fallback.

## Commands

### sync_wahlkreise
- Downloads Wahlkreis GeoJSON data
- Creates all 299 federal constituencies
- Populates wahlkreis_id fields
- Ensures EU constituency exists
```

**Step 2: Commit documentation**

```bash
git add docs/architecture/wahlkreis-constituency-separation.md
git commit -m "docs: add Wahlkreis-Constituency separation architecture"
```

---

## Completion

All tasks complete! The implementation:
- ✅ Separates Wahlkreis identifiers from Constituency objects
- ✅ Supports multiple parliament levels per address
- ✅ Maintains backward compatibility through updated methods
- ✅ Includes comprehensive tests
- ✅ Addresses all PR review comments
- ✅ Documents the architecture

Next steps:
- Run the sync_wahlkreise command with real data
- Test with actual user addresses
- Verify representative qualification logic works correctly
