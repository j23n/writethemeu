# ABOUTME: Management command to download Wahlkreis geodata and sync all constituencies to database.
# ABOUTME: Ensures all 299 Bundestag constituencies exist independent of representative assignments.

import io
import json
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

try:
    import shapefile
except ImportError:
    shapefile = None

from letters.models import Parliament, ParliamentTerm, Constituency
from letters.constants import normalize_german_state

# Official Bundeswahlleiterin Shapefile URL (2025 election)
DEFAULT_WAHLKREIS_URL = (
    "https://www.bundeswahlleiterin.de/dam/jcr/a3b60aa9-8fa5-4223-9fb4-0a3a3cebd7d1/"
    "btw25_geometrie_wahlkreise_vg250_shp_geo.zip"
)

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
        'url': 'https://fragdenstaat.de/files/foi/788050/shapefilestimmkreiseltwbayern2023.zip?download',
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
        'url': 'https://download.statistik-berlin-brandenburg.de/265b512e15ac1f85/7adee8c53c6c/RBS_OD_Wahlkreise_AH2021.zip',
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
        'count': None,
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
        'url': 'https://wahlergebnisse.sachsen-anhalt.de/wahlen/lt21/wahlkreiseinteilung/downloads/Wahlkreise_LT_2021.zip',
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
        'format': 'geojson_zip',
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


class Command(BaseCommand):
    """Download Wahlkreis geodata and sync all constituencies to database."""

    help = (
        "Fetch German electoral district (Wahlkreis) boundary data and sync to database. "
        "Downloads federal Bundestag boundaries by default and syncs all 299 constituencies, "
        "or state Landtag boundaries with --state flag (syncs if Parliament/Term exists). "
        "Converts Shapefiles/GeoPackages to GeoJSON and normalizes properties. "
        "Use --list to see available states. Use --all-states to download all 9 available state datasets."
    )

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

    def _get_state_region_name(self, state_code: str) -> str:
        """Map state code to canonical German region name used in Parliament.region."""
        state_name = STATE_SOURCES[state_code]['name']
        return normalize_german_state(state_name) or state_name

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

        # Default: fetch federal data and sync to database
        url: str = options["url"]
        output_path = Path(options["output"]).expanduser().resolve()
        zip_member: Optional[str] = options["zip_member"]
        force: bool = options["force"]

        # If file exists and force is not set, use existing file
        if output_path.exists() and not force:
            self.stdout.write(f"Using existing GeoJSON file at {output_path}")
            geojson_text = output_path.read_text(encoding="utf-8")
            try:
                geojson_data = json.loads(geojson_text)
                feature_count = len(geojson_data.get("features", []))
                self.stdout.write(f"Loaded GeoJSON with {feature_count} features")
            except json.JSONDecodeError as exc:
                raise CommandError("Existing file is not valid GeoJSON") from exc
        else:
            # Download and process the file
            self.stdout.write(f"Downloading Wahlkreis data from {url} ...")

            try:
                response = requests.get(url, timeout=60)
                response.raise_for_status()
            except requests.RequestException as exc:
                raise CommandError(f"Failed to download data: {exc}") from exc

            content_type = response.headers.get("Content-Type", "")
            data_bytes = response.content

            # Check if this is a ZIP file
            if url.lower().endswith(".zip") or "zip" in content_type:
                # Check if it contains a .shp file (Shapefile format)
                if self._zip_contains_shapefile(data_bytes):
                    self.stdout.write("Detected Shapefile in ZIP, converting to GeoJSON...")
                    geojson_text = self._convert_shapefile_to_geojson(data_bytes)
                else:
                    # Extract GeoJSON directly from ZIP
                    geojson_bytes = self._extract_from_zip(data_bytes, zip_member)
                    geojson_text = geojson_bytes.decode("utf-8")
            else:
                geojson_text = data_bytes.decode("utf-8")

            # Validate GeoJSON
            try:
                geojson_data = json.loads(geojson_text)
                feature_count = len(geojson_data.get("features", []))
                self.stdout.write(f"Validated GeoJSON with {feature_count} features")
            except json.JSONDecodeError as exc:
                raise CommandError("Downloaded data is not valid GeoJSON") from exc

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(geojson_text, encoding="utf-8")

            self.stdout.write(self.style.SUCCESS(f"Saved Wahlkreis data to {output_path}"))

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

    def _zip_contains_shapefile(self, data: bytes) -> bool:
        """Check if ZIP contains Shapefile components (.shp)."""
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                return any(name.lower().endswith(".shp") for name in archive.namelist())
        except zipfile.BadZipFile:
            return False

    def _convert_shapefile_to_geojson(self, data: bytes) -> str:
        """Convert Shapefile in ZIP to GeoJSON using pyshp."""
        if shapefile is None:
            raise CommandError(
                "pyshp library is required to convert Shapefiles. "
                "Install with: uv add --dev pyshp"
            )

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Extract all Shapefile components to temp directory
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                shp_files = [name for name in archive.namelist() if name.lower().endswith(".shp")]
                if not shp_files:
                    raise CommandError("No .shp file found in ZIP archive")

                shp_file = shp_files[0]
                base_name = Path(shp_file).stem

                # Extract all related files (.shp, .shx, .dbf, .prj, etc.)
                for member in archive.namelist():
                    if Path(member).stem == base_name:
                        archive.extract(member, tmpdir_path)

            # Convert using pyshp
            shp_path = tmpdir_path / shp_file
            sf = shapefile.Reader(str(shp_path))

            # Convert to GeoJSON
            features = []
            for shape_rec in sf.shapeRecords():
                feature = {
                    "type": "Feature",
                    "geometry": shape_rec.shape.__geo_interface__,
                    "properties": shape_rec.record.as_dict()
                }
                features.append(feature)

            geojson = {
                "type": "FeatureCollection",
                "features": features
            }

            return json.dumps(geojson, ensure_ascii=False, indent=None)

    def _extract_from_zip(self, data: bytes, member: Optional[str]) -> bytes:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            target_name = member
            if target_name is None:
                target_name = next(
                    (name for name in archive.namelist()
                     if name.lower().endswith((".geojson", ".json"))),
                    None,
                )
                if target_name is None:
                    raise CommandError(
                        "ZIP archive does not contain a *.geojson or *.json file. Use --zip-member to specify a file."
                    )

            if target_name not in archive.namelist():
                available = ", ".join(archive.namelist())
                raise CommandError(
                    f"ZIP member '{target_name}' not found. Available members: {available}"
                )

            return archive.read(target_name)

    @transaction.atomic
    def _sync_constituencies_to_db(self, geojson_data: dict) -> dict:
        """Create or update all Wahlkreise as Constituency records in the database."""
        # Get or create Bundestag parliament and current term
        bundestag, _ = Parliament.objects.get_or_create(
            name='Bundestag',
            defaults={
                'level': 'FEDERAL',
                'legislative_body': 'Bundestag',
                'region': 'DE',
                'metadata': {'source': 'wahlkreise_geojson'}
            }
        )

        # Get or create current term (2025-2029)
        term, _ = ParliamentTerm.objects.get_or_create(
            parliament=bundestag,
            name='Bundestag 2025 - 2029',
            defaults={
                'metadata': {'source': 'wahlkreise_geojson'}
            }
        )

        stats = {'created': 0, 'updated': 0}
        features = geojson_data.get('features', [])

        for feature in features:
            props = feature.get('properties', {})
            wkr_nr = props.get('WKR_NR')
            wkr_name = props.get('WKR_NAME')
            land_name = props.get('LAND_NAME')

            if not wkr_nr or not wkr_name:
                continue

            # Generate wahlkreis_id (3-digit zero-padded)
            wahlkreis_id = f"{wkr_nr:03d}"

            # Create constituency name matching the format used by sync_representatives
            constituency_name = f"{wkr_nr} - {wkr_name} (Bundestag 2025 - 2029)"

            # Match by wahlkreis_id + parliament_term
            existing = Constituency.objects.filter(
                parliament_term=term,
                scope='FEDERAL_DISTRICT',
                wahlkreis_id=wahlkreis_id
            ).first()

            if existing:
                # Update existing constituency
                existing.external_id = str(wkr_nr)
                existing.name = constituency_name
                if not existing.metadata:
                    existing.metadata = {}
                existing.metadata.update({
                    'WKR_NR': wkr_nr,
                    'WKR_NAME': wkr_name,
                    'LAND_NAME': land_name,
                    'state': land_name,
                    'source': 'wahlkreise_geojson'
                })
                existing.last_synced_at = timezone.now()
                existing.save()
                stats['updated'] += 1
            else:
                # Create new constituency
                try:
                    Constituency.objects.create(
                        external_id=str(wkr_nr),
                        parliament_term=term,
                        name=constituency_name,
                        scope='FEDERAL_DISTRICT',
                        wahlkreis_id=wahlkreis_id,
                        metadata={
                            'WKR_NR': wkr_nr,
                            'WKR_NAME': wkr_name,
                            'LAND_NAME': land_name,
                            'state': land_name,
                            'source': 'wahlkreise_geojson'
                        },
                        last_synced_at=timezone.now()
                    )
                    stats['created'] += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to create constituency {constituency_name}: {e}"
                        )
                    )
                    raise

        return stats

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

    def _ensure_eu_constituency(self) -> None:
        """Ensure a Germany-wide EU constituency exists."""
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

    @transaction.atomic
    def _sync_state_constituencies_to_db(self, state_code: str, geojson_data: dict) -> dict:
        """Create or update state Wahlkreise as Constituency records in the database."""
        # Map state code to canonical region name
        region_name = self._get_state_region_name(state_code)

        # Find the state parliament
        try:
            parliament = Parliament.objects.get(level='STATE', region=region_name)
        except Parliament.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(
                    f"Parliament not found for region '{region_name}'. "
                    f"Skipping database sync. Run sync_representatives first."
                )
            )
            return {'created': 0, 'updated': 0, 'skipped': True}

        # Find the appropriate ParliamentTerm based on election year
        config = STATE_SOURCES[state_code]
        election_year = config['election_year']

        # Try to find a term that includes this election year
        term = None
        for t in parliament.terms.all():
            # Term names are like "Baden-Württemberg 2021 - 2026"
            if str(election_year) in t.name:
                term = t
                break

        if not term:
            self.stdout.write(
                self.style.WARNING(
                    f"No ParliamentTerm found for {region_name} with election year {election_year}. "
                    f"Available terms: {', '.join(t.name for t in parliament.terms.all())}. "
                    f"Skipping database sync."
                )
            )
            return {'created': 0, 'updated': 0, 'skipped': True}

        stats = {'created': 0, 'updated': 0}
        features = geojson_data.get('features', [])

        for feature in features:
            props = feature.get('properties', {})
            wkr_nr = props.get('WKR_NR')
            wkr_name = props.get('WKR_NAME')

            if not wkr_nr:
                raise ValueError(f"Could not parse wkr_nr from {props}, {feature.keys()}")
            if not wkr_name:
                raise ValueError(f"Could not parse wkr_name from {props}, {feature.keys()}")

            # Ensure wkr_nr is an int
            if isinstance(wkr_nr, str):
                wkr_nr = int(wkr_nr)
            elif isinstance(wkr_nr, float):
                wkr_nr = int(wkr_nr)

            # Generate wahlkreis_id with state prefix (4-digit zero-padded for states)
            wahlkreis_id = f"{state_code}-{str(wkr_nr).zfill(4)}"

            # Create constituency name matching existing format
            # Format: "{wkr_nr} - {name} ({term_name})"
            constituency_name = f"{wkr_nr} - {wkr_name} ({term.name})"

            # Match by wahlkreis_id + parliament_term
            existing = Constituency.objects.filter(
                parliament_term=term,
                scope='STATE_DISTRICT',
                wahlkreis_id=wahlkreis_id
            ).first()

            if existing:
                # Update existing constituency
                existing.name = constituency_name
                if not existing.metadata:
                    existing.metadata = {}
                existing.metadata.update({
                    'WKR_NR': wkr_nr,
                    'WKR_NAME': wkr_name,
                    'LAND_CODE': state_code,
                    'LAND_NAME': region_name,
                    'state': region_name,
                    'source': 'wahlkreise_geojson'
                })
                existing.last_synced_at = timezone.now()
                existing.save()
                stats['updated'] += 1
            else:
                # Create new constituency
                try:
                    Constituency.objects.create(
                        parliament_term=term,
                        name=constituency_name,
                        scope='STATE_DISTRICT',
                        wahlkreis_id=wahlkreis_id,
                        metadata={
                            'WKR_NR': wkr_nr,
                            'WKR_NAME': wkr_name,
                            'LAND_CODE': state_code,
                            'LAND_NAME': region_name,
                            'state': region_name,
                            'source': 'wahlkreise_geojson'
                        },
                        last_synced_at=timezone.now()
                    )
                    stats['created'] += 1
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to create constituency {constituency_name}: {e}"
                        )
                    )
                    raise

        return stats

    def _list_states(self):
        """Display available state configurations."""
        self.stdout.write(self.style.SUCCESS("\nAvailable State Data Sources:"))
        for code, config in STATE_SOURCES.items():
            self.stdout.write(f"\n{code} - {config['name']}")
            self.stdout.write(f"  Election: {config['election_year']}")
            self.stdout.write(f"  URL: {config['url'][:70]}...")
        self.stdout.write(f"\nTotal: {len(STATE_SOURCES)} states with direct downloads\n")

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

        # Process based on format
        format_type = config['format']

        if format_type == 'geojson_direct':
            geojson_text = data_bytes.decode('utf-8')
        elif format_type == 'geojson_zip':
            geojson_bytes = self._extract_from_zip(data_bytes, None)
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

    def _convert_geopackage_to_geojson(self, data: bytes) -> str:
        """Convert GeoPackage in ZIP to GeoJSON using fiona."""
        try:
            import fiona
        except ImportError:
            raise CommandError(
                "fiona library is required to convert GeoPackage files. "
                "Install with: uv add --dev fiona"
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
                        "geometry": feature["geometry"].__geo_interface__,
                        "properties": dict(feature["properties"])
                    })

            geojson = {
                "type": "FeatureCollection",
                "features": features
            }

            return json.dumps(geojson, ensure_ascii=False, indent=None)

    def _normalize_state_geojson(self, geojson_text: str, state_code: str, state_name: str) -> str:
        """Add standardized properties to state GeoJSON features."""
        from letters.services.geocoding import WahlkreisLocator

        data = json.loads(geojson_text)

        for feature in data.get("features", []):
            props = feature.get("properties", {})

            wkr_nr, wkr_name = WahlkreisLocator._normalize_properties(props)

            if wkr_nr is not None:
                props["WKR_NR"] = wkr_nr
            if wkr_name:
                props["WKR_NAME"] = wkr_name

            # Ensure standard fields exist
            if "LAND_CODE" not in props:
                props["LAND_CODE"] = state_code
            if "LAND_NAME" not in props:
                props["LAND_NAME"] = state_name
            if "LEVEL" not in props:
                props["LEVEL"] = "STATE"

            feature["properties"] = props

        return json.dumps(data, ensure_ascii=False, indent=None)
