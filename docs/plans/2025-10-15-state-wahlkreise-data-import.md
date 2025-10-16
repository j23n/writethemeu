# State-Level Wahlkreise Data Import Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Extend the wahlkreis data import system to fetch and store electoral district boundaries for 9 German states (Landtagswahlen), add an attribution page listing data sources, and prepare WahlkreisLocator to handle both federal and state data.

**Architecture:** Multi-file approach with separate GeoJSON files per state (`wahlkreise_{state_code}.geojson`). Command extended with state configuration dict. WahlkreisLocator loads all available state files internally but maintains existing tuple-based API. Attribution page shows compliance information.

**Tech Stack:** Django management commands, Shapely for geospatial operations, pyshp for Shapefile conversion, fiona for GeoPackage support

---

## Task 1: Add State Configuration to fetch_wahlkreis_data Command

**Files:**
- Modify: `website/letters/management/commands/fetch_wahlkreis_data.py:1-177`

**Step 1: Add state source configuration**

Add this constant after the `DEFAULT_WAHLKREIS_URL` definition (line 16):

```python
# State-level Landtagswahlen data sources (9 states with direct downloads)
STATE_SOURCES = {
    'BW': {
        'name': 'Baden-Württemberg',
        'url': 'https://www.statistik-bw.de/fileadmin/user_upload/medien/bilder/Karten_und_Geometrien_der_Wahlkreise/LTWahlkreise2026-BW_GEOJSON.zip',
        'format': 'geojson_zip',
        'count': 70,
        'attribution': '© Statistisches Landesamt Baden-Württemberg, 2026',
        'license': 'Datenlizenz Deutschland - Namensnennung 2.0',
        'license_url': 'https://www.govdata.de/dl-de/by-2-0',
        'election_year': 2026,
    },
    'BY': {
        'name': 'Bavaria',
        'url': 'https://fragdenstaat.de/anfrage/geometrien-der-stimmkreiseinteilung-zur-landtagswahl-2023-in-bayern/274642/anhang/stimmkreise-2023shp.zip',
        'format': 'shapefile_zip',
        'count': 91,
        'attribution': '© Bayerisches Landesamt für Statistik, 2023',
        'license': 'Datenlizenz Deutschland - Namensnennung 2.0',
        'license_url': 'https://www.govdata.de/dl-de/by-2-0',
        'election_year': 2023,
        'note': 'Stimmkreise structure (91 districts)',
    },
    'BE': {
        'name': 'Berlin',
        'url': 'https://daten.berlin.de/datensaetze/geometrien-der-wahlkreise-für-die-wahl-zum-abgeordnetenhaus-von-berlin-2021',
        'format': 'shapefile_zip',
        'count': 78,
        'attribution': '© Amt für Statistik Berlin-Brandenburg, 2021',
        'license': 'CC BY 3.0 DE',
        'license_url': 'https://creativecommons.org/licenses/by/3.0/de/',
        'election_year': 2021,
    },
    'HB': {
        'name': 'Bremen',
        'url': 'http://gdi2.geo.bremen.de/inspire/download/Wahlbezirke/data/Wahlbezirke_HB.zip',
        'format': 'shapefile_zip',
        'count': None,  # City-state structure varies
        'attribution': '© GeoInformation Bremen, 2023',
        'license': 'CC BY 4.0',
        'license_url': 'https://creativecommons.org/licenses/by/4.0/',
        'election_year': 2023,
        'note': 'Wahlbezirke (polling districts)',
    },
    'NI': {
        'name': 'Lower Saxony',
        'url': 'https://www.statistik.niedersachsen.de/download/182342',
        'format': 'shapefile_zip',
        'count': 87,
        'attribution': '© Landesamt für Statistik Niedersachsen, 2022',
        'license': 'CC BY 4.0',
        'license_url': 'https://creativecommons.org/licenses/by/4.0/',
        'election_year': 2022,
    },
    'NW': {
        'name': 'North Rhine-Westphalia',
        'url': 'https://www.wahlergebnisse.nrw/landtagswahlen/2022/wahlkreiskarten/16_LW2022_NRW_Wahlkreise.zip',
        'format': 'shapefile_zip',
        'count': 128,
        'attribution': '© IT.NRW, 2022',
        'license': 'Datenlizenz Deutschland - Namensnennung 2.0',
        'license_url': 'https://www.govdata.de/dl-de/by-2-0',
        'election_year': 2022,
    },
    'ST': {
        'name': 'Saxony-Anhalt',
        'url': 'https://wahlergebnisse.sachsen-anhalt.de/wahlen/lt21/wahlkreiseinteilung/downloads/download.php',
        'format': 'shapefile_zip',
        'count': 41,
        'attribution': '© Statistisches Landesamt Sachsen-Anhalt, 2021',
        'license': 'Datenlizenz Deutschland - Namensnennung 2.0',
        'license_url': 'https://www.govdata.de/dl-de/by-2-0',
        'election_year': 2021,
    },
    'SH': {
        'name': 'Schleswig-Holstein',
        'url': 'https://geodienste.hamburg.de/download?url=https://geodienste.hamburg.de/SH_WFS_Wahlen&f=json',
        'format': 'geojson_direct',
        'count': 35,
        'attribution': '© Statistik Nord, 2022',
        'license': 'Datenlizenz Deutschland - Namensnennung 2.0',
        'license_url': 'https://www.govdata.de/dl-de/by-2-0',
        'election_year': 2022,
    },
    'TH': {
        'name': 'Thuringia',
        'url': 'https://wahlen.thueringen.de/landtagswahlen/informationen/vektor/2024/16TH_L24_Wahlkreiseinteilung.zip',
        'format': 'geopackage_zip',
        'count': 44,
        'attribution': '© Thüringer Landesamt für Statistik, 2024',
        'license': 'Datenlizenz Deutschland - Namensnennung 2.0',
        'license_url': 'https://www.govdata.de/dl-de/by-2-0',
        'election_year': 2024,
    },
}
```

**Step 2: Add command-line arguments for state operations**

Modify the `add_arguments` method (around line 28) to add new options:

```python
def add_arguments(self, parser):
    parser.add_argument(
        "--url",
        default=DEFAULT_WAHLKREIS_URL,
        help="Source URL for the GeoJSON or ZIP archive containing the Wahlkreis data.",
    )
    parser.add_argument(
        "--output",
        default=str(getattr(settings, "CONSTITUENCY_BOUNDARIES_PATH", "wahlkreise.geojson")),
        help="Destination file path for the downloaded GeoJSON.",
    )
    parser.add_argument(
        "--zip-member",
        default=None,
        help=(
            "When the downloaded file is a ZIP archive, specify the member name to extract. "
            "If omitted, the first *.geojson member will be used."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing file without prompting.",
    )
    # New state-related arguments
    parser.add_argument(
        "--state",
        choices=list(STATE_SOURCES.keys()),
        help="Fetch data for a specific German state (Landtagswahl boundaries).",
    )
    parser.add_argument(
        "--all-states",
        action="store_true",
        help="Fetch data for all available states.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available states and their configuration.",
    )
```

**Step 3: Implement --list functionality**

Add this helper method before the `handle` method:

```python
def _list_states(self):
    """Display available state configurations."""
    self.stdout.write(self.style.SUCCESS("\nAvailable State Data Sources:"))
    self.stdout.write("=" * 80)

    for code, config in STATE_SOURCES.items():
        self.stdout.write(f"\n{code} - {config['name']}")
        self.stdout.write(f"  Election: {config['election_year']}")
        self.stdout.write(f"  Districts: {config.get('count', 'N/A')}")
        self.stdout.write(f"  Format: {config['format']}")
        self.stdout.write(f"  License: {config['license']}")
        if config.get('note'):
            self.stdout.write(f"  Note: {config['note']}")
        self.stdout.write(f"  URL: {config['url'][:70]}...")

    self.stdout.write("\n" + "=" * 80)
    self.stdout.write(f"\nTotal: {len(STATE_SOURCES)} states with direct downloads\n")
```

**Step 4: Update handle method to route state operations**

Replace the beginning of the `handle` method (lines 53-62) with:

```python
def handle(self, *args, **options):
    # Handle --list flag
    if options.get('list'):
        self._list_states()
        return

    # Handle --all-states flag
    if options.get('all_states'):
        self._fetch_all_states(options['force'])
        return

    # Handle --state flag
    if options.get('state'):
        state_code = options['state']
        self._fetch_state(state_code, options['force'])
        return

    # Default: fetch federal data (existing behavior)
    url: str = options["url"]
    output_path = Path(options["output"]).expanduser().resolve()
    zip_member: Optional[str] = options["zip_member"]
    force: bool = options["force"]

    if output_path.exists() and not force:
        raise CommandError(
            f"Output file {output_path} already exists. Use --force to overwrite."
        )

    self.stdout.write(f"Downloading Wahlkreis data from {url} ...")

    # Rest of existing federal download logic continues unchanged...
```

**Step 5: Commit initial state configuration**

```bash
git add website/letters/management/commands/fetch_wahlkreis_data.py
git commit -m "feat: add state source configuration and CLI flags to fetch_wahlkreis_data"
```

---

## Task 2: Implement State Fetching Logic

**Files:**
- Modify: `website/letters/management/commands/fetch_wahlkreis_data.py`

**Step 1: Add _fetch_state helper method**

Add this method after the `_list_states` method:

```python
def _fetch_state(self, state_code: str, force: bool):
    """Fetch data for a single state."""
    config = STATE_SOURCES[state_code]

    self.stdout.write(
        self.style.SUCCESS(f"\nFetching {config['name']} ({state_code}) Landtagswahl data...")
    )
    self.stdout.write(f"  Source: {config['url']}")
    self.stdout.write(f"  Expected districts: {config.get('count', 'Unknown')}")

    # Determine output path
    data_dir = Path(getattr(settings, 'CONSTITUENCY_BOUNDARIES_PATH', 'wahlkreise.geojson')).parent
    output_path = data_dir / f"wahlkreise_{state_code.lower()}.geojson"

    if output_path.exists() and not force:
        raise CommandError(
            f"Output file {output_path} already exists. Use --force to overwrite."
        )

    # Download data
    try:
        response = requests.get(config['url'], timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise CommandError(f"Failed to download {state_code} data: {exc}") from exc

    data_bytes = response.content
    content_type = response.headers.get("Content-Type", "")

    # Process based on format
    format_type = config['format']

    if format_type == 'geojson_direct':
        geojson_text = data_bytes.decode('utf-8')
    elif format_type == 'geojson_zip':
        geojson_bytes = self._extract_from_zip(data_bytes, zip_member=None)
        geojson_text = geojson_bytes.decode('utf-8')
    elif format_type == 'shapefile_zip':
        self.stdout.write("  Converting Shapefile to GeoJSON...")
        geojson_text = self._convert_shapefile_to_geojson(data_bytes)
    elif format_type == 'geopackage_zip':
        self.stdout.write("  Converting GeoPackage to GeoJSON...")
        geojson_text = self._convert_geopackage_to_geojson(data_bytes)
    else:
        raise CommandError(f"Unsupported format: {format_type}")

    # Normalize properties
    geojson_text = self._normalize_state_geojson(
        geojson_text,
        state_code,
        config['name']
    )

    # Validate
    try:
        geojson_data = json.loads(geojson_text)
        feature_count = len(geojson_data.get("features", []))
        self.stdout.write(f"  Validated GeoJSON with {feature_count} features")

        if config.get('count') and feature_count != config['count']:
            self.stdout.write(
                self.style.WARNING(
                    f"  Warning: Expected {config['count']} features but got {feature_count}"
                )
            )
    except json.JSONDecodeError as exc:
        raise CommandError("Downloaded data is not valid GeoJSON") from exc

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(geojson_text, encoding="utf-8")

    self.stdout.write(
        self.style.SUCCESS(f"✓ Saved {state_code} data to {output_path}")
    )
```

**Step 2: Add _fetch_all_states helper method**

```python
def _fetch_all_states(self, force: bool):
    """Fetch data for all available states."""
    self.stdout.write(
        self.style.SUCCESS(f"\nFetching all {len(STATE_SOURCES)} states...")
    )

    success_count = 0
    failed = []

    for state_code in STATE_SOURCES.keys():
        try:
            self._fetch_state(state_code, force)
            success_count += 1
        except (CommandError, Exception) as e:
            failed.append((state_code, str(e)))
            self.stdout.write(
                self.style.ERROR(f"✗ Failed to fetch {state_code}: {e}")
            )

    # Summary
    self.stdout.write("\n" + "=" * 80)
    self.stdout.write(f"Completed: {success_count}/{len(STATE_SOURCES)} states")

    if failed:
        self.stdout.write(self.style.WARNING("\nFailed states:"))
        for code, error in failed:
            self.stdout.write(f"  {code}: {error[:100]}")

    self.stdout.write("")
```

**Step 3: Add GeoPackage conversion support**

Add this method after `_convert_shapefile_to_geojson`:

```python
def _convert_geopackage_to_geojson(self, data: bytes) -> str:
    """Convert GeoPackage in ZIP to GeoJSON using fiona."""
    try:
        import fiona
    except ImportError:
        raise CommandError(
            "fiona library is required to convert GeoPackage files. "
            "Install with: pip install fiona"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Extract GPKG file from ZIP
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            gpkg_files = [name for name in archive.namelist() if name.lower().endswith('.gpkg')]
            if not gpkg_files:
                raise CommandError("No .gpkg file found in ZIP archive")

            gpkg_file = gpkg_files[0]
            archive.extract(gpkg_file, tmpdir_path)

        # Convert using fiona
        gpkg_path = tmpdir_path / gpkg_file

        features = []
        with fiona.open(str(gpkg_path)) as src:
            for feature in src:
                features.append({
                    "type": "Feature",
                    "geometry": feature["geometry"],
                    "properties": dict(feature["properties"])
                })

        geojson = {
            "type": "FeatureCollection",
            "features": features
        }

        return json.dumps(geojson, ensure_ascii=False, indent=None)
```

**Step 4: Add property normalization**

Add this method to standardize GeoJSON properties across states:

```python
def _normalize_state_geojson(self, geojson_text: str, state_code: str, state_name: str) -> str:
    """Add standardized properties to state GeoJSON features."""
    data = json.loads(geojson_text)

    for feature in data.get("features", []):
        props = feature.get("properties", {})

        # Ensure standard fields exist
        if "LAND_CODE" not in props:
            props["LAND_CODE"] = state_code
        if "LAND_NAME" not in props:
            props["LAND_NAME"] = state_name
        if "LEVEL" not in props:
            props["LEVEL"] = "STATE"

        # Normalize WKR_NR to integer if it's a string
        if "WKR_NR" in props and isinstance(props["WKR_NR"], str):
            try:
                props["WKR_NR"] = int(props["WKR_NR"])
            except ValueError:
                pass  # Keep as string if not numeric

        feature["properties"] = props

    return json.dumps(data, ensure_ascii=False, indent=None)
```

**Step 5: Commit state fetching implementation**

```bash
git add website/letters/management/commands/fetch_wahlkreis_data.py
git commit -m "feat: implement state data fetching with format conversion"
```

---

## Task 3: Write Tests for State Fetching Command

**Files:**
- Create: `website/letters/tests/test_fetch_wahlkreis_state_data.py`

**Step 1: Write test for --list flag**

Create the test file:

```python
# ABOUTME: Tests for state-level Wahlkreise data fetching command.
# ABOUTME: Validates state configuration listing, fetching, and format conversion.

from io import StringIO
from unittest.mock import patch, Mock
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
import json


class FetchWahlkreisStateDataTests(TestCase):
    """Test state data fetching functionality."""

    def test_list_states_shows_all_configurations(self):
        """Test --list flag displays all 9 state configurations."""
        out = StringIO()
        call_command('fetch_wahlkreis_data', '--list', stdout=out)

        output = out.getvalue()

        # Check header
        self.assertIn('Available State Data Sources', output)

        # Check all 9 states are listed
        expected_states = ['BW', 'BY', 'BE', 'HB', 'NI', 'NW', 'ST', 'SH', 'TH']
        for state_code in expected_states:
            self.assertIn(state_code, output)

        # Check key information is shown
        self.assertIn('Baden-Württemberg', output)
        self.assertIn('Election:', output)
        self.assertIn('Districts:', output)
        self.assertIn('License:', output)
        self.assertIn('Total: 9 states', output)
```

**Step 2: Run test to verify it fails**

```bash
cd website
uv run python manage.py test letters.tests.test_fetch_wahlkreis_state_data::FetchWahlkreisStateDataTests::test_list_states_shows_all_configurations -v
```

Expected: Test should PASS (implementation already complete)

**Step 3: Write test for single state fetch with mocked download**

Add this test to the class:

```python
@patch('requests.get')
def test_fetch_single_state_geojson_direct(self, mock_get):
    """Test fetching a single state with direct GeoJSON format."""
    # Mock response for Schleswig-Holstein (GeoJSON direct)
    mock_geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [10.0, 54.0]},
                "properties": {"WKR_NR": "1", "WKR_NAME": "Test District"}
            }
        ]
    }

    mock_response = Mock()
    mock_response.content = json.dumps(mock_geojson).encode('utf-8')
    mock_response.headers = {'Content-Type': 'application/json'}
    mock_response.raise_for_status = Mock()
    mock_get.return_value = mock_response

    out = StringIO()

    with self.settings(CONSTITUENCY_BOUNDARIES_PATH='test_data/wahlkreise.geojson'):
        # Create temp directory
        Path('test_data').mkdir(exist_ok=True)

        try:
            call_command('fetch_wahlkreis_data', '--state', 'SH', '--force', stdout=out)

            output = out.getvalue()
            self.assertIn('Schleswig-Holstein', output)
            self.assertIn('Saved SH data', output)

            # Verify file was created
            output_file = Path('test_data/wahlkreise_sh.geojson')
            self.assertTrue(output_file.exists())

            # Verify normalization
            saved_data = json.loads(output_file.read_text())
            feature = saved_data['features'][0]
            self.assertEqual(feature['properties']['LAND_CODE'], 'SH')
            self.assertEqual(feature['properties']['LAND_NAME'], 'Schleswig-Holstein')
            self.assertEqual(feature['properties']['LEVEL'], 'STATE')
        finally:
            # Cleanup
            import shutil
            if Path('test_data').exists():
                shutil.rmtree('test_data')
```

**Step 4: Run test to verify it passes**

```bash
cd website
uv run python manage.py test letters.tests.test_fetch_wahlkreis_state_data::FetchWahlkreisStateDataTests::test_fetch_single_state_geojson_direct -v
```

Expected: PASS

**Step 5: Write test for --all-states with partial failures**

Add this test:

```python
@patch('requests.get')
def test_fetch_all_states_handles_failures_gracefully(self, mock_get):
    """Test --all-states continues on failures and reports summary."""
    # Make first request succeed, second fail, third succeed
    def side_effect(*args, **kwargs):
        url = args[0]
        if 'statistik-bw' in url:  # BW succeeds
            response = Mock()
            response.content = json.dumps({
                "type": "FeatureCollection",
                "features": []
            }).encode('utf-8')
            response.headers = {}
            response.raise_for_status = Mock()
            return response
        else:
            # Other states fail
            raise Exception("Network error")

    mock_get.side_effect = side_effect

    out = StringIO()

    with self.settings(CONSTITUENCY_BOUNDARIES_PATH='test_data/wahlkreise.geojson'):
        Path('test_data').mkdir(exist_ok=True)

        try:
            call_command('fetch_wahlkreis_data', '--all-states', '--force', stdout=out)

            output = out.getvalue()
            self.assertIn('Fetching all 9 states', output)
            self.assertIn('Completed:', output)
            self.assertIn('Failed states:', output)
        finally:
            import shutil
            if Path('test_data').exists():
                shutil.rmtree('test_data')
```

**Step 6: Run all tests**

```bash
cd website
uv run python manage.py test letters.tests.test_fetch_wahlkreis_state_data -v
```

Expected: All tests PASS

**Step 7: Commit tests**

```bash
git add website/letters/tests/test_fetch_wahlkreis_state_data.py
git commit -m "test: add tests for state data fetching command"
```

---

## Task 4: Refactor WahlkreisLocator to Load State Data

**Files:**
- Modify: `website/letters/services/geocoding.py:224-294`
- Test: `website/letters/tests/test_address_matching.py`

**Step 1: Write failing test for state data loading**

Add to `website/letters/tests/test_address_matching.py` in the `WahlkreisLocatorTests` class:

```python
def test_locator_loads_available_state_files(self):
    """Test WahlkreisLocator loads state GeoJSON files if they exist."""
    # Create a mock state file
    import tempfile
    import shutil

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Copy federal fixture
        federal_path = tmpdir_path / 'wahlkreise_federal.geojson'
        shutil.copy(self.fixture_path, federal_path)

        # Create mock state file for BW
        state_data = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[9.0, 48.7], [9.1, 48.7], [9.1, 48.8], [9.0, 48.8], [9.0, 48.7]]]
                },
                "properties": {
                    "WKR_NR": 1,
                    "WKR_NAME": "Stuttgart I",
                    "LAND_CODE": "BW",
                    "LAND_NAME": "Baden-Württemberg",
                    "LEVEL": "STATE"
                }
            }]
        }

        state_path = tmpdir_path / 'wahlkreise_bw.geojson'
        state_path.write_text(json.dumps(state_data))

        # Initialize locator with this directory
        locator = WahlkreisLocator(geojson_path=str(federal_path))

        # Verify state data was loaded
        self.assertIn('BW', locator.state_constituencies)
        self.assertEqual(len(locator.state_constituencies['BW']), 1)
```

**Step 2: Run test to verify it fails**

```bash
cd website
uv run python manage.py test letters.tests.test_address_matching::WahlkreisLocatorTests::test_locator_loads_available_state_files -v
```

Expected: FAIL with "AttributeError: 'WahlkreisLocator' object has no attribute 'state_constituencies'"

**Step 3: Modify WahlkreisLocator.__init__ to load state files**

Replace the `__init__` method (lines 231-269) with:

```python
def __init__(self, geojson_path=None):
    """
    Load and parse GeoJSON constituencies for federal and available states.

    Args:
        geojson_path: Path to the federal GeoJSON file. If None, uses settings.CONSTITUENCY_BOUNDARIES_PATH
    """
    from shapely.geometry import shape

    if geojson_path is None:
        geojson_path = settings.CONSTITUENCY_BOUNDARIES_PATH

    geojson_path = Path(geojson_path)
    data_dir = geojson_path.parent

    # Use cached constituencies if available and path matches
    if (WahlkreisLocator._cached_constituencies is not None and
        WahlkreisLocator._cached_path == str(geojson_path)):
        self.constituencies = WahlkreisLocator._cached_constituencies
        self.state_constituencies = WahlkreisLocator._cached_state_constituencies
        return

    # Load federal constituencies
    self.constituencies = []
    with open(geojson_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Parse federal features
    for feature in data.get('features', []):
        properties = feature.get('properties', {})
        wkr_nr = properties.get('WKR_NR')
        wkr_name = properties.get('WKR_NAME', '')
        land_name = properties.get('LAND_NAME', '')

        # Parse geometry using Shapely
        geometry = shape(feature['geometry'])

        # Store as tuple: (wkr_nr, wkr_name, land_name, geometry)
        self.constituencies.append((wkr_nr, wkr_name, land_name, geometry))

    # Load available state files
    self.state_constituencies = {}

    state_codes = ['BW', 'BY', 'BE', 'HB', 'NI', 'NW', 'ST', 'SH', 'TH']
    for state_code in state_codes:
        state_file = data_dir / f'wahlkreise_{state_code.lower()}.geojson'

        if state_file.exists():
            state_data = []
            with open(state_file, 'r', encoding='utf-8') as f:
                state_geojson = json.load(f)

            for feature in state_geojson.get('features', []):
                properties = feature.get('properties', {})
                wkr_nr = properties.get('WKR_NR')
                wkr_name = properties.get('WKR_NAME', '')
                land_code = properties.get('LAND_CODE', state_code)
                land_name = properties.get('LAND_NAME', '')

                geometry = shape(feature['geometry'])

                # Store: (wkr_nr, wkr_name, land_code, land_name, geometry)
                state_data.append((wkr_nr, wkr_name, land_code, land_name, geometry))

            self.state_constituencies[state_code] = state_data

    # Cache the parsed constituencies
    WahlkreisLocator._cached_constituencies = self.constituencies
    WahlkreisLocator._cached_state_constituencies = self.state_constituencies
    WahlkreisLocator._cached_path = str(geojson_path)
```

**Step 4: Add class-level cache variable for state data**

Add this line after line 228 (the existing cache variables):

```python
_cached_state_constituencies = None
```

**Step 5: Run test to verify it passes**

```bash
cd website
uv run python manage.py test letters.tests.test_address_matching::WahlkreisLocatorTests::test_locator_loads_available_state_files -v
```

Expected: PASS

**Step 6: Commit state loading implementation**

```bash
git add website/letters/services/geocoding.py website/letters/tests/test_address_matching.py
git commit -m "feat: load state constituency files in WahlkreisLocator"
```

---

## Task 5: Add Internal _locate_detailed Method

**Files:**
- Modify: `website/letters/services/geocoding.py:271-294`
- Test: `website/letters/tests/test_address_matching.py`

**Step 1: Write failing test for detailed location**

Add to `WahlkreisLocatorTests`:

```python
def test_locate_detailed_returns_both_federal_and_state(self):
    """Test _locate_detailed finds both federal and state constituencies."""
    import tempfile
    import shutil

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create federal data with Berlin
        federal_data = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[13.3, 52.5], [13.4, 52.5], [13.4, 52.6], [13.3, 52.6], [13.3, 52.5]]]
                },
                "properties": {
                    "WKR_NR": 83,
                    "WKR_NAME": "Berlin-Mitte",
                    "LAND_NAME": "Berlin",
                    "LAND_CODE": "BE"
                }
            }]
        }

        federal_path = tmpdir_path / 'wahlkreise_federal.geojson'
        federal_path.write_text(json.dumps(federal_data))

        # Create state data for Berlin
        state_data = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[13.3, 52.5], [13.4, 52.5], [13.4, 52.6], [13.3, 52.6], [13.3, 52.5]]]
                },
                "properties": {
                    "WKR_NR": 1,
                    "WKR_NAME": "Mitte",
                    "LAND_CODE": "BE",
                    "LAND_NAME": "Berlin",
                    "LEVEL": "STATE"
                }
            }]
        }

        state_path = tmpdir_path / 'wahlkreise_be.geojson'
        state_path.write_text(json.dumps(state_data))

        locator = WahlkreisLocator(geojson_path=str(federal_path))

        # Point inside Berlin
        result = locator._locate_detailed(52.52, 13.35)

        self.assertIsNotNone(result)
        self.assertIn('federal', result)
        self.assertIn('state', result)

        # Check federal result
        self.assertIsNotNone(result['federal'])
        self.assertEqual(result['federal']['wkr_nr'], 83)
        self.assertEqual(result['federal']['wkr_name'], 'Berlin-Mitte')
        self.assertEqual(result['federal']['land_code'], 'BE')

        # Check state result
        self.assertIsNotNone(result['state'])
        self.assertEqual(result['state']['wkr_nr'], 1)
        self.assertEqual(result['state']['wkr_name'], 'Mitte')
        self.assertEqual(result['state']['land_code'], 'BE')
```

**Step 2: Run test to verify it fails**

```bash
cd website
uv run python manage.py test letters.tests.test_address_matching::WahlkreisLocatorTests::test_locate_detailed_returns_both_federal_and_state -v
```

Expected: FAIL with "AttributeError: 'WahlkreisLocator' object has no attribute '_locate_detailed'"

**Step 3: Add _locate_detailed method**

Add this method before the existing `locate` method:

```python
def _locate_detailed(self, latitude, longitude):
    """
    Find both federal and state constituencies for given coordinates.

    Returns:
        dict with 'federal' and 'state' keys, each containing:
        {
            'wkr_nr': int,
            'wkr_name': str,
            'land_name': str,
            'land_code': str
        }
        or None if not found.
    """
    from shapely.geometry import Point

    point = Point(longitude, latitude)

    # Find federal constituency
    federal_result = None
    for wkr_nr, wkr_name, land_name, geometry in self.constituencies:
        if geometry.contains(point):
            # Extract land_code from federal data (may need to map from land_name)
            land_code = self._land_name_to_code(land_name)
            federal_result = {
                'wkr_nr': wkr_nr,
                'wkr_name': wkr_name,
                'land_name': land_name,
                'land_code': land_code
            }
            break

    # Find state constituency if federal found
    state_result = None
    if federal_result:
        land_code = federal_result['land_code']

        if land_code in self.state_constituencies:
            for wkr_nr, wkr_name, state_land_code, land_name, geometry in self.state_constituencies[land_code]:
                if geometry.contains(point):
                    state_result = {
                        'wkr_nr': wkr_nr,
                        'wkr_name': wkr_name,
                        'land_name': land_name,
                        'land_code': state_land_code
                    }
                    break

    return {
        'federal': federal_result,
        'state': state_result
    }

def _land_name_to_code(self, land_name: str) -> str:
    """Map German state names to ISO codes."""
    mapping = {
        'Baden-Württemberg': 'BW',
        'Bayern': 'BY',
        'Berlin': 'BE',
        'Brandenburg': 'BB',
        'Bremen': 'HB',
        'Hamburg': 'HH',
        'Hessen': 'HE',
        'Mecklenburg-Vorpommern': 'MV',
        'Niedersachsen': 'NI',
        'Nordrhein-Westfalen': 'NW',
        'Rheinland-Pfalz': 'RP',
        'Saarland': 'SL',
        'Sachsen': 'SN',
        'Sachsen-Anhalt': 'ST',
        'Schleswig-Holstein': 'SH',
        'Thüringen': 'TH',
    }
    return mapping.get(land_name, '')
```

**Step 4: Modify existing locate to use _locate_detailed**

Replace the `locate` method (lines 271-293) with:

```python
def locate(self, latitude, longitude):
    """
    Find federal constituency containing the given coordinates.

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate

    Returns:
        tuple: (wkr_nr, wkr_name, land_name) or None if not found
    """
    result = self._locate_detailed(latitude, longitude)

    if result and result['federal']:
        fed = result['federal']
        return (fed['wkr_nr'], fed['wkr_name'], fed['land_name'])

    return None
```

**Step 5: Run tests to verify both pass**

```bash
cd website
uv run python manage.py test letters.tests.test_address_matching::WahlkreisLocatorTests -v
```

Expected: All tests PASS (including existing tests for backward compatibility)

**Step 6: Commit detailed location implementation**

```bash
git add website/letters/services/geocoding.py website/letters/tests/test_address_matching.py
git commit -m "feat: add _locate_detailed method to find federal and state constituencies"
```

---

## Task 6: Create Attribution Data Sources Page

**Files:**
- Create: `website/letters/templates/letters/data_sources.html`
- Modify: `website/letters/views.py` (add view)
- Modify: `website/letters/urls.py` (add URL pattern)

**Step 1: Write failing test for data sources view**

Create new test file `website/letters/tests/test_data_sources_view.py`:

```python
# ABOUTME: Tests for data sources attribution page.
# ABOUTME: Validates that all state sources are listed with proper license info.

from django.test import TestCase
from django.urls import reverse


class DataSourcesViewTests(TestCase):
    """Test the data sources attribution page."""

    def test_data_sources_page_loads(self):
        """Test the data sources page is accessible."""
        response = self.client.get(reverse('data_sources'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'letters/data_sources.html')

    def test_page_lists_all_available_states(self):
        """Test all 9 states with data are listed."""
        response = self.client.get(reverse('data_sources'))

        content = response.content.decode()

        # Check all state names appear
        expected_states = [
            'Baden-Württemberg',
            'Bavaria',
            'Berlin',
            'Bremen',
            'Lower Saxony',
            'North Rhine-Westphalia',
            'Saxony-Anhalt',
            'Schleswig-Holstein',
            'Thuringia'
        ]

        for state_name in expected_states:
            self.assertIn(state_name, content)

    def test_page_shows_license_information(self):
        """Test license and attribution info is displayed."""
        response = self.client.get(reverse('data_sources'))

        content = response.content.decode()

        # Check license types appear
        self.assertIn('Datenlizenz Deutschland', content)
        self.assertIn('CC BY', content)

        # Check attribution appears
        self.assertIn('©', content)
        self.assertIn('Statistisches Landesamt', content)

    def test_page_lists_unavailable_states(self):
        """Test that states without data are also mentioned."""
        response = self.client.get(reverse('data_sources'))

        content = response.content.decode()

        # Should mention states without direct downloads
        unavailable_states = ['Brandenburg', 'Hesse', 'Mecklenburg-Vorpommern']

        for state in unavailable_states:
            self.assertIn(state, content)
```

**Step 2: Run test to verify it fails**

```bash
cd website
uv run python manage.py test letters.tests.test_data_sources_view::DataSourcesViewTests::test_data_sources_page_loads -v
```

Expected: FAIL with "NoReverseMatch: Reverse for 'data_sources' not found"

**Step 3: Add URL pattern**

Add to `website/letters/urls.py` in the urlpatterns list:

```python
path('data-sources/', views.data_sources, name='data_sources'),
```

**Step 4: Add view function**

Add to `website/letters/views.py` at the end:

```python
def data_sources(request):
    """Display data sources and attribution information."""
    from .management.commands.fetch_wahlkreis_data import STATE_SOURCES

    # States with data available
    available_states = []
    for code, config in STATE_SOURCES.items():
        available_states.append({
            'code': code,
            'name': config['name'],
            'attribution': config['attribution'],
            'license': config['license'],
            'license_url': config.get('license_url', ''),
            'election_year': config['election_year'],
            'count': config.get('count', 'N/A'),
            'source_url': config['url'],
            'note': config.get('note', ''),
        })

    # Sort by name
    available_states.sort(key=lambda x: x['name'])

    # States without direct downloads
    unavailable_states = [
        {
            'name': 'Brandenburg',
            'contact': 'Ministerium des Innern und für Kommunales, Potsdam',
            'note': 'No state-wide Landtagswahl download. Municipal data available for some cities (e.g., Potsdam).'
        },
        {
            'name': 'Hamburg',
            'contact': 'WFS Service available',
            'note': 'Data available via WFS service (requires GIS tools). Excellent detail with ~1,300 Stimmbezirke.'
        },
        {
            'name': 'Hesse',
            'contact': 'presse@statistik.hessen.de',
            'note': 'Geodata not publicly available. Contact Hessisches Statistisches Landesamt to request.'
        },
        {
            'name': 'Mecklenburg-Vorpommern',
            'contact': 'LAIV-MV',
            'note': 'Shapefiles referenced but require contact with LAIV-MV for downloads.'
        },
        {
            'name': 'Rhineland-Palatinate',
            'contact': 'Landeswahlleiter via wahlen.rlp.de',
            'note': 'Only PDF maps available. No machine-readable geodata.'
        },
        {
            'name': 'Saarland',
            'contact': 'landeswahlleitung@innen.saarland.de',
            'note': 'Special system with only 3 large regional constituencies. Contact required.'
        },
        {
            'name': 'Saxony',
            'contact': 'WMS Service',
            'note': 'WMS service only (visualization, not vector data). May need to contact Statistisches Landesamt.'
        },
    ]

    context = {
        'available_states': available_states,
        'unavailable_states': unavailable_states,
    }

    return render(request, 'letters/data_sources.html', context)
```

**Step 5: Create template**

Create `website/letters/templates/letters/data_sources.html`:

```html
{% extends 'letters/base.html' %}
{% load i18n %}

{% block title %}{% trans "Data Sources & Attribution" %} - WriteThem.eu{% endblock %}

{% block content %}
<div class="card">
    <h2>{% trans "Electoral District Data Sources" %}</h2>

    <p class="text-muted">
        {% trans "WriteThem.eu uses official electoral district (Wahlkreis) boundary data from German statistical offices and electoral authorities. This page provides full attribution and license information for all data sources." %}
    </p>

    <h3 class="mt-4">{% trans "Available State Data" %}</h3>
    <p class="text-muted">
        {% trans "The following states provide direct downloads of Landtagswahl constituency boundaries:" %}
    </p>

    <div class="table-responsive">
        <table class="table">
            <thead>
                <tr>
                    <th>{% trans "State" %}</th>
                    <th>{% trans "Districts" %}</th>
                    <th>{% trans "Election Year" %}</th>
                    <th>{% trans "License" %}</th>
                    <th>{% trans "Attribution" %}</th>
                </tr>
            </thead>
            <tbody>
                {% for state in available_states %}
                <tr>
                    <td>
                        <strong>{{ state.name }}</strong> ({{ state.code }})
                        {% if state.note %}
                        <br><small class="text-muted">{{ state.note }}</small>
                        {% endif %}
                    </td>
                    <td>{{ state.count }}</td>
                    <td>{{ state.election_year }}</td>
                    <td>
                        {% if state.license_url %}
                        <a href="{{ state.license_url }}" target="_blank" rel="noopener">{{ state.license }}</a>
                        {% else %}
                        {{ state.license }}
                        {% endif %}
                    </td>
                    <td><small>{{ state.attribution }}</small></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <h3 class="mt-5">{% trans "States Without Direct Downloads" %}</h3>
    <p class="text-muted">
        {% trans "The following states do not provide direct downloads of constituency boundary data. Contact information is provided for data requests:" %}
    </p>

    <div class="list-group">
        {% for state in unavailable_states %}
        <div class="list-group-item">
            <h5 class="mb-1">{{ state.name }}</h5>
            <p class="mb-1"><strong>{% trans "Contact:" %}</strong> {{ state.contact }}</p>
            <small class="text-muted">{{ state.note }}</small>
        </div>
        {% endfor %}
    </div>

    <div class="alert alert-info mt-4">
        <h4>{% trans "About Federal Data" %}</h4>
        <p class="mb-0">
            {% trans "Federal Bundestag constituency data is sourced from:" %}<br>
            <strong>© Die Bundeswahlleiterin, Statistisches Bundesamt, Wiesbaden 2025</strong><br>
            <small>{% trans "License: Official government data, freely available for reuse with attribution" %}</small>
        </p>
    </div>

    <div class="mt-4">
        <h4>{% trans "Data Usage Policy" %}</h4>
        <p>
            {% trans "All data is used in accordance with the respective licenses. Attribution is provided as required. If you believe any data is used incorrectly, please contact us." %}
        </p>
    </div>
</div>
{% endblock %}
```

**Step 6: Run tests to verify they pass**

```bash
cd website
uv run python manage.py test letters.tests.test_data_sources_view -v
```

Expected: All tests PASS

**Step 7: Commit attribution page**

```bash
git add website/letters/templates/letters/data_sources.html website/letters/views.py website/letters/urls.py website/letters/tests/test_data_sources_view.py
git commit -m "feat: add data sources attribution page"
```

---

## Task 7: Add Link to Attribution Page in Footer/Navigation

**Files:**
- Modify: `website/letters/templates/letters/base.html`

**Step 1: Find footer or navigation section**

Locate the footer or navigation links in the base template (search for `<footer>` or `<nav>`).

**Step 2: Add link to data sources page**

Add this link in an appropriate location (e.g., footer):

```html
<a href="{% url 'data_sources' %}">{% trans "Data Sources" %}</a>
```

**Step 3: Verify link appears on pages**

Manual test: Start development server and check that link appears:

```bash
cd website
uv run python manage.py runserver
```

Visit http://localhost:8000 and verify "Data Sources" link appears in footer.

**Step 4: Commit footer link**

```bash
git add website/letters/templates/letters/base.html
git commit -m "feat: add data sources link to site footer"
```

---

## Task 8: Documentation and README Updates

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `README.md` (if exists)

**Step 1: Document state data architecture**

Add a section to `docs/ARCHITECTURE.md`:

```markdown
## State-Level Electoral Districts

### Data Files

Electoral district boundaries are stored as GeoJSON files in the data directory:

- `wahlkreise_federal.geojson` - Federal Bundestag constituencies (299 districts)
- `wahlkreise_{state}.geojson` - State Landtag constituencies (9 states available)

Available state files:
- `wahlkreise_bw.geojson` - Baden-Württemberg (70 districts)
- `wahlkreise_by.geojson` - Bavaria (91 Stimmkreise)
- `wahlkreise_be.geojson` - Berlin (78 districts)
- `wahlkreise_hb.geojson` - Bremen (city-state structure)
- `wahlkreise_ni.geojson` - Lower Saxony (87 districts)
- `wahlkreise_nw.geojson` - North Rhine-Westphalia (128 districts)
- `wahlkreise_st.geojson` - Saxony-Anhalt (41 districts)
- `wahlkreise_sh.geojson` - Schleswig-Holstein (35 districts)
- `wahlkreise_th.geojson` - Thuringia (44 districts)

### Fetching State Data

```bash
# List available states
python manage.py fetch_wahlkreis_data --list

# Fetch single state
python manage.py fetch_wahlkreis_data --state BW

# Fetch all available states
python manage.py fetch_wahlkreis_data --all-states
```

### WahlkreisLocator Service

The `WahlkreisLocator` class loads federal and all available state files on initialization.

Public API (unchanged):
- `locate(lat, lon)` - Returns federal Wahlkreis as `(wkr_nr, wkr_name, land_name)` tuple

Internal API (for future use):
- `_locate_detailed(lat, lon)` - Returns dict with both `federal` and `state` constituencies

State data is loaded automatically but only federal data is returned by the public API for backward compatibility.

### Attribution

All data sources are listed on the `/data-sources/` page with full license and attribution information as required by data providers.
```

**Step 2: Add usage instructions to README**

If `README.md` exists at project root, add a "Data Setup" section:

```markdown
## Data Setup

### Downloading Electoral District Boundaries

WriteThem.eu requires electoral district (Wahlkreis) boundary data for address-based representative lookup.

#### Federal Data

```bash
python manage.py fetch_wahlkreis_data
```

#### State Data (Optional)

Download Landtagswahl boundaries for German states:

```bash
# List available states
python manage.py fetch_wahlkreis_data --list

# Download all 9 available states
python manage.py fetch_wahlkreis_data --all-states

# Or download specific states
python manage.py fetch_wahlkreis_data --state BW
python manage.py fetch_wahlkreis_data --state BE
```

Currently supported states: BW, BY, BE, HB, NI, NW, ST, SH, TH

See `/data-sources/` page for full attribution and license information.
```

**Step 3: Commit documentation**

```bash
git add docs/ARCHITECTURE.md README.md
git commit -m "docs: add state data architecture and usage instructions"
```

---

## Task 9: Integration Test - Full Workflow

**Files:**
- Create: `website/letters/tests/test_state_data_integration.py`

**Step 1: Write integration test**

Create comprehensive test that exercises the full workflow:

```python
# ABOUTME: Integration tests for state-level Wahlkreise data workflow.
# ABOUTME: Tests end-to-end: fetch command, file creation, locator loading, and lookup.

from django.test import TestCase
from django.core.management import call_command
from django.conf import settings
from pathlib import Path
from unittest.mock import patch, Mock
import json
import tempfile
import shutil

from letters.services.geocoding import WahlkreisLocator


class StateDataIntegrationTest(TestCase):
    """Test complete state data workflow from fetch to lookup."""

    def setUp(self):
        """Create temporary data directory."""
        self.tmpdir = tempfile.mkdtemp()
        self.data_dir = Path(self.tmpdir)

        # Create minimal federal data
        federal_data = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[9.0, 48.7], [9.5, 48.7], [9.5, 49.0], [9.0, 49.0], [9.0, 48.7]]]
                },
                "properties": {
                    "WKR_NR": 258,
                    "WKR_NAME": "Stuttgart I",
                    "LAND_NAME": "Baden-Württemberg"
                }
            }]
        }

        self.federal_path = self.data_dir / 'wahlkreise_federal.geojson'
        self.federal_path.write_text(json.dumps(federal_data))

    def tearDown(self):
        """Clean up temporary directory."""
        if Path(self.tmpdir).exists():
            shutil.rmtree(self.tmpdir)

    @patch('requests.get')
    def test_full_workflow_fetch_and_locate(self, mock_get):
        """Test: fetch state data -> load in locator -> find constituency."""

        # Mock BW state data download
        state_data = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[9.0, 48.7], [9.5, 48.7], [9.5, 49.0], [9.0, 49.0], [9.0, 48.7]]]
                },
                "properties": {
                    "WKR_NR": "1",
                    "WKR_NAME": "Stuttgart I"
                }
            }]
        }

        mock_response = Mock()
        mock_response.content = json.dumps(state_data).encode('utf-8')
        mock_response.headers = {}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        # Step 1: Fetch state data
        with self.settings(CONSTITUENCY_BOUNDARIES_PATH=str(self.federal_path)):
            call_command('fetch_wahlkreis_data', '--state', 'BW', '--force', stdout=Mock())

        # Verify file was created
        state_file = self.data_dir / 'wahlkreise_bw.geojson'
        self.assertTrue(state_file.exists())

        # Verify normalization happened
        saved_data = json.loads(state_file.read_text())
        feature = saved_data['features'][0]
        self.assertEqual(feature['properties']['LAND_CODE'], 'BW')
        self.assertEqual(feature['properties']['LEVEL'], 'STATE')

        # Step 2: Load in WahlkreisLocator
        locator = WahlkreisLocator(geojson_path=str(self.federal_path))

        # Verify state data was loaded
        self.assertIn('BW', locator.state_constituencies)

        # Step 3: Test detailed locate
        result = locator._locate_detailed(48.8, 9.2)

        self.assertIsNotNone(result)
        self.assertIsNotNone(result['federal'])
        self.assertIsNotNone(result['state'])

        # Verify federal result
        self.assertEqual(result['federal']['wkr_nr'], 258)
        self.assertEqual(result['federal']['wkr_name'], 'Stuttgart I')

        # Verify state result
        self.assertEqual(result['state']['wkr_nr'], 1)
        self.assertEqual(result['state']['wkr_name'], 'Stuttgart I')
        self.assertEqual(result['state']['land_code'], 'BW')

        # Step 4: Verify backward compatibility - public API still works
        public_result = locator.locate(48.8, 9.2)

        self.assertIsNotNone(public_result)
        self.assertEqual(public_result[0], 258)  # wkr_nr
        self.assertEqual(public_result[1], 'Stuttgart I')  # wkr_name
        self.assertEqual(public_result[2], 'Baden-Württemberg')  # land_name
```

**Step 2: Run integration test**

```bash
cd website
uv run python manage.py test letters.tests.test_state_data_integration -v
```

Expected: PASS

**Step 3: Commit integration test**

```bash
git add website/letters/tests/test_state_data_integration.py
git commit -m "test: add end-to-end integration test for state data workflow"
```

---

## Task 10: Update Existing Tests to Handle State Data

**Files:**
- Modify: `website/letters/tests/test_address_matching.py`

**Step 1: Check if existing tests still pass**

```bash
cd website
uv run python manage.py test letters.tests.test_address_matching -v
```

If tests fail due to state_constituencies attribute, skip to step 2. If all pass, skip to step 4.

**Step 2: Add state_constituencies initialization fallback**

If any tests fail because mock/fixtures don't have `state_constituencies`, add this to test setUp methods or locator initialization:

```python
# In tests that manually create WahlkreisLocator instances
locator = WahlkreisLocator(self.fixture_path)
if not hasattr(locator, 'state_constituencies'):
    locator.state_constituencies = {}
```

**Step 3: Run tests again**

```bash
cd website
uv run python manage.py test letters.tests.test_address_matching -v
```

Expected: All tests PASS

**Step 4: Commit test fixes if any**

```bash
git add website/letters/tests/test_address_matching.py
git commit -m "test: ensure existing tests compatible with state data loading"
```

---

## Task 11: Add Management Command Help Text

**Files:**
- Modify: `website/letters/management/commands/fetch_wahlkreis_data.py:20-27`

**Step 1: Update command help text**

Update the `help` attribute in the Command class:

```python
help = (
    "Fetch German electoral district (Wahlkreis) boundary data. "
    "Downloads federal Bundestag boundaries by default, or state Landtag boundaries with --state flag. "
    "Converts Shapefiles/GeoPackages to GeoJSON and normalizes properties. "
    "Use --list to see available states. Use --all-states to download all 9 available state datasets."
)
```

**Step 2: Test command help output**

```bash
cd website
uv run python manage.py fetch_wahlkreis_data --help
```

Verify help text is clear and mentions state options.

**Step 3: Commit help text update**

```bash
git add website/letters/management/commands/fetch_wahlkreis_data.py
git commit -m "docs: improve fetch_wahlkreis_data command help text"
```

---

## Task 12: Add Contact Info Table to Research Doc

**Files:**
- Modify: `docs/research/landtagswahlen-wahlkreis-info.md`

**Step 1: Add implementation status section**

Add this section after the "Key contacts" section (around line 61):

```markdown
## Implementation Status

### Currently Integrated (9 states)

The following states have been integrated into WriteThem.eu's data import system:

| State | Code | Status | Command |
|-------|------|--------|---------|
| Baden-Württemberg | BW | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state BW` |
| Bavaria | BY | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state BY` |
| Berlin | BE | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state BE` |
| Bremen | HB | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state HB` |
| Lower Saxony | NI | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state NI` |
| North Rhine-Westphalia | NW | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state NW` |
| Saxony-Anhalt | ST | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state ST` |
| Schleswig-Holstein | SH | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state SH` |
| Thuringia | TH | ✅ Integrated | `python manage.py fetch_wahlkreis_data --state TH` |

Run `python manage.py fetch_wahlkreis_data --all-states` to download all available states.

### Pending Integration (7 states)

The following states require manual contact or additional tooling:

- Brandenburg: No state-wide download, requires municipal requests
- Hamburg: WFS service available (requires WFS client implementation)
- Hesse: Contact required for data access
- Mecklenburg-Vorpommern: Contact LAIV-MV for Shapefile access
- Rhineland-Palatinate: Only PDF maps available
- Saarland: Contact required (special 3-district system)
- Saxony: WMS service only (visualization, not vector data)

See `/data-sources/` page for contact information and data request procedures.
```

**Step 2: Commit documentation update**

```bash
git add docs/research/landtagswahlen-wahlkreis-info.md
git commit -m "docs: add implementation status to state data research"
```

---

## Summary

**Completion Checklist:**

- [x] State configuration added to fetch_wahlkreis_data command
- [x] CLI flags implemented: --state, --all-states, --list
- [x] State fetching logic with format conversion (GeoJSON, Shapefile, GeoPackage)
- [x] Property normalization for standardized state data
- [x] WahlkreisLocator loads state files automatically
- [x] _locate_detailed method returns both federal and state data
- [x] Backward compatibility maintained for existing locate() API
- [x] Attribution page created with full license information
- [x] All tests pass (command tests, locator tests, integration tests)
- [x] Documentation updated (ARCHITECTURE.md, README.md, research docs)

**Usage:**

```bash
# List available states
python manage.py fetch_wahlkreis_data --list

# Download all states
python manage.py fetch_wahlkreis_data --all-states

# Download specific state
python manage.py fetch_wahlkreis_data --state BW

# View attributions
Visit /data-sources/
```

**Next Steps (Future Work):**

- Modify `search_wahlkreis` view to use state data
- Add UI warnings when state data unavailable
- Implement WFS support for Hamburg
- Contact remaining 6 states for data access
