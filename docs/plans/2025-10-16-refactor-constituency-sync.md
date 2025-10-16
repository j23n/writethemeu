# Refactor Constituency Sync Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Refactor sync_wahlkreise and sync_representatives to use Abgeordnetenwatch API as single source of truth for constituencies, eliminating duplication and clarifying separation of concerns.

**Architecture:** sync_wahlkreise fetches ALL constituencies (districts + lists) from Abgeordnetenwatch API and enriches districts with GeoJSON boundary data. sync_representatives only links representatives to existing constituencies via external_id. WahlkreisResolver uses list_id for address→constituency lookup.

**Tech Stack:** Django, Abgeordnetenwatch API v2, GeoJSON, pyshp, shapely

---

## Task 1: Rename wahlkreis_id to list_id in database schema

**Files:**
- Create: `website/letters/migrations/XXXX_rename_wahlkreis_id_to_list_id.py`
- Modify: `website/letters/models.py` (Constituency model)

**Step 1: Create Django migration**

```bash
cd website
uv run python manage.py makemigrations letters --empty -n rename_wahlkreis_id_to_list_id
```

Expected: Creates new migration file

**Step 2: Write migration operations**

Edit the generated migration file:

```python
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('letters', 'PREVIOUS_MIGRATION'),  # Will be auto-filled
    ]

    operations = [
        # Rename field
        migrations.RenameField(
            model_name='constituency',
            old_name='wahlkreis_id',
            new_name='list_id',
        ),
        # Remove unique constraint (list_id is only unique per parliament_term)
        # Note: Check if there's an explicit unique constraint to remove
        # If wahlkreis_id has unique=True in model, this will be handled by RenameField
    ]
```

**Step 3: Update model definition**

In `website/letters/models.py`, find the Constituency model and change:

```python
# OLD:
wahlkreis_id = models.CharField(max_length=20, blank=True, null=True, unique=True)

# NEW:
list_id = models.CharField(
    max_length=20,
    blank=True,
    null=True,
    help_text="Identifier for WahlkreisResolver lookups (e.g., '001', 'BY-0001', 'BUND-BY-LIST')"
)
```

Also add a unique_together constraint if not already present:

```python
class Meta:
    unique_together = [['list_id', 'parliament_term']]
    # ... other meta options
```

**Step 4: Run migration**

```bash
uv run python manage.py migrate letters
```

Expected: Migration applies successfully

**Step 5: Commit**

```bash
git add website/letters/migrations/ website/letters/models.py
git commit -m "refactor: rename wahlkreis_id to list_id and adjust constraints

- Rename Constituency.wahlkreis_id to list_id for clarity
- Remove unique constraint (only unique per parliament_term)
- Add help text explaining list_id purpose

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 2: Add get_constituencies method to AbgeordnetenwatchAPI client

**Files:**
- Modify: `website/letters/services/abgeordnetenwatch_api_client.py`
- Test: `website/letters/tests/test_abgeordnetenwatch_api_client.py`

**Step 1: Write failing test**

Create or update `website/letters/tests/test_abgeordnetenwatch_api_client.py`:

```python
from unittest.mock import patch, Mock
from django.test import TestCase
from letters.services.abgeordnetenwatch_api_client import AbgeordnetenwatchAPI


class GetConstituenciesTests(TestCase):
    """Test the get_constituencies method."""

    @patch('letters.services.abgeordnetenwatch_api_client.AbgeordnetenwatchAPI.fetch_paginated')
    def test_get_constituencies_fetches_with_parliament_period_filter(self, mock_fetch):
        """Test that get_constituencies calls fetch_paginated with correct params."""
        mock_fetch.return_value = [
            {'id': 14205, 'number': 299, 'name': 'Homburg'},
            {'id': 14204, 'number': 298, 'name': 'Saarlouis'},
        ]

        result = AbgeordnetenwatchAPI.get_constituencies(parliament_period_id=161)

        mock_fetch.assert_called_once_with('constituencies', {'parliament_period': 161})
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['number'], 299)

    @patch('letters.services.abgeordnetenwatch_api_client.AbgeordnetenwatchAPI.fetch_paginated')
    def test_get_electoral_lists_fetches_with_parliament_period_filter(self, mock_fetch):
        """Test that get_electoral_lists calls fetch_paginated with correct params."""
        mock_fetch.return_value = [
            {'id': 733, 'name': 'Landesliste Thüringen'},
            {'id': 732, 'name': 'Landesliste Schleswig-Holstein'},
        ]

        result = AbgeordnetenwatchAPI.get_electoral_lists(parliament_period_id=161)

        mock_fetch.assert_called_once_with('electoral-lists', {'parliament_period': 161})
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]['name'], 'Landesliste Thüringen')
```

**Step 2: Run test to verify it fails**

```bash
uv run python manage.py test letters.tests.test_abgeordnetenwatch_api_client::GetConstituenciesTests -v
```

Expected: FAIL with "AttributeError: ... has no attribute 'get_constituencies'"

**Step 3: Implement methods in API client**

In `website/letters/services/abgeordnetenwatch_api_client.py`, add:

```python
@classmethod
def get_constituencies(cls, parliament_period_id: int) -> List[Dict]:
    """Fetch all constituencies for a given parliament period."""
    return cls.fetch_paginated('constituencies', {'parliament_period': parliament_period_id})

@classmethod
def get_electoral_lists(cls, parliament_period_id: int) -> List[Dict]:
    """Fetch all electoral lists for a given parliament period."""
    return cls.fetch_paginated('electoral-lists', {'parliament_period': parliament_period_id})
```

**Step 4: Run test to verify it passes**

```bash
uv run python manage.py test letters.tests.test_abgeordnetenwatch_api_client::GetConstituenciesTests -v
```

Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add website/letters/services/abgeordnetenwatch_api_client.py website/letters/tests/test_abgeordnetenwatch_api_client.py
git commit -m "feat: add get_constituencies and get_electoral_lists to API client

- Add methods to fetch constituencies and electoral lists by parliament period
- Include tests for both methods

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 3: Move _normalize_properties to WahlkreisLocator

**Files:**
- Modify: `website/letters/services/geocoding.py` (WahlkreisLocator class)
- Modify: `website/letters/management/commands/sync_wahlkreise.py`

**Step 1: Verify _normalize_properties is identical in both locations**

```bash
# Compare the two implementations
diff <(sed -n '/def _normalize_properties/,/^$/p' website/letters/services/geocoding.py) \
     <(sed -n '/def _normalize_properties/,/^    def \|^$/p' website/letters/management/commands/sync_wahlkreise.py)
```

Expected: No differences (or note what's different)

**Step 2: Remove _normalize_properties from sync_wahlkreise**

In `website/letters/management/commands/sync_wahlkreise.py`, delete lines 805-867 (the `_normalize_properties` method).

Update the one place it's called (line 877 in `_normalize_state_geojson`):

```python
# OLD:
wkr_nr, wkr_name = self._normalize_properties(props)

# NEW:
from letters.services.geocoding import WahlkreisLocator
wkr_nr, wkr_name = WahlkreisLocator._normalize_properties(props)
```

But actually, since `_normalize_state_geojson` is only used during GeoJSON processing, we can access it via the locator. Better approach - keep it as a static method:

In `website/letters/services/geocoding.py`, change line 316:

```python
# OLD:
def _normalize_properties(self, props: dict) -> tuple:

# NEW:
@staticmethod
def _normalize_properties(props: dict) -> tuple:
```

Then in sync_wahlkreise, change line 877:

```python
# OLD:
wkr_nr, wkr_name = self._normalize_properties(props)

# NEW:
from letters.services.geocoding import WahlkreisLocator
wkr_nr, wkr_name = WahlkreisLocator._normalize_properties(props)
```

**Step 3: Remove duplicate method from sync_wahlkreise**

Delete the entire `_normalize_properties` method (lines 805-867) from `sync_wahlkreise.py`.

Update the comment on line 812 that says:

```python
# Note: This is a copy of WahlkreisLocator._normalize_properties
# to avoid circular dependencies and file loading issues in tests.
```

Remove this comment since we're now using the single source of truth.

**Step 4: Run existing tests**

```bash
uv run python manage.py test letters.tests.test_wahlkreis_resolver -v
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add website/letters/services/geocoding.py website/letters/management/commands/sync_wahlkreise.py
git commit -m "refactor: consolidate _normalize_properties in WahlkreisLocator

- Remove duplicate _normalize_properties from sync_wahlkreise
- Make WahlkreisLocator._normalize_properties static for reuse
- Use single source of truth for property normalization

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 4: Refactor sync_wahlkreise to fetch from API

**Files:**
- Modify: `website/letters/management/commands/sync_wahlkreise.py`

**Step 1: Add _sync_constituencies_from_api method**

Add this new method to the Command class in `sync_wahlkreise.py`:

```python
@transaction.atomic
def _sync_constituencies_from_api(self, parliament_id: int, parliament_term_id: int, level: str) -> dict:
    """
    Sync constituencies from Abgeordnetenwatch API for a given parliament term.

    Args:
        parliament_id: Parliament ID from API
        parliament_term_id: Parliament term/period ID from API
        level: 'FEDERAL', 'STATE', or 'EU'

    Returns:
        dict with stats: {'created': int, 'updated': int}
    """
    from letters.services.abgeordnetenwatch_api_client import AbgeordnetenwatchAPI

    stats = {'created': 0, 'updated': 0}

    # Fetch constituencies (districts)
    constituencies_data = AbgeordnetenwatchAPI.get_constituencies(parliament_term_id)

    # Fetch electoral lists
    electoral_lists_data = AbgeordnetenwatchAPI.get_electoral_lists(parliament_term_id)

    # Get or create Parliament and ParliamentTerm
    parliament, _ = Parliament.objects.get_or_create(
        metadata__api_id=parliament_id,
        defaults={
            'name': f'Parliament {parliament_id}',  # Will be updated by sync_representatives
            'level': level,
            'legislative_body': '',
            'region': '',
            'metadata': {'api_id': parliament_id, 'source': 'abgeordnetenwatch'}
        }
    )

    term, _ = ParliamentTerm.objects.get_or_create(
        metadata__period_id=parliament_term_id,
        parliament=parliament,
        defaults={
            'name': f'Term {parliament_term_id}',  # Will be updated by sync_representatives
            'metadata': {'period_id': parliament_term_id, 'source': 'abgeordnetenwatch'}
        }
    )

    # Process district constituencies
    for const_data in constituencies_data:
        external_id = str(const_data['id'])
        number = const_data.get('number')
        name = const_data.get('name', '')
        label = const_data.get('label', f"{number} - {name}")

        # Determine scope based on parliament level
        if level == 'FEDERAL':
            scope = 'FEDERAL_DISTRICT'
        elif level == 'STATE':
            scope = 'STATE_DISTRICT'
        else:
            continue  # EU doesn't have districts

        # Create or update constituency
        constituency, created = Constituency.objects.update_or_create(
            external_id=external_id,
            defaults={
                'parliament_term': term,
                'name': label,
                'scope': scope,
                'metadata': {
                    'api_id': const_data['id'],
                    'number': number,
                    'source': 'abgeordnetenwatch',
                    'raw': const_data
                },
                'last_synced_at': timezone.now()
            }
        )

        if created:
            stats['created'] += 1
        else:
            stats['updated'] += 1

    # Process electoral lists
    for list_data in electoral_lists_data:
        external_id = str(list_data['id'])
        name = list_data.get('name', '')
        label = list_data.get('label', name)

        # Determine scope based on name pattern
        name_lower = name.lower()
        if level == 'FEDERAL':
            if 'bundesliste' in name_lower:
                scope = 'FEDERAL_LIST'
            else:
                scope = 'FEDERAL_STATE_LIST'
        elif level == 'STATE':
            if 'regional' in name_lower or 'wahlkreis' in name_lower:
                scope = 'STATE_REGIONAL_LIST'
            else:
                scope = 'STATE_LIST'
        elif level == 'EU':
            scope = 'EU_AT_LARGE'
        else:
            scope = 'OTHER'

        # Create or update constituency
        constituency, created = Constituency.objects.update_or_create(
            external_id=external_id,
            defaults={
                'parliament_term': term,
                'name': label,
                'scope': scope,
                'metadata': {
                    'api_id': list_data['id'],
                    'source': 'abgeordnetenwatch',
                    'raw': list_data
                },
                'last_synced_at': timezone.now()
            }
        )

        if created:
            stats['created'] += 1
        else:
            stats['updated'] += 1

    return stats
```

**Step 2: Update handle() method to use new approach**

This is a large change. In `sync_wahlkreise.py`, modify the `handle()` method to add a new `--api-sync` mode:

```python
def add_arguments(self, parser):
    # ... existing arguments ...

    parser.add_argument(
        "--api-sync",
        action="store_true",
        help="Sync constituencies from Abgeordnetenwatch API (new approach)",
    )
```

Then in `handle()`, add at the beginning:

```python
def handle(self, *args, **options):
    # Handle --api-sync flag (new approach)
    if options.get('api_sync'):
        self._handle_api_sync()
        return

    # ... rest of existing handle() logic for GeoJSON sync ...
```

**Step 3: Add _handle_api_sync method**

```python
def _handle_api_sync(self):
    """Sync constituencies from Abgeordnetenwatch API for all parliaments."""
    from letters.services.abgeordnetenwatch_api_client import AbgeordnetenwatchAPI

    self.stdout.write("Syncing constituencies from Abgeordnetenwatch API...")

    # Get all parliaments
    parliaments_data = AbgeordnetenwatchAPI.get_parliaments()

    for parliament_data in parliaments_data:
        parliament_id = parliament_data['id']
        parliament_name = parliament_data['label']

        # Determine level
        if parliament_name == 'EU-Parlament':
            level = 'EU'
        elif parliament_name == 'Bundestag':
            level = 'FEDERAL'
        else:
            level = 'STATE'

        self.stdout.write(f"\n{parliament_name} ({level})...")

        # Get parliament periods
        periods = AbgeordnetenwatchAPI.get_parliament_periods(parliament_id)
        if not periods:
            self.stdout.write(f"  No periods found")
            continue

        # Sync current period only
        current_period = periods[0]
        period_id = current_period['id']
        period_name = current_period['label']

        self.stdout.write(f"  Period: {period_name}")

        stats = self._sync_constituencies_from_api(parliament_id, period_id, level)
        self.stdout.write(
            self.style.SUCCESS(
                f"  Created {stats['created']}, Updated {stats['updated']} constituencies"
            )
        )
```

**Step 4: Test the new API sync**

```bash
uv run python manage.py sync_wahlkreise --api-sync
```

Expected: Syncs constituencies from API, shows progress

**Step 5: Commit**

```bash
git add website/letters/management/commands/sync_wahlkreise.py
git commit -m "feat: add API-based constituency sync to sync_wahlkreise

- Add _sync_constituencies_from_api method
- Add _handle_api_sync to orchestrate API sync
- Add --api-sync flag to enable new approach
- Fetches all constituencies and electoral lists from API
- Creates Parliament and ParliamentTerm records

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 5: Add list_id generation for district constituencies

**Files:**
- Modify: `website/letters/management/commands/sync_wahlkreise.py`

**Step 1: Add _generate_list_id_for_district method**

Add this helper method to the Command class:

```python
@staticmethod
def _generate_list_id_for_district(number: int, level: str, state_code: Optional[str] = None) -> str:
    """
    Generate list_id for a district constituency.

    Args:
        number: Constituency number from API
        level: 'FEDERAL' or 'STATE'
        state_code: State code (e.g., 'BY', 'BE') for state-level districts

    Returns:
        list_id string (e.g., '001', '299', 'BY-0001')
    """
    if level == 'FEDERAL':
        return f"{number:03d}"
    elif level == 'STATE' and state_code:
        return f"{state_code}-{number:04d}"
    else:
        return f"{number:03d}"  # Fallback
```

**Step 2: Add _generate_list_id_for_electoral_list method**

```python
@staticmethod
def _generate_list_id_for_electoral_list(
    list_name: str,
    level: str,
    parliament_name: str
) -> str:
    """
    Generate list_id for an electoral list constituency.

    Args:
        list_name: Name of electoral list from API
        level: 'FEDERAL', 'STATE', or 'EU'
        parliament_name: Name of parliament (for extracting state)

    Returns:
        list_id string (e.g., 'BUND-BY-LIST', 'LAND-BY-LIST', 'EU-DE-LIST')
    """
    from letters.constants import get_state_code, normalize_german_state

    name_lower = list_name.lower()

    if level == 'EU':
        return 'EU-DE-LIST'

    # Extract state from name
    # Examples: "Landesliste Bayern", "Wahlkreisliste Oberbayern"
    state_name = None
    for word in list_name.split():
        normalized = normalize_german_state(word)
        if normalized:
            state_name = normalized
            break

    # If no state found in name, try parliament name
    if not state_name:
        state_name = normalize_german_state(parliament_name)

    state_code = get_state_code(state_name) if state_name else 'XX'

    if level == 'FEDERAL':
        return f'BUND-{state_code}-LIST'
    elif level == 'STATE':
        return f'LAND-{state_code}-LIST'
    else:
        return f'{state_code}-LIST'
```

**Step 3: Update _sync_constituencies_from_api to set list_id**

In the district processing loop, after determining scope:

```python
# Generate list_id for districts
list_id = self._generate_list_id_for_district(number, level, state_code=None)  # Will add state_code extraction next

# Create or update constituency
constituency, created = Constituency.objects.update_or_create(
    external_id=external_id,
    defaults={
        'parliament_term': term,
        'name': label,
        'scope': scope,
        'list_id': list_id,  # ADD THIS
        'metadata': {
            'api_id': const_data['id'],
            'number': number,
            'source': 'abgeordnetenwatch',
            'raw': const_data
        },
        'last_synced_at': timezone.now()
    }
)
```

In the electoral list processing loop:

```python
# Generate list_id for lists
list_id = self._generate_list_id_for_electoral_list(name, level, parliament.name)

# Create or update constituency
constituency, created = Constituency.objects.update_or_create(
    external_id=external_id,
    defaults={
        'parliament_term': term,
        'name': label,
        'scope': scope,
        'list_id': list_id,  # ADD THIS
        'metadata': {
            'api_id': list_data['id'],
            'source': 'abgeordnetenwatch',
            'raw': list_data
        },
        'last_synced_at': timezone.now()
    }
)
```

**Step 4: Test list_id generation**

```bash
uv run python manage.py sync_wahlkreise --api-sync
# Then check a few constituencies
uv run python manage.py shell
```

```python
from letters.models import Constituency
# Check federal district
fed = Constituency.objects.filter(scope='FEDERAL_DISTRICT').first()
print(f"Federal district list_id: {fed.list_id}")  # Should be like "001"

# Check federal state list
fed_list = Constituency.objects.filter(scope='FEDERAL_STATE_LIST').first()
print(f"Federal state list list_id: {fed_list.list_id}")  # Should be like "BUND-BY-LIST"
```

Expected: list_id values are correctly formatted

**Step 5: Commit**

```bash
git add website/letters/management/commands/sync_wahlkreise.py
git commit -m "feat: generate list_id for all constituencies from API

- Add _generate_list_id_for_district helper
- Add _generate_list_id_for_electoral_list helper
- Set list_id on all constituencies during API sync
- Format: '001' for federal districts, 'BY-0001' for state districts
- Format: 'BUND-BY-LIST', 'LAND-BY-LIST', 'EU-DE-LIST' for lists

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 6: Enrich district constituencies with GeoJSON data

**Files:**
- Modify: `website/letters/management/commands/sync_wahlkreise.py`

**Step 1: Add _enrich_constituencies_with_geojson method**

```python
def _enrich_constituencies_with_geojson(self, geojson_path: Path, level: str, state_code: Optional[str] = None):
    """
    Enrich existing constituencies with list_id derived from GeoJSON.

    This updates constituencies that were created from API with precise list_id
    values extracted from official GeoJSON boundary files.

    Args:
        geojson_path: Path to GeoJSON file
        level: 'FEDERAL' or 'STATE'
        state_code: State code (e.g., 'BY') for state-level GeoJSON
    """
    from letters.services.geocoding import WahlkreisLocator

    # Load GeoJSON
    with open(geojson_path, 'r', encoding='utf-8') as f:
        geojson_data = json.load(f)

    updated_count = 0

    for feature in geojson_data.get('features', []):
        properties = feature.get('properties', {})

        # Normalize properties
        wkr_nr, wkr_name = WahlkreisLocator._normalize_properties(properties)

        if not wkr_nr:
            continue

        # Generate list_id from GeoJSON
        if level == 'FEDERAL':
            list_id = f"{wkr_nr:03d}"
        elif level == 'STATE' and state_code:
            list_id = f"{state_code}-{wkr_nr:04d}"
        else:
            continue

        # Find constituency by number (stored in metadata)
        # We can't use list_id yet because it might not match exactly
        scope = 'FEDERAL_DISTRICT' if level == 'FEDERAL' else 'STATE_DISTRICT'

        constituencies = Constituency.objects.filter(
            scope=scope,
            metadata__number=wkr_nr
        )

        for constituency in constituencies:
            if constituency.list_id != list_id:
                constituency.list_id = list_id
                constituency.save(update_fields=['list_id'])
                updated_count += 1
                self.stdout.write(f"  Updated {constituency.name} with list_id={list_id}")

    return updated_count
```

**Step 2: Update handle() to call enrichment after GeoJSON download**

In the existing GeoJSON download logic (around line 255), after saving the GeoJSON file:

```python
# After: output_path.write_text(geojson_text, encoding="utf-8")

self.stdout.write(self.style.SUCCESS(f"Saved Wahlkreis data to {output_path}"))

# Enrich constituencies with GeoJSON data
if not options.get('state'):  # Federal GeoJSON
    self.stdout.write("Enriching federal constituencies with GeoJSON list_id...")
    updated = self._enrich_constituencies_with_geojson(output_path, level='FEDERAL')
    self.stdout.write(self.style.SUCCESS(f"Updated {updated} federal constituencies"))
```

For state GeoJSON, in `_fetch_state()` method:

```python
# After saving state GeoJSON
self.stdout.write(
    self.style.SUCCESS(f"✓ Saved {state_code} data to {output_path}")
)

# Enrich constituencies
self.stdout.write(f"  Enriching {state_code} constituencies with GeoJSON list_id...")
updated = self._enrich_constituencies_with_geojson(output_path, level='STATE', state_code=state_code)
self.stdout.write(self.style.SUCCESS(f"  Updated {updated} constituencies"))
```

**Step 3: Test GeoJSON enrichment**

```bash
# First sync from API
uv run python manage.py sync_wahlkreise --api-sync

# Then download and enrich with federal GeoJSON
uv run python manage.py sync_wahlkreise --force

# Check results
uv run python manage.py shell
```

```python
from letters.models import Constituency
# Check that list_id is set from GeoJSON
const = Constituency.objects.filter(scope='FEDERAL_DISTRICT', metadata__number=1).first()
print(f"Constituency: {const.name}")
print(f"list_id: {const.list_id}")  # Should be "001"
```

Expected: list_id values match GeoJSON WKR_NR format

**Step 4: Commit**

```bash
git add website/letters/management/commands/sync_wahlkreise.py
git commit -m "feat: enrich constituencies with GeoJSON list_id

- Add _enrich_constituencies_with_geojson method
- Update GeoJSON download flow to call enrichment
- Matches constituencies by number, updates list_id from GeoJSON
- Ensures list_id accuracy for address-based constituency lookup

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 7: Refactor sync_representatives to use external_id

**Files:**
- Modify: `website/letters/services/representative_sync.py`

**Step 1: Update _handle_direct_mandate to find by external_id**

In `representative_sync.py`, replace the `_handle_direct_mandate` method (lines 401-435):

```python
def _handle_direct_mandate(self, parliament: Parliament, term: ParliamentTerm, electoral: Dict) -> Optional[Constituency]:
    """Find existing constituency by API external_id."""
    const_data = electoral.get('constituency') or {}
    constituency_id = const_data.get('id')

    if not constituency_id:
        logger.warning("Direct mandate has no constituency ID in electoral data")
        return None

    # Find constituency by external_id (Abgeordnetenwatch constituency ID)
    try:
        constituency = Constituency.objects.get(
            external_id=str(constituency_id),
            parliament_term=term
        )
        return constituency
    except Constituency.DoesNotExist:
        logger.error(
            "Constituency not found for external_id=%s, term=%s. "
            "Run sync_wahlkreise --api-sync first.",
            constituency_id,
            term.name
        )
        return None
```

**Step 2: Update _determine_constituencies for list mandates**

In `_determine_constituencies` method, update the list constituency handling:

```python
def _determine_constituencies(
    self,
    parliament: Parliament,
    term: ParliamentTerm,
    electoral: Dict,
    representative: Representative,
) -> Iterable[Constituency]:
    """Determine which constituencies a representative belongs to."""

    # For direct mandates, find the district constituency
    mandate_won = electoral.get('mandate_won')
    if mandate_won == 'constituency':
        constituency = self._handle_direct_mandate(parliament, term, electoral)
        if constituency:
            yield constituency

    # For list mandates, find the electoral list constituency
    electoral_list = electoral.get('electoral_list')
    if electoral_list:
        list_id = electoral_list.get('id')
        if list_id:
            try:
                list_constituency = Constituency.objects.get(
                    external_id=str(list_id),
                    parliament_term=term
                )
                yield list_constituency
            except Constituency.DoesNotExist:
                logger.error(
                    "Electoral list constituency not found for external_id=%s, term=%s. "
                    "Run sync_wahlkreise --api-sync first.",
                    list_id,
                    term.name
                )
```

**Step 3: Delete _get_or_create_constituency method**

Remove the entire `_get_or_create_constituency` method (lines 468-534) since we no longer create constituencies.

**Step 4: Update _determine_federal_list_scope - DELETE IT**

Delete the `_determine_federal_list_scope` method (lines 451-465) - no longer needed.

Delete the `_build_list_name` method (lines 438-449) - no longer needed.

**Step 5: Simplify _determine_constituencies**

After all changes, the method should look like:

```python
def _determine_constituencies(
    self,
    parliament: Parliament,
    term: ParliamentTerm,
    electoral: Dict,
    representative: Representative,
) -> Iterable[Constituency]:
    """Determine which constituencies a representative belongs to by looking up API IDs."""

    # Direct mandate constituency
    constituency_data = electoral.get('constituency')
    if constituency_data:
        constituency_id = constituency_data.get('id')
        if constituency_id:
            try:
                yield Constituency.objects.get(
                    external_id=str(constituency_id),
                    parliament_term=term
                )
            except Constituency.DoesNotExist:
                logger.error(
                    "Constituency not found for external_id=%s. Run sync_wahlkreise --api-sync first.",
                    constituency_id
                )

    # Electoral list constituency
    electoral_list = electoral.get('electoral_list')
    if electoral_list:
        list_id = electoral_list.get('id')
        if list_id:
            try:
                yield Constituency.objects.get(
                    external_id=str(list_id),
                    parliament_term=term
                )
            except Constituency.DoesNotExist:
                logger.error(
                    "Electoral list not found for external_id=%s. Run sync_wahlkreise --api-sync first.",
                    list_id
                )
```

**Step 6: Run sync_representatives to test**

```bash
# First ensure constituencies exist
uv run python manage.py sync_wahlkreise --api-sync

# Then sync representatives
uv run python manage.py sync_representatives --level federal --dry-run
```

Expected: No errors about creating constituencies

**Step 7: Commit**

```bash
git add website/letters/services/representative_sync.py
git commit -m "refactor: simplify sync_representatives to only lookup constituencies

- Remove all constituency creation logic
- Find constituencies by external_id only
- Delete _get_or_create_constituency method
- Delete helper methods no longer needed
- Log errors if constituencies not found (must run sync_wahlkreise first)

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 8: Update WahlkreisResolver to use list_id

**Files:**
- Modify: `website/letters/services/wahlkreis.py`

**Step 1: Update resolve() to use list_id**

In `wahlkreis.py`, update the constituency lookup sections (around lines 119-136):

```python
# OLD (line 120):
federal_constituencies = list(
    Constituency.objects.filter(
        wahlkreis_id=federal_wahlkreis_number,
        scope='FEDERAL_DISTRICT'
    )
)

# NEW:
federal_constituencies = list(
    Constituency.objects.filter(
        list_id=federal_wahlkreis_number,
        scope='FEDERAL_DISTRICT'
    )
)

# OLD (line 131):
state_district_constituencies = list(
    Constituency.objects.filter(
        wahlkreis_id=state_wahlkreis_number,
        scope='STATE_DISTRICT'
    )
)

# NEW:
state_district_constituencies = list(
    Constituency.objects.filter(
        list_id=state_wahlkreis_number,
        scope='STATE_DISTRICT'
    )
)
```

**Step 2: Run tests**

```bash
uv run python manage.py test letters.tests.test_wahlkreis_resolver -v
```

Expected: Tests pass (or need updating if they reference wahlkreis_id)

**Step 3: Update any test fixtures if needed**

If tests fail, update test code in `website/letters/tests/test_wahlkreis_resolver.py`:

```python
# Change any references from wahlkreis_id to list_id
# OLD:
constituency = Constituency.objects.create(
    ...,
    wahlkreis_id='001'
)

# NEW:
constituency = Constituency.objects.create(
    ...,
    list_id='001'
)
```

**Step 4: Commit**

```bash
git add website/letters/services/wahlkreis.py website/letters/tests/
git commit -m "refactor: update WahlkreisResolver to use list_id

- Replace wahlkreis_id with list_id in constituency lookups
- Update tests to use list_id field

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 9: Update query commands to use list_id

**Files:**
- Modify: `website/letters/management/commands/query_wahlkreis.py`
- Modify: `website/letters/management/commands/query_representatives.py`

**Step 1: Update query_wahlkreis.py**

In `query_wahlkreis.py`, line 50 and 51:

```python
# OLD:
if c.wahlkreis_id:
    self.stdout.write(f"  WK ID:      {c.wahlkreis_id}")

# NEW:
if c.list_id:
    self.stdout.write(f"  List ID:    {c.list_id}")
```

**Step 2: Test query command**

```bash
uv run python manage.py query_wahlkreis "Unter den Linden 1, 10117 Berlin"
```

Expected: Shows "List ID: 075" or similar

**Step 3: Check query_representatives (likely no changes needed)**

Review `query_representatives.py` to ensure it doesn't reference wahlkreis_id:

```bash
grep -n "wahlkreis_id" website/letters/management/commands/query_representatives.py
```

Expected: No matches (it uses WahlkreisResolver which we already updated)

**Step 4: Commit**

```bash
git add website/letters/management/commands/
git commit -m "refactor: update query commands to use list_id

- Update query_wahlkreis to display list_id instead of wahlkreis_id
- Verify query_representatives works with updated resolver

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 10: Remove obsolete code from sync_wahlkreise

**Files:**
- Modify: `website/letters/management/commands/sync_wahlkreise.py`

**Step 1: Remove _sync_constituencies_to_db method**

Delete lines 350-440 (the old `_sync_constituencies_to_db` method for federal constituencies).

**Step 2: Remove _sync_state_constituencies_to_db method**

Delete lines 518-633 (the old `_sync_state_constituencies_to_db` method).

**Step 3: Remove _update_wahlkreis_ids method**

Delete lines 442-471 (the `_update_wahlkreis_ids` method - no longer needed).

**Step 4: Remove _ensure_eu_constituency method**

Delete lines 473-516 (the `_ensure_eu_constituency` method - now handled by API sync).

**Step 5: Update handle() to remove old sync calls**

In `handle()` method, remove these calls (around lines 256-271):

```python
# DELETE THESE:
# Ensure EU constituency exists
self.stdout.write("Ensuring EU constituency exists...")
self._ensure_eu_constituency()

# Sync constituencies to database
self.stdout.write("Syncing constituencies to database...")
stats = self._sync_constituencies_to_db(geojson_data)
self.stdout.write(self.style.SUCCESS(
    f"Created {stats['created']} and updated {stats['updated']} constituencies"
))

# Update wahlkreis_id on existing constituencies
self.stdout.write("Updating wahlkreis_id fields on constituencies...")
updated = self._update_wahlkreis_ids(geojson_data)
self.stdout.write(self.style.SUCCESS(f"Updated {updated} constituencies with wahlkreis_id"))
```

Replace with:

```python
# Enrich constituencies with GeoJSON data
self.stdout.write("Enriching constituencies with GeoJSON list_id...")
updated = self._enrich_constituencies_with_geojson(output_path, level='FEDERAL')
self.stdout.write(self.style.SUCCESS(f"Updated {updated} constituencies"))
```

**Step 6: Remove from _fetch_state as well**

In `_fetch_state()` method, remove the database sync calls (around lines 719-732):

```python
# DELETE THESE:
# Sync to database
self.stdout.write(f"  Syncing constituencies to database...")
stats = self._sync_state_constituencies_to_db(state_code, geojson_data)

if stats.get('skipped'):
    self.stdout.write(
        self.style.WARNING(f"  Database sync skipped for {state_code}")
    )
else:
    self.stdout.write(
        self.style.SUCCESS(
            f"  ✓ Created {stats['created']} and updated {stats['updated']} constituencies"
        )
    )
```

Already replaced with enrichment call in previous task.

**Step 7: Run tests to ensure nothing broke**

```bash
uv run python manage.py test letters -v
```

Expected: All tests pass

**Step 8: Commit**

```bash
git add website/letters/management/commands/sync_wahlkreise.py
git commit -m "refactor: remove obsolete constituency creation from sync_wahlkreise

- Delete _sync_constituencies_to_db (federal)
- Delete _sync_state_constituencies_to_db (state)
- Delete _update_wahlkreis_ids (no longer needed)
- Delete _ensure_eu_constituency (handled by API sync)
- GeoJSON files now only used for list_id enrichment

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 11: Write integration test for full sync flow

**Files:**
- Create: `website/letters/tests/test_constituency_sync_integration.py`

**Step 1: Write integration test**

```python
# ABOUTME: Integration test for constituency sync flow
# ABOUTME: Tests the complete flow: API sync -> GeoJSON enrichment -> representative linking

from unittest.mock import patch, Mock
from django.test import TestCase
from letters.models import Parliament, ParliamentTerm, Constituency, Representative
from letters.services.representative_sync import RepresentativeSyncService


class ConstituencySyncIntegrationTest(TestCase):
    """Test the complete constituency sync flow."""

    def setUp(self):
        """Set up test data."""
        self.bundestag = Parliament.objects.create(
            name='Bundestag',
            level='FEDERAL',
            region='DE',
            legislative_body='Bundestag'
        )

        self.term = ParliamentTerm.objects.create(
            parliament=self.bundestag,
            name='Bundestag 2025 - 2029',
            metadata={'period_id': 161}
        )

    @patch('letters.services.abgeordnetenwatch_api_client.AbgeordnetenwatchAPI.get_constituencies')
    def test_api_sync_creates_constituencies_with_external_id(self, mock_get_constituencies):
        """Test that API sync creates constituencies with external_id."""
        mock_get_constituencies.return_value = [
            {
                'id': 14205,
                'number': 299,
                'name': 'Homburg',
                'label': '299 - Homburg (Bundestag 2025 - 2029)'
            },
            {
                'id': 14204,
                'number': 298,
                'name': 'Saarlouis',
                'label': '298 - Saarlouis (Bundestag 2025 - 2029)'
            }
        ]

        # Run sync
        from letters.management.commands.sync_wahlkreise import Command
        cmd = Command()
        stats = cmd._sync_constituencies_from_api(
            parliament_id=5,
            parliament_term_id=161,
            level='FEDERAL'
        )

        # Verify constituencies created
        self.assertEqual(stats['created'], 2)

        # Verify external_id set correctly
        const1 = Constituency.objects.get(external_id='14205')
        self.assertEqual(const1.metadata['number'], 299)
        self.assertEqual(const1.name, '299 - Homburg (Bundestag 2025 - 2029)')

        const2 = Constituency.objects.get(external_id='14204')
        self.assertEqual(const2.metadata['number'], 298)

    def test_sync_representatives_finds_constituencies_by_external_id(self):
        """Test that sync_representatives links to constituencies by external_id."""
        # Create constituency
        constituency = Constituency.objects.create(
            external_id='14205',
            parliament_term=self.term,
            name='299 - Homburg',
            scope='FEDERAL_DISTRICT',
            list_id='299'
        )

        # Mock mandate data
        mandate = {
            'id': 12345,
            'type': 'mandate',
            'start_date': '2025-02-23',
            'politician': {
                'id': 999,
                'label': 'Test Person'
            },
            'electoral_data': {
                'constituency': {
                    'id': 14205,  # Matches our constituency external_id
                    'label': '299 - Homburg'
                },
                'mandate_won': 'constituency'
            }
        }

        # Create service and import representative
        service = RepresentativeSyncService(dry_run=False)
        service._import_representative(mandate, self.bundestag, self.term)

        # Verify representative linked to constituency
        rep = Representative.objects.get(external_id='12345')
        self.assertIn(constituency, rep.constituencies.all())

    def test_constituency_not_found_logs_error(self):
        """Test that missing constituency logs error instead of creating."""
        # Mock mandate with non-existent constituency
        mandate = {
            'id': 12345,
            'type': 'mandate',
            'politician': {'id': 999, 'label': 'Test Person'},
            'electoral_data': {
                'constituency': {
                    'id': 99999,  # Does not exist
                },
                'mandate_won': 'constituency'
            }
        }

        service = RepresentativeSyncService(dry_run=False)

        # Should not raise, but should log error
        with self.assertLogs('letters.services', level='ERROR') as logs:
            service._import_representative(mandate, self.bundestag, self.term)

        # Verify error logged
        self.assertTrue(any('Constituency not found' in log for log in logs.output))

        # Verify representative still created (just without constituency)
        rep = Representative.objects.get(external_id='12345')
        self.assertEqual(rep.constituencies.count(), 0)
```

**Step 2: Run test**

```bash
uv run python manage.py test letters.tests.test_constituency_sync_integration -v
```

Expected: All 3 tests pass

**Step 3: Commit**

```bash
git add website/letters/tests/test_constituency_sync_integration.py
git commit -m "test: add integration tests for constituency sync flow

- Test API sync creates constituencies with external_id
- Test sync_representatives finds constituencies by external_id
- Test missing constituency logs error instead of creating

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 12: Update documentation and help text

**Files:**
- Modify: `website/letters/management/commands/sync_wahlkreise.py`
- Modify: `website/letters/management/commands/sync_representatives.py`

**Step 1: Update sync_wahlkreise help text**

In `sync_wahlkreise.py`, update the `help` attribute:

```python
help = (
    "Sync German electoral constituencies from Abgeordnetenwatch API. "
    "Use --api-sync to fetch all constituencies (districts + lists) from API. "
    "Downloads GeoJSON boundary files to enrich districts with list_id for address lookups. "
    "Use --list to see available state GeoJSON sources."
)
```

Update `add_arguments()` docstrings:

```python
parser.add_argument(
    "--api-sync",
    action="store_true",
    help="Sync all constituencies from Abgeordnetenwatch API (run this first)",
)

parser.add_argument(
    "--force",
    action="store_true",
    help="Download GeoJSON files even if they exist (for enrichment)",
)
```

**Step 2: Update sync_representatives help text**

In `sync_representatives.py`, update the help text:

```python
help = (
    "Sync representatives from Abgeordnetenwatch API. "
    "Links representatives to constituencies created by sync_wahlkreise. "
    "Run 'python manage.py sync_wahlkreise --api-sync' first."
)
```

**Step 3: Add usage examples to command output**

In `sync_wahlkreise.py`, add to `_handle_api_sync()` at the end:

```python
self.stdout.write("\n" + "="*70)
self.stdout.write(self.style.SUCCESS("API sync complete!"))
self.stdout.write("\nNext steps:")
self.stdout.write("  1. Download GeoJSON for better address matching:")
self.stdout.write("     python manage.py sync_wahlkreise --force")
self.stdout.write("  2. Sync representatives:")
self.stdout.write("     python manage.py sync_representatives --level all")
```

**Step 4: Test help output**

```bash
uv run python manage.py sync_wahlkreise --help
uv run python manage.py sync_representatives --help
```

Expected: Clear, updated help text

**Step 5: Commit**

```bash
git add website/letters/management/commands/
git commit -m "docs: update command help text and usage guidance

- Update sync_wahlkreise help to explain API sync workflow
- Update sync_representatives to mention dependency on sync_wahlkreise
- Add usage examples in command output

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## Task 13: Run full sync and verify data

**Files:**
- None (verification task)

**Step 1: Clear existing data (optional)**

```bash
uv run python manage.py shell
```

```python
from letters.models import Constituency, Representative
# Optional: Clear to test from scratch
# Constituency.objects.all().delete()
# Representative.objects.all().delete()
```

**Step 2: Run full sync workflow**

```bash
# Step 1: Sync constituencies from API
uv run python manage.py sync_wahlkreise --api-sync

# Step 2: Download and enrich with GeoJSON
uv run python manage.py sync_wahlkreise --force

# Step 3: Sync representatives
uv run python manage.py sync_representatives --level federal
```

**Step 3: Verify constituency counts**

```bash
uv run python manage.py shell
```

```python
from letters.models import Constituency

# Check federal districts
federal_districts = Constituency.objects.filter(scope='FEDERAL_DISTRICT').count()
print(f"Federal districts: {federal_districts}")  # Should be 299

# Check federal state lists
federal_lists = Constituency.objects.filter(scope='FEDERAL_STATE_LIST').count()
print(f"Federal state lists: {federal_lists}")  # Should be 16

# Check EU
eu = Constituency.objects.filter(scope='EU_AT_LARGE').count()
print(f"EU constituencies: {eu}")  # Should be 1

# Check list_id populated
no_list_id = Constituency.objects.filter(list_id__isnull=True).count()
print(f"Constituencies without list_id: {no_list_id}")  # Should be 0 or very low

# Check external_id populated
no_external_id = Constituency.objects.filter(external_id__isnull=True).count()
print(f"Constituencies without external_id: {no_external_id}")  # Should be 0
```

**Step 4: Verify representatives linked correctly**

```python
from letters.models import Representative

# Check representatives have constituencies
reps_with_const = Representative.objects.filter(constituencies__isnull=False).distinct().count()
total_reps = Representative.objects.count()
print(f"Representatives with constituencies: {reps_with_const}/{total_reps}")

# Check a specific representative
rep = Representative.objects.filter(constituencies__isnull=False).first()
if rep:
    print(f"\nExample: {rep.full_name}")
    for const in rep.constituencies.all():
        print(f"  - {const.name} (external_id={const.external_id}, list_id={const.list_id})")
```

**Step 5: Test address lookup**

```bash
uv run python manage.py query_wahlkreis "Unter den Linden 1, 10117 Berlin"
```

Expected: Shows constituency with list_id

**Step 6: Document results**

Create a verification report showing:
- Total constituencies created
- Constituencies with/without list_id
- Representatives linked successfully
- Any errors or warnings

**Step 7: No commit needed (verification task)**

---

## Summary

This plan refactors the constituency sync system to:

1. **Use Abgeordnetenwatch API as single source of truth** - All constituencies (districts + lists) come from API
2. **Rename `wahlkreis_id` to `list_id`** - Clearer name for its purpose (address→constituency lookup)
3. **Enrich districts with GeoJSON** - Boundary files provide precise list_id for WahlkreisResolver
4. **Simplify sync_representatives** - Only finds constituencies by external_id, never creates
5. **Eliminate duplication** - Remove duplicate _normalize_properties, consolidate logic

**Key benefits:**
- Complete coverage (all 16 states, not just 9 with GeoJSON)
- Clear separation of concerns (sync_wahlkreise owns constituencies, sync_representatives owns representatives)
- Single source of truth (API external_id)
- Simpler codebase (removed ~300 lines of creation logic from sync_representatives)

**Testing approach:**
- Unit tests for API methods
- Integration tests for full flow
- Manual verification of data

**Execution time estimate:** 4-6 hours for implementation, 1-2 hours for testing and verification
