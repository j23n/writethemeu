# Rebase Plan: feature/state-wahlkreise-import onto main

## Summary
Our branch adds state-level Wahlkreis data fetching to `fetch_wahlkreis_data.py`, but in main this file was renamed to `sync_wahlkreise.py` and significantly enhanced with database syncing functionality.

## Changes in main (since divergence)

### Key architectural changes:
1. **File renamed**: `fetch_wahlkreis_data.py` → `sync_wahlkreise.py`
2. **IdentityVerification refactor**:
   - Added `wahlkreis_id`, `wahlkreis_name`, `state` fields
   - Converted `constituency` ForeignKey → `constituencies` M2M
3. **Constituency model**: Added `wahlkreis_id` field
4. **WahlkreisResolver service**: New service for resolving Wahlkreis data
5. **ConstituencyLocator**: Now uses WahlkreisResolver
6. **sync_wahlkreise.py enhancements**:
   - Added database syncing: `_sync_constituencies_to_db()`
   - Added wahlkreis_id updating: `_update_wahlkreis_ids()`
   - Added EU constituency creation: `_ensure_eu_constituency()`
   - Uses existing file if present (doesn't force re-download)

### Commits in main we need to integrate with:
- d1fc1c8: feat: create sync_wahlkreise command (file rename)
- e17be36: feat: add wahlkreis_id field to Constituency
- 977b44a: feat: add Wahlkreis fields to IdentityVerification
- a4afc53: refactor: IdentityVerification to use constituencies M2M
- f6a095e: feat: add WahlkreisResolver service
- bee88b5: feat: populate wahlkreis_id when syncing
- 979619e: feat: ensure EU constituency exists
- c7948e5: refactor: identity verification to use Wahlkreis fields
- 4ae5082: refactor: convert constituency ForeignKeys to M2M

## Changes in our branch

### What we're adding:
1. **STATE_SOURCES configuration**: 9 German states with data source URLs
2. **CLI flags**:
   - `--state <CODE>`: Fetch specific state data
   - `--all-states`: Fetch all states
   - `--list`: List available states
3. **New methods**:
   - `_list_states()`: Display state configurations
   - `_fetch_state()`: Fetch single state data
   - `_fetch_all_states()`: Fetch all states with error handling
   - `_convert_geopackage_to_geojson()`: Convert GPKG files
   - `_normalize_state_geojson()`: Add standard properties to state data
4. **Enhanced handle() method**: Route to state fetching based on flags
5. **WahlkreisLocator changes**: Load state constituency files
6. **Data sources page**: Attribution and links
7. **Tests**: State data fetching tests
8. **Documentation**: Research and architecture docs

### Our branch commits:
- 068b730: feat: implement state data fetching with format conversion
- ca487b9: test: add tests for state data fetching command
- 32f29ea: feat: load state constituency files in WahlkreisLocator
- d9ec87a: feat: add _locate_detailed method
- c637ead: feat: add data sources attribution page
- d792fbe: docs: add state data architecture
- 3d282b4: test: add end-to-end integration test
- b53f21b: docs: improve command help text
- 590a8d1: docs: add implementation status
- 4b725a3: feat: add data sources link to footer
- 0685360: feat: add state source config and CLI flags
- 2775ac5: docs: update todo and plan

## Merge Strategy

### Files with conflicts:
1. **sync_wahlkreise.py** (was fetch_wahlkreis_data.py on our branch)
   - Need to merge our state fetching functionality into main's enhanced version

### Integration approach:
1. Add STATE_SOURCES configuration after DEFAULT_WAHLKREIS_URL
2. Update Command docstring to mention state data
3. Update help text
4. Add CLI arguments: --state, --all-states, --list
5. Add methods: _list_states(), _fetch_state(), _fetch_all_states(), _convert_geopackage_to_geojson(), _normalize_state_geojson()
6. Update handle() to route based on flags (list/all-states/state/federal)
7. Preserve main's database syncing logic for federal data
8. Our state fetching doesn't sync to DB (just downloads GeoJSON files)

### Files that should merge cleanly:
- WahlkreisLocator changes (loading state files)
- Data sources page and footer link
- Tests
- Documentation

### Testing plan:
1. Run existing tests to ensure federal functionality still works
2. Run our state data tests
3. Run end-to-end integration test
4. Manual verification: `python manage.py sync_wahlkreise --list`
5. Manual verification: `python manage.py sync_wahlkreise` (federal)

## Execution Steps

1. Start rebase: `git rebase gh/main`
2. When conflict occurs on fetch_wahlkreis_data.py:
   - Remove the deleted file: `git rm fetch_wahlkreis_data.py`
   - Edit sync_wahlkreise.py to add our state functionality
   - Stage changes: `git add sync_wahlkreise.py`
   - Continue: `git rebase --continue`
3. Resolve any subsequent conflicts
4. Run full test suite
5. Fix any failures
6. Manual testing of both federal and state functionality
