# Simplify Constituency Sync Commands Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Simplify sync_wahlkreise and sync_representatives by removing duplicate code, consolidating region helpers, and establishing clear data flow: API → DB → GeoJSON validation.

**Architecture:** Single sync_wahlkreise command that (1) syncs from API with list_id, (2) loads GeoJSON wahlkreise files, (3) validates exhaustive list_id matching. Representative sync simplified to use direct ORM queries instead of helper methods. All region/state helpers consolidated to constants.py.

**Tech Stack:** Django management commands, Abgeordnetenwatch API, GeoJSON/Shapely for geocoding

---

## Task 1: Consolidate Region Helpers to constants.py

**Files:**
- Modify: `website/letters/management/commands/sync_wahlkreise.py`
- Modify: `website/letters/services/representative_sync.py`
- Reference: `website/letters/constants.py`

**Step 1: Write test for region helper consolidation**

Create: `website/letters/tests/test_region_helpers.py`

```python
from letters.constants import normalize_german_state, get_state_code

def test_normalize_german_state():
    """Test that normalize_german_state handles all variants."""
    assert normalize_german_state('Bavaria') == 'Bayern'
    assert normalize_german_state('Baden-Württemberg') == 'Baden-Württemberg'
    assert normalize_german_state('berlin') == 'Berlin'
    assert normalize_german_state(None) is None
    assert normalize_german_state('') is None

def test_get_state_code():
    """Test that get_state_code returns correct codes."""
    assert get_state_code('Bayern') == 'BY'
    assert get_state_code('Bavaria') == 'BY'
    assert get_state_code('Baden-Württemberg') == 'BW'
    assert get_state_code('Berlin') == 'BE'
    assert get_state_code(None) is None
    assert get_state_code('Invalid') is None
```

**Step 2: Run test to verify it passes**

Run: `uv run python website/manage.py test letters.tests.test_region_helpers -v`
Expected: PASS (constants.py already implements these correctly)

**Step 3: Remove _region_to_state_code from sync_wahlkreise.py**

Delete lines 1327-1363 in `website/letters/management/commands/sync_wahlkreise.py`

Replace the single call at line 1249:
```python
# OLD:
state_code = self._region_to_state_code(parliament.region)

# NEW:
from letters.constants import get_state_code
state_code = get_state_code(parliament.region)
```

**Step 4: Remove _get_state_region_name from sync_wahlkreise.py**

Delete lines 190-193 in `website/letters/management/commands/sync_wahlkreise.py`

Replace calls at line 541:
```python
# OLD:
region_name = self._get_state_region_name(state_code)

# NEW:
from letters.constants import normalize_german_state
state_name = STATE_SOURCES[state_code]['name']
region_name = normalize_german_state(state_name) or state_name
```

**Step 5: Remove _extract_state_from_electoral from representative_sync.py**

Delete lines 464-475 in `website/letters/services/representative_sync.py`

Note: This method is not currently used, so just remove it.

**Step 6: Remove _extract_region_from_parliament_name from sync_wahlkreise.py**

Delete lines 1295-1325 in `website/letters/management/commands/sync_wahlkreise.py`

Note: This method is not currently used, so just remove it.

**Step 7: Run tests**

Run: `uv run python website/manage.py test letters -v`
Expected: All tests pass

**Step 8: Commit**

```bash
git add website/letters/management/commands/sync_wahlkreise.py \
        website/letters/services/representative_sync.py \
        website/letters/tests/test_region_helpers.py
git commit -m "refactor: consolidate region helpers to constants.py

- Remove duplicate _region_to_state_code, _get_state_region_name, _extract_state_from_electoral
- Use constants.normalize_german_state() and get_state_code() directly
- Add test coverage for region helper functions"
```

---

## Task 2: Simplify Representative Constituency Assignment

**Files:**
- Modify: `website/letters/services/representative_sync.py:359-419`
- Test: Verify with existing integration tests

**Step 1: Write test for simplified constituency assignment**

Add to existing test file (or create): `website/letters/tests/test_representative_sync.py`

```python
import pytest
from unittest.mock import Mock, patch
from letters.services.representative_sync import RepresentativeSyncService
from letters.models import Constituency, Parliament, ParliamentTerm

@pytest.mark.django_db
def test_determine_constituencies_direct_mandate():
    """Test that direct mandate finds constituency by external_id."""
    parliament = Parliament.objects.create(name='Test', level='FEDERAL', region='DE')
    term = ParliamentTerm.objects.create(parliament=parliament, name='Test Term')
    constituency = Constituency.objects.create(
        external_id='12345',
        parliament_term=term,
        name='Test District',
        scope='FEDERAL_DISTRICT'
    )

    service = RepresentativeSyncService(dry_run=True)
    representative = Mock(full_name='Test Rep', external_id='999')

    electoral = {
        'constituency': {'id': 12345},
        'mandate_won': 'constituency'
    }

    results = list(service._determine_constituencies(parliament, term, electoral, representative))

    assert len(results) == 1
    assert results[0].external_id == '12345'

@pytest.mark.django_db
def test_determine_constituencies_list_seat():
    """Test that list seat finds constituency by electoral_list id."""
    parliament = Parliament.objects.create(name='Test', level='FEDERAL', region='DE')
    term = ParliamentTerm.objects.create(parliament=parliament, name='Test Term')
    list_constituency = Constituency.objects.create(
        external_id='67890',
        parliament_term=term,
        name='Test List',
        scope='FEDERAL_STATE_LIST'
    )

    service = RepresentativeSyncService(dry_run=True)
    representative = Mock(full_name='Test Rep', external_id='999')

    electoral = {
        'electoral_list': {'id': 67890},
        'mandate_won': 'list'
    }

    results = list(service._determine_constituencies(parliament, term, electoral, representative))

    assert len(results) == 1
    assert results[0].external_id == '67890'

@pytest.mark.django_db
def test_determine_constituencies_not_found():
    """Test that missing constituency logs warning but doesn't crash."""
    parliament = Parliament.objects.create(name='Test', level='FEDERAL', region='DE')
    term = ParliamentTerm.objects.create(parliament=parliament, name='Test Term')

    service = RepresentativeSyncService(dry_run=True)
    representative = Mock(full_name='Test Rep', external_id='999')

    electoral = {
        'constituency': {'id': 99999},  # Doesn't exist
        'mandate_won': 'constituency'
    }

    with patch('letters.services.representative_sync.logger') as mock_logger:
        results = list(service._determine_constituencies(parliament, term, electoral, representative))

        assert len(results) == 0
        mock_logger.warning.assert_called_once()
        assert '99999' in mock_logger.warning.call_args[0][0]
```

**Step 2: Run test to verify it fails**

Run: `uv run python website/manage.py test letters.tests.test_representative_sync -v`
Expected: FAIL (test expects new behavior)

**Step 3: Simplify _determine_constituencies method**

Replace lines 359-419 in `website/letters/services/representative_sync.py`:

```python
def _determine_constituencies(
    self,
    parliament: Parliament,
    term: ParliamentTerm,
    electoral: Dict,
    representative: Representative,
) -> Iterable[Constituency]:
    """Link representative to constituencies by external_id from API."""

    # Try direct constituency (Direktmandat)
    const_data = electoral.get('constituency')
    if const_data:
        const_id = const_data.get('id')
        if const_id:
            try:
                yield Constituency.objects.get(external_id=str(const_id))
            except Constituency.DoesNotExist:
                logger.warning(
                    "Constituency external_id=%s not found for %s. Run sync_wahlkreise first.",
                    const_id,
                    representative.full_name
                )

    # Try electoral list (Listenmandat)
    list_data = electoral.get('electoral_list')
    if list_data:
        list_id = list_data.get('id')
        if list_id:
            try:
                yield Constituency.objects.get(external_id=str(list_id))
            except Constituency.DoesNotExist:
                logger.warning(
                    "Electoral list external_id=%s not found for %s. Run sync_wahlkreise first.",
                    list_id,
                    representative.full_name
                )
```

**Step 4: Run test to verify it passes**

Run: `uv run python website/manage.py test letters.tests.test_representative_sync -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `uv run python website/manage.py test letters -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add website/letters/services/representative_sync.py \
        website/letters/tests/test_representative_sync.py
git commit -m "refactor: simplify constituency assignment in representative sync

- Remove _find_constituency_by_external_id and _handle_direct_mandate methods
- Use direct ORM queries with try/except for both direct and list mandates
- Add comprehensive test coverage for constituency assignment
- Fix list seat handling (was logging warning and skipping)"
```

---

## Task 3: Remove Duplicate GeoJSON Sync Methods from sync_wahlkreise

**Files:**
- Modify: `website/letters/management/commands/sync_wahlkreise.py:222-291,370-460,462-491,538-653`
- Test: Run command and verify behavior

**Step 1: Write test for streamlined sync behavior**

Create: `website/letters/tests/test_sync_wahlkreise_command.py`

```python
import pytest
from io import StringIO
from django.core.management import call_command
from unittest.mock import patch, MagicMock
from letters.models import Parliament, ParliamentTerm, Constituency

@pytest.mark.django_db
class TestSyncWahlkreiseCommand:

    @patch('letters.management.commands.sync_wahlkreise.AbgeordnetenwatchAPI')
    def test_command_syncs_from_api_only(self, mock_api):
        """Test that command syncs from API without GeoJSON-based DB updates."""
        # Mock API responses
        mock_api.get_parliaments.return_value = [
            {'id': 111, 'label': 'Bundestag'}
        ]
        mock_api.get_parliament_periods.return_value = [
            {'id': 222, 'label': '2025-2029'}
        ]
        mock_api.get_constituencies.return_value = [
            {'id': 1, 'number': 1, 'name': 'Flensburg', 'label': '1 - Flensburg'}
        ]
        mock_api.get_electoral_lists.return_value = []

        out = StringIO()
        call_command('sync_wahlkreise', stdout=out)

        output = out.getvalue()
        assert 'Syncing constituencies from API' in output
        assert 'Created' in output or 'Updated' in output

        # Verify constituency was created from API
        assert Constituency.objects.filter(external_id='1').exists()
        constituency = Constituency.objects.get(external_id='1')
        assert constituency.list_id == '001'  # Should be set from API

    def test_command_has_no_deprecated_flags(self):
        """Test that deprecated flags are removed."""
        from django.core.management import get_commands, load_command_class

        command = load_command_class('letters', 'sync_wahlkreise')
        parser = command.create_parser('manage.py', 'sync_wahlkreise')

        # Get list of all option strings
        option_strings = []
        for action in parser._actions:
            option_strings.extend(action.option_strings)

        # Verify deprecated flags are removed
        assert '--state' not in option_strings
        assert '--all-states' not in option_strings
        assert '--enrich-from-geojson' not in option_strings
        assert '--api-sync' not in option_strings
```

**Step 2: Run test to verify it fails**

Run: `uv run python website/manage.py test letters.tests.test_sync_wahlkreise_command -v`
Expected: FAIL (command still has old behavior)

**Step 3: Remove deprecated sync methods**

Delete the following methods from `website/letters/management/commands/sync_wahlkreise.py`:
- `_sync_constituencies_to_db()` (lines 370-460)
- `_update_wahlkreis_ids()` (lines 462-491)
- `_sync_state_constituencies_to_db()` (lines 538-653)
- `_handle_enrich_from_geojson()` (lines 1145-1153)
- `_enrich_constituencies_from_geojson()` (lines 1156-1293)

**Step 4: Remove deprecated command flags**

In `add_arguments()` method, delete these arguments:
```python
# DELETE these entire parser.add_argument() blocks:
'--url'
'--output'
'--zip-member'
'--force'
'--state'
'--all-states'
'--list'
'--enrich-from-geojson'
```

Keep only `--api-sync` for now (will be default behavior in next step).

**Step 5: Simplify handle() method to single flow**

Replace the entire `handle()` method (lines 195-220) with:

```python
def handle(self, *args, **options):
    """Sync constituencies from API and validate against GeoJSON wahlkreise."""

    # Step 1: Sync from API
    self.stdout.write(self.style.SUCCESS("Step 1: Syncing constituencies from Abgeordnetenwatch API..."))
    self._handle_api_sync()

    # Step 2: Ensure EU constituency exists
    self.stdout.write(self.style.SUCCESS("\nStep 2: Ensuring EU constituency exists..."))
    self._ensure_eu_constituency()

    # Step 3: Load GeoJSON files (for future validation)
    self.stdout.write(self.style.SUCCESS("\nStep 3: GeoJSON validation..."))
    self.stdout.write("  (GeoJSON validation not yet implemented - wahlkreise files used for geocoding only)")

    self.stdout.write(self.style.SUCCESS("\n✓ Sync complete!"))
```

**Step 6: Update _handle_api_sync to not check flags**

In `_handle_api_sync()` method (line 1027), remove the option check since this is now the default behavior.

**Step 7: Remove state download methods**

Delete these methods (we can add them back as a separate command later if needed):
- `_list_states()` (lines 655-662)
- `_fetch_state()` (lines 664-752)
- `_fetch_all_states()` (lines 754-782)
- `_convert_geopackage_to_geojson()` (lines 784-823)
- `_normalize_state_geojson()` (lines 825-851)

Also delete:
- `_zip_contains_shapefile()` (lines 293-299)
- `_convert_shapefile_to_geojson()` (lines 301-345)
- `_extract_from_zip()` (lines 347-367)

**Step 8: Clean up imports**

Remove unused imports at the top of the file:
```python
# DELETE if no longer used:
import io
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

try:
    import shapefile
except ImportError:
    shapefile = None
```

**Step 9: Remove STATE_SOURCES constant**

Delete lines 32-126 (the entire STATE_SOURCES dictionary).

**Step 10: Run test to verify it passes**

Run: `uv run python website/manage.py test letters.tests.test_sync_wahlkreise_command -v`
Expected: PASS

**Step 11: Run full test suite**

Run: `uv run python website/manage.py test letters -v`
Expected: All tests pass

**Step 12: Test command manually**

Run: `uv run python website/manage.py sync_wahlkreise`
Expected: Command syncs from API successfully

**Step 13: Commit**

```bash
git add website/letters/management/commands/sync_wahlkreise.py \
        website/letters/tests/test_sync_wahlkreise_command.py
git commit -m "refactor: simplify sync_wahlkreise to API-only sync

- Remove duplicate _sync_constituencies_to_db and _sync_state_constituencies_to_db
- Remove _enrich_constituencies_from_geojson (list_id set from API now)
- Remove state download functionality (can be separate command if needed)
- Remove deprecated flags: --state, --all-states, --enrich-from-geojson, --api-sync
- Simplify handle() to single flow: API sync → EU constituency → validation placeholder
- Remove 500+ lines of duplicate/deprecated code"
```

---

## Task 4: Ensure list_id is Set During API Sync

**Files:**
- Modify: `website/letters/management/commands/sync_wahlkreise.py:853-1025`
- Test: Verify constituencies have list_id after sync

**Step 1: Write test for list_id generation**

Add to `website/letters/tests/test_sync_wahlkreise_command.py`:

```python
@pytest.mark.django_db
def test_api_sync_sets_list_id_federal():
    """Test that federal constituency list_id is set from API."""
    from letters.management.commands.sync_wahlkreise import Command
    from unittest.mock import Mock

    command = Command()

    parliament_data = {'id': 111, 'label': 'Bundestag'}
    period_data = {'id': 222, 'label': '2025-2029'}

    # Mock constituency data from API
    with patch('letters.services.abgeordnetenwatch_api_client.AbgeordnetenwatchAPI') as mock_api:
        mock_api.get_constituencies.return_value = [
            {'id': 1, 'number': 1, 'name': 'Flensburg', 'label': '1 - Flensburg'},
            {'id': 42, 'number': 42, 'name': 'München', 'label': '42 - München'},
            {'id': 299, 'number': 299, 'name': 'Rosenheim', 'label': '299 - Rosenheim'},
        ]
        mock_api.get_electoral_lists.return_value = []

        stats = command._sync_constituencies_from_api(parliament_data, period_data, 'FEDERAL')

    # Verify list_id format for federal: 3-digit zero-padded
    c1 = Constituency.objects.get(external_id='1')
    assert c1.list_id == '001'

    c42 = Constituency.objects.get(external_id='42')
    assert c42.list_id == '042'

    c299 = Constituency.objects.get(external_id='299')
    assert c299.list_id == '299'

@pytest.mark.django_db
def test_api_sync_sets_list_id_state():
    """Test that state constituency list_id is set from API with state code."""
    from letters.management.commands.sync_wahlkreise import Command
    from letters.models import Parliament, ParliamentTerm

    # Create Bayern parliament first
    parliament = Parliament.objects.create(
        name='Landtag Bayern',
        level='STATE',
        region='Bayern',
        legislative_body='Landtag Bayern'
    )
    term = ParliamentTerm.objects.create(
        parliament=parliament,
        name='Bayern 2023-2028',
        metadata={'period_id': 333}
    )

    command = Command()
    parliament_data = {'id': 112, 'label': 'Landtag Bayern'}
    period_data = {'id': 333, 'label': 'Bayern 2023-2028'}

    with patch('letters.services.abgeordnetenwatch_api_client.AbgeordnetenwatchAPI') as mock_api:
        mock_api.get_constituencies.return_value = [
            {'id': 5001, 'number': 101, 'name': 'München-Land', 'label': '101 - München-Land'},
        ]
        mock_api.get_electoral_lists.return_value = []

        stats = command._sync_constituencies_from_api(parliament_data, period_data, 'STATE')

    # Verify list_id format for state: STATE_CODE-NNNN
    constituency = Constituency.objects.get(external_id='5001')
    assert constituency.list_id == 'BY-0101'
```

**Step 2: Run test to verify it fails**

Run: `uv run python website/manage.py test letters.tests.test_sync_wahlkreise_command::test_api_sync_sets_list_id_federal -v`
Expected: FAIL (list_id not set or wrong format)

**Step 3: Update _sync_constituencies_from_api to set list_id**

In `website/letters/management/commands/sync_wahlkreise.py`, find the `_sync_constituencies_from_api()` method (around line 853).

In the section that processes district constituencies (around line 929), update the list_id generation:

```python
# Around line 936-947, replace:
if level == 'FEDERAL':
    scope = 'FEDERAL_DISTRICT'
    # Generate list_id: 3-digit zero-padded for federal (e.g., "001")
    list_id = str(number).zfill(3) if number else None
elif level == 'STATE':
    scope = 'STATE_DISTRICT'
    # Generate list_id: state code + 4-digit number (e.g., "BY-0001")
    # We'll need to get state code from parliament metadata or name
    # For now, leave list_id as None - it will be enriched from GeoJSON
    list_id = None
else:
    continue  # EU doesn't have districts

# WITH:
if level == 'FEDERAL':
    scope = 'FEDERAL_DISTRICT'
    list_id = str(number).zfill(3) if number else None
elif level == 'STATE':
    scope = 'STATE_DISTRICT'
    # Get state code from parliament region
    from letters.constants import get_state_code
    parliament = Parliament.objects.filter(metadata__api_id=parliament_data['id']).first()
    if parliament and number:
        state_code = get_state_code(parliament.region)
        if state_code:
            list_id = f"{state_code}-{str(number).zfill(4)}"
        else:
            list_id = None
            logger.warning("Could not determine state code for parliament %s", parliament.name)
    else:
        list_id = None
else:
    continue  # EU doesn't have districts
```

**Step 4: Update electoral lists list_id generation**

In the section that processes electoral lists (around line 972), update similarly:

```python
# Around line 978-1001, improve the list_id logic for electoral lists:
if level == 'FEDERAL':
    if 'bundesliste' in name_lower:
        scope = 'FEDERAL_LIST'
        list_id = 'BUND-DE-LIST'
    else:
        scope = 'FEDERAL_STATE_LIST'
        # Try to extract state from name
        from letters.constants import normalize_german_state, get_state_code
        for state_name in ['Baden-Württemberg', 'Bayern', 'Berlin', 'Brandenburg',
                          'Bremen', 'Hamburg', 'Hessen', 'Mecklenburg-Vorpommern',
                          'Niedersachsen', 'Nordrhein-Westfalen', 'Rheinland-Pfalz',
                          'Saarland', 'Sachsen', 'Sachsen-Anhalt', 'Schleswig-Holstein', 'Thüringen']:
            if state_name.lower() in name_lower:
                state_code = get_state_code(state_name)
                if state_code:
                    list_id = f"{state_code}-LIST"
                    break
        else:
            list_id = None
            logger.warning("Could not determine state code for federal list: %s", name)
elif level == 'STATE':
    if 'regional' in name_lower or 'wahlkreis' in name_lower:
        scope = 'STATE_REGIONAL_LIST'
    else:
        scope = 'STATE_LIST'
    # Get state code from parliament
    parliament = Parliament.objects.filter(metadata__api_id=parliament_data['id']).first()
    if parliament:
        state_code = get_state_code(parliament.region)
        if state_code:
            list_id = f"{state_code}-STATE-LIST"
        else:
            list_id = None
    else:
        list_id = None
elif level == 'EU':
    scope = 'EU_AT_LARGE'
    list_id = 'DE'
else:
    scope = 'OTHER'
    list_id = None
```

**Step 5: Run test to verify it passes**

Run: `uv run python website/manage.py test letters.tests.test_sync_wahlkreise_command::test_api_sync_sets_list_id_federal -v`
Expected: PASS

Run: `uv run python website/manage.py test letters.tests.test_sync_wahlkreise_command::test_api_sync_sets_list_id_state -v`
Expected: PASS

**Step 6: Run full test suite**

Run: `uv run python website/manage.py test letters -v`
Expected: All tests pass

**Step 7: Commit**

```bash
git add website/letters/management/commands/sync_wahlkreise.py \
        website/letters/tests/test_sync_wahlkreise_command.py
git commit -m "feat: set list_id during API sync for all constituency types

- Federal districts: 3-digit zero-padded (001, 042, 299)
- State districts: STATE-NNNN format (BY-0101, BW-0042)
- Federal state lists: STATE-LIST format (BY-LIST)
- State lists: STATE-STATE-LIST format (BY-STATE-LIST)
- Use constants.get_state_code() to derive state codes from parliament region"
```

---

## Task 5: Add GeoJSON Validation (Future Work Placeholder)

**Files:**
- Modify: `website/letters/management/commands/sync_wahlkreise.py`
- Note: This task creates the structure for future validation work

**Step 1: Add validation method stub**

Add new method to `Command` class in `website/letters/management/commands/sync_wahlkreise.py`:

```python
def _validate_geojson_matches(self) -> dict:
    """
    Validate that all GeoJSON wahlkreise have matching constituencies in DB.

    This ensures address geocoding will always find a valid constituency.

    Returns:
        dict with validation stats:
        - 'geojson_count': int - number of wahlkreise in GeoJSON files
        - 'db_count': int - number of constituencies in DB with list_id
        - 'matched': int - wahlkreise with matching constituency
        - 'missing_in_db': list - list_ids in GeoJSON but not in DB
        - 'missing_in_geojson': list - list_ids in DB but not in GeoJSON
    """
    from pathlib import Path
    import json
    from django.conf import settings
    from letters.services.geocoding import WahlkreisLocator

    # Load federal GeoJSON
    geojson_path = Path(settings.CONSTITUENCY_BOUNDARIES_PATH)
    if not geojson_path.exists():
        self.stdout.write(self.style.WARNING(f"  GeoJSON file not found at {geojson_path}"))
        return {
            'geojson_count': 0,
            'db_count': 0,
            'matched': 0,
            'missing_in_db': [],
            'missing_in_geojson': []
        }

    # Extract list_ids from GeoJSON
    geojson_list_ids = set()
    with open(geojson_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        for feature in data.get('features', []):
            props = feature.get('properties', {})
            wkr_nr = props.get('WKR_NR')
            if wkr_nr:
                list_id = str(wkr_nr).zfill(3)
                geojson_list_ids.add(list_id)

    # Get list_ids from DB
    from letters.models import Constituency
    db_list_ids = set(
        Constituency.objects
        .filter(scope='FEDERAL_DISTRICT', list_id__isnull=False)
        .values_list('list_id', flat=True)
    )

    # Find mismatches
    missing_in_db = sorted(geojson_list_ids - db_list_ids)
    missing_in_geojson = sorted(db_list_ids - geojson_list_ids)
    matched = len(geojson_list_ids & db_list_ids)

    stats = {
        'geojson_count': len(geojson_list_ids),
        'db_count': len(db_list_ids),
        'matched': matched,
        'missing_in_db': missing_in_db,
        'missing_in_geojson': missing_in_geojson
    }

    # Report results
    self.stdout.write(f"  GeoJSON wahlkreise: {stats['geojson_count']}")
    self.stdout.write(f"  DB constituencies: {stats['db_count']}")
    self.stdout.write(f"  Matched: {stats['matched']}")

    if missing_in_db:
        self.stdout.write(self.style.WARNING(
            f"  ⚠ {len(missing_in_db)} wahlkreise in GeoJSON but not in DB: {', '.join(missing_in_db[:10])}"
        ))

    if missing_in_geojson:
        self.stdout.write(self.style.WARNING(
            f"  ⚠ {len(missing_in_geojson)} constituencies in DB but not in GeoJSON: {', '.join(missing_in_geojson[:10])}"
        ))

    if not missing_in_db and not missing_in_geojson:
        self.stdout.write(self.style.SUCCESS("  ✓ All wahlkreise have matching constituencies!"))

    return stats
```

**Step 2: Update handle() to call validation**

Update the handle() method to call the new validation:

```python
def handle(self, *args, **options):
    """Sync constituencies from API and validate against GeoJSON wahlkreise."""

    # Step 1: Sync from API
    self.stdout.write(self.style.SUCCESS("Step 1: Syncing constituencies from Abgeordnetenwatch API..."))
    self._handle_api_sync()

    # Step 2: Ensure EU constituency exists
    self.stdout.write(self.style.SUCCESS("\nStep 2: Ensuring EU constituency exists..."))
    self._ensure_eu_constituency()

    # Step 3: Validate GeoJSON matches
    self.stdout.write(self.style.SUCCESS("\nStep 3: Validating GeoJSON matches..."))
    validation_stats = self._validate_geojson_matches()

    self.stdout.write(self.style.SUCCESS("\n✓ Sync complete!"))
```

**Step 3: Write test for validation**

Add to `website/letters/tests/test_sync_wahlkreise_command.py`:

```python
@pytest.mark.django_db
def test_validation_detects_mismatches():
    """Test that validation detects mismatches between GeoJSON and DB."""
    from letters.management.commands.sync_wahlkreise import Command
    from letters.models import Parliament, ParliamentTerm, Constituency

    # Create a constituency that won't match GeoJSON
    parliament = Parliament.objects.create(name='Bundestag', level='FEDERAL', region='DE')
    term = ParliamentTerm.objects.create(parliament=parliament, name='Test')

    # Constituency with list_id that doesn't exist in GeoJSON
    Constituency.objects.create(
        external_id='999',
        parliament_term=term,
        scope='FEDERAL_DISTRICT',
        list_id='999',
        name='Fake District'
    )

    command = Command()
    stats = command._validate_geojson_matches()

    # Should detect mismatch
    assert '999' in stats['missing_in_geojson']
```

**Step 4: Run test**

Run: `uv run python website/manage.py test letters.tests.test_sync_wahlkreise_command::test_validation_detects_mismatches -v`
Expected: PASS

**Step 5: Run full test suite**

Run: `uv run python website/manage.py test letters -v`
Expected: All tests pass

**Step 6: Commit**

```bash
git add website/letters/management/commands/sync_wahlkreise.py \
        website/letters/tests/test_sync_wahlkreise_command.py
git commit -m "feat: add GeoJSON validation to sync_wahlkreise

- Validate that all GeoJSON wahlkreise have matching constituencies in DB
- Report mismatches between GeoJSON files and database
- Ensures address geocoding will always find valid constituencies
- Add test coverage for validation logic"
```

---

## Task 6: Update Command Help Documentation

**Files:**
- Modify: `website/letters/management/commands/sync_wahlkreise.py:129-138`

**Step 1: Update help text**

Replace the `help` attribute in the `Command` class:

```python
help = (
    "Sync German electoral constituencies from Abgeordnetenwatch API. "
    "Creates Parliament, ParliamentTerm, and Constituency records for all levels "
    "(EU, Federal Bundestag, State Landtag). Validates that GeoJSON wahlkreise files "
    "have matching constituencies for address geocoding. "
    "Run this command before sync_representatives."
)
```

**Step 2: Update ABOUTME comments**

Update the file header comments (lines 1-2):

```python
# ABOUTME: Management command to sync constituencies from Abgeordnetenwatch API.
# ABOUTME: Creates Parliament/ParliamentTerm/Constituency records and validates against GeoJSON wahlkreise files.
```

**Step 3: Test help output**

Run: `uv run python website/manage.py sync_wahlkreise --help`
Expected: Shows updated help text

**Step 4: Commit**

```bash
git add website/letters/management/commands/sync_wahlkreise.py
git commit -m "docs: update sync_wahlkreise help text to reflect simplified behavior"
```

---

## Task 7: Update sync_representatives Documentation

**Files:**
- Modify: `website/letters/services/representative_sync.py:1-2,35`

**Step 1: Update ABOUTME comments**

Update file header (lines 1-2):

```python
# ABOUTME: Service for synchronizing representatives, parliaments, and committees from Abgeordnetenwatch.
# ABOUTME: Links representatives to constituencies via external_id from API. Run sync_wahlkreise first.
```

**Step 2: Update class docstring**

Update the `RepresentativeSyncService` class docstring (line 35):

```python
class RepresentativeSyncService:
    """
    Sync representatives from Abgeordnetenwatch API and link to constituencies.

    Prerequisites:
    - Run sync_wahlkreise first to create constituencies
    - Constituencies are linked by external_id from API
    - Both direct mandates and list seats are supported
    """
```

**Step 3: Commit**

```bash
git add website/letters/services/representative_sync.py
git commit -m "docs: update representative_sync to clarify constituency linking"
```

---

## Task 8: Integration Testing

**Files:**
- Create: `website/letters/tests/test_sync_integration.py`

**Step 1: Write end-to-end integration test**

```python
import pytest
from io import StringIO
from django.core.management import call_command
from unittest.mock import patch, MagicMock
from letters.models import Parliament, ParliamentTerm, Constituency, Representative

@pytest.mark.django_db
class TestSyncIntegration:
    """Integration tests for the full sync workflow."""

    @patch('letters.services.abgeordnetenwatch_api_client.AbgeordnetenwatchAPI')
    def test_full_sync_workflow(self, mock_api):
        """Test complete workflow: sync_wahlkreise → sync_representatives."""

        # Mock API responses for sync_wahlkreise
        mock_api.get_parliaments.return_value = [
            {'id': 111, 'label': 'Bundestag', 'current_project': {'id': 222}}
        ]
        mock_api.get_parliament_periods.return_value = [
            {
                'id': 222,
                'label': '2025-2029',
                'start_date_period': '2025-01-01',
                'end_date_period': '2029-12-31'
            }
        ]
        mock_api.get_constituencies.return_value = [
            {'id': 1, 'number': 1, 'name': 'Flensburg', 'label': '1 - Flensburg'},
            {'id': 2, 'number': 2, 'name': 'Nordfriesland', 'label': '2 - Nordfriesland'},
        ]
        mock_api.get_electoral_lists.return_value = [
            {'id': 5001, 'name': 'Landesliste Schleswig-Holstein', 'label': 'SPD Schleswig-Holstein'}
        ]

        # Step 1: Run sync_wahlkreise
        out = StringIO()
        call_command('sync_wahlkreise', stdout=out)

        output = out.getvalue()
        assert 'Syncing constituencies from API' in output
        assert '✓ Sync complete!' in output

        # Verify constituencies exist
        assert Constituency.objects.count() >= 2
        c1 = Constituency.objects.get(external_id='1')
        assert c1.list_id == '001'
        assert c1.scope == 'FEDERAL_DISTRICT'

        c2 = Constituency.objects.get(external_id='2')
        assert c2.list_id == '002'

        # Mock API responses for sync_representatives
        mock_api.get_candidacies_mandates.return_value = [
            {
                'id': 9001,
                'type': 'mandate',
                'politician': {'id': 8001, 'label': 'Anna Schmidt'},
                'electoral_data': {
                    'mandate_won': 'constituency',
                    'constituency': {'id': 1}
                },
                'fraction_membership': [
                    {'fraction': {'label': 'SPD'}}
                ],
                'start_date': '2025-01-01',
                'end_date': '2029-12-31'
            },
            {
                'id': 9002,
                'type': 'mandate',
                'politician': {'id': 8002, 'label': 'Max Müller'},
                'electoral_data': {
                    'mandate_won': 'list',
                    'electoral_list': {'id': 5001}
                },
                'fraction_membership': [
                    {'fraction': {'label': 'SPD'}}
                ],
                'start_date': '2025-01-01',
                'end_date': '2029-12-31'
            }
        ]
        mock_api.get_politician.return_value = {}
        mock_api.get_committees.return_value = []

        # Step 2: Run sync_representatives
        out = StringIO()
        call_command('sync_representatives', level='federal', stdout=out)

        output = out.getvalue()
        assert 'Sync completed successfully' in output

        # Verify representatives exist and are linked to constituencies
        assert Representative.objects.count() == 2

        # Direct mandate representative
        rep1 = Representative.objects.get(external_id='9001')
        assert rep1.last_name == 'Schmidt'
        assert rep1.constituencies.count() == 1
        assert rep1.constituencies.first().external_id == '1'

        # List seat representative
        rep2 = Representative.objects.get(external_id='9002')
        assert rep2.last_name == 'Müller'
        assert rep2.constituencies.count() == 1
        assert rep2.constituencies.first().external_id == '5001'

    @patch('letters.services.abgeordnetenwatch_api_client.AbgeordnetenwatchAPI')
    def test_sync_representatives_without_constituencies_logs_warning(self, mock_api):
        """Test that syncing representatives before constituencies logs warnings."""

        # Don't create any constituencies

        # Mock API for representatives
        mock_api.get_parliaments.return_value = [
            {'id': 111, 'label': 'Bundestag', 'current_project': {'id': 222}}
        ]
        mock_api.get_parliament_periods.return_value = [
            {'id': 222, 'label': '2025-2029'}
        ]
        mock_api.get_candidacies_mandates.return_value = [
            {
                'id': 9001,
                'type': 'mandate',
                'politician': {'id': 8001, 'label': 'Anna Schmidt'},
                'electoral_data': {
                    'mandate_won': 'constituency',
                    'constituency': {'id': 999}  # Doesn't exist
                },
                'fraction_membership': [{'fraction': {'label': 'SPD'}}],
                'start_date': '2025-01-01'
            }
        ]
        mock_api.get_politician.return_value = {}
        mock_api.get_committees.return_value = []

        # Run sync - should not crash, but log warning
        with patch('letters.services.representative_sync.logger') as mock_logger:
            out = StringIO()
            call_command('sync_representatives', level='federal', stdout=out)

            # Verify warning was logged
            mock_logger.warning.assert_called()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert '999' in warning_msg
            assert 'Run sync_wahlkreise first' in warning_msg

        # Representative should exist but have no constituencies
        rep = Representative.objects.get(external_id='9001')
        assert rep.constituencies.count() == 0
```

**Step 2: Run integration test**

Run: `uv run python website/manage.py test letters.tests.test_sync_integration -v`
Expected: PASS

**Step 3: Run full test suite**

Run: `uv run python website/manage.py test letters -v`
Expected: All tests pass

**Step 4: Commit**

```bash
git add website/letters/tests/test_sync_integration.py
git commit -m "test: add integration tests for full sync workflow

- Test complete sync_wahlkreise → sync_representatives flow
- Verify constituencies created with correct list_id
- Verify representatives linked to constituencies by external_id
- Test both direct mandates and list seats
- Test error handling when constituencies don't exist"
```

---

## Final Verification

**Step 1: Run complete test suite**

Run: `uv run python website/manage.py test letters -v`
Expected: All tests pass

**Step 2: Test commands manually**

```bash
# Test sync_wahlkreise
uv run python website/manage.py sync_wahlkreise

# Test sync_representatives
uv run python website/manage.py sync_representatives --level federal
```

Expected: Both commands run successfully

**Step 3: Verify code reduction**

Run: `git diff --stat feature/state-wahlkreise-import`
Expected: Shows significant line reduction in sync_wahlkreise.py and representative_sync.py

**Step 4: Update journal with learnings**

Document key insights:
- API is source of truth for constituencies, GeoJSON is for geocoding only
- list_id must be set during API sync for address lookup matching
- Direct ORM queries are simpler than helper methods
- Consolidating region helpers to constants.py reduces duplication

---

## Summary

This plan removes ~500 lines of duplicate/deprecated code while establishing a clear data flow:

1. **API → DB**: `sync_wahlkreise` creates constituencies from Abgeordnetenwatch API with list_id
2. **GeoJSON validation**: Validates that GeoJSON wahlkreise match DB constituencies for geocoding
3. **Representative linking**: `sync_representatives` links representatives to constituencies by external_id

**Key simplifications:**
- Single-command `sync_wahlkreise` (no subcommands)
- Direct ORM queries instead of helper methods
- Consolidated region/state helpers in `constants.py`
- Clear separation: API for data, GeoJSON for geocoding
