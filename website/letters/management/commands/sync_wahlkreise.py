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
from letters.constants import normalize_german_state, get_state_code, GERMAN_STATE_ALIASES

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
        parser.add_argument(
            "--api-sync",
            action="store_true",
            help="Sync constituencies from Abgeordnetenwatch API (new approach)",
        )
        parser.add_argument(
            "--enrich-from-geojson",
            action="store_true",
            help="Enrich existing constituencies with list_id from GeoJSON files",
        )

    def handle(self, *args, **options):
        # Handle --enrich-from-geojson flag
        if options.get('enrich_from_geojson'):
            self._handle_enrich_from_geojson()
            return

        # Handle --api-sync flag (new approach)
        if options.get('api_sync'):
            self._handle_api_sync()
            return

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

        # Update list_id on existing constituencies
        self.stdout.write("Updating list_id fields on constituencies...")
        updated = self._update_wahlkreis_ids(geojson_data)
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} constituencies with list_id"))

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

            # Generate list_id (3-digit zero-padded)
            list_id = f"{wkr_nr:03d}"

            # Create constituency name matching the format used by sync_representatives
            constituency_name = f"{wkr_nr} - {wkr_name} (Bundestag 2025 - 2029)"

            # Match by list_id + parliament_term
            existing = Constituency.objects.filter(
                parliament_term=term,
                scope='FEDERAL_DISTRICT',
                list_id=list_id
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
                        list_id=list_id,
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
        """Update list_id field on existing constituencies from GeoJSON."""
        updated_count = 0

        for feature in geojson_data.get('features', []):
            properties = feature.get('properties', {})
            wkr_nr = properties.get('WKR_NR')

            if not wkr_nr:
                continue

            # Normalize to 3-digit string
            list_id = str(wkr_nr).zfill(3)

            # Find constituencies by metadata WKR_NR
            constituencies = Constituency.objects.filter(
                metadata__WKR_NR=wkr_nr,
                scope='FEDERAL_DISTRICT'
            )

            for constituency in constituencies:
                if constituency.list_id != list_id:
                    constituency.list_id = list_id
                    constituency.save(update_fields=['list_id'])
                    updated_count += 1
                    self.stdout.write(
                        f"Updated {constituency.name} with list_id={list_id}"
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
                'list_id': 'DE',
                'metadata': {'country': 'DE'}
            }
        )

        if created:
            self.stdout.write(self.style.SUCCESS(
                f"Created EU constituency: {eu_constituency.name}"
            ))
        else:
            # Update list_id if missing
            if not eu_constituency.list_id:
                eu_constituency.list_id = 'DE'
                eu_constituency.save(update_fields=['list_id'])
                self.stdout.write(f"Updated EU constituency with list_id=DE")

    @transaction.atomic
    def _sync_state_constituencies_to_db(self, state_code: str, geojson_data: dict) -> dict:
        """Create or update state Wahlkreise as Constituency records in the database."""
        # Map state code to canonical region name
        state_name = STATE_SOURCES[state_code]['name']
        region_name = normalize_german_state(state_name) or state_name

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

            # Generate list_id with state prefix (4-digit zero-padded for states)
            list_id = f"{state_code}-{str(wkr_nr).zfill(4)}"

            # Create constituency name matching existing format
            # Format: "{wkr_nr} - {name} ({term_name})"
            constituency_name = f"{wkr_nr} - {wkr_name} ({term.name})"

            # Match by list_id + parliament_term
            existing = Constituency.objects.filter(
                parliament_term=term,
                scope='STATE_DISTRICT',
                list_id=list_id
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
                        list_id=list_id,
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

    @transaction.atomic
    def _sync_constituencies_from_api(
        self,
        parliament_data: dict,
        period_data: dict,
        level: str
    ) -> dict:
        """
        Sync constituencies from Abgeordnetenwatch API for a given parliament term.

        Args:
            parliament_data: Parliament data from API (includes 'id' and 'label')
            period_data: Parliament period/term data from API (includes 'id' and 'label')
            level: 'FEDERAL', 'STATE', or 'EU'

        Returns:
            dict with stats: {'created': int, 'updated': int, 'errors': list}
        """
        parliament_id = parliament_data['id']
        parliament_name = parliament_data['label']
        parliament_term_id = period_data['id']
        period_name = period_data['label']
        from letters.services.abgeordnetenwatch_api_client import AbgeordnetenwatchAPI

        stats = {'created': 0, 'updated': 0, 'errors': []}

        # Fetch constituencies (districts)
        try:
            constituencies_data = AbgeordnetenwatchAPI.get_constituencies(parliament_term_id)
        except requests.RequestException as e:
            error_msg = f"Failed to fetch constituencies for parliament_term_id {parliament_term_id}: {e}"
            self.stdout.write(self.style.ERROR(f"  {error_msg}"))
            stats['errors'].append(error_msg)
            constituencies_data = []
        except Exception as e:
            error_msg = f"Unexpected error fetching constituencies for parliament_term_id {parliament_term_id}: {e}"
            self.stdout.write(self.style.ERROR(f"  {error_msg}"))
            stats['errors'].append(error_msg)
            constituencies_data = []

        # Fetch electoral lists
        try:
            electoral_lists_data = AbgeordnetenwatchAPI.get_electoral_lists(parliament_term_id)
        except requests.RequestException as e:
            error_msg = f"Failed to fetch electoral lists for parliament_term_id {parliament_term_id}: {e}"
            self.stdout.write(self.style.ERROR(f"  {error_msg}"))
            stats['errors'].append(error_msg)
            electoral_lists_data = []
        except Exception as e:
            error_msg = f"Unexpected error fetching electoral lists for parliament_term_id {parliament_term_id}: {e}"
            self.stdout.write(self.style.ERROR(f"  {error_msg}"))
            stats['errors'].append(error_msg)
            electoral_lists_data = []

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

            # Create or update constituency
            constituency, created = Constituency.objects.update_or_create(
                external_id=external_id,
                defaults={
                    'parliament_term': term,
                    'name': label,
                    'scope': scope,
                    'list_id': list_id,
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

            # Determine scope and list_id based on name pattern
            name_lower = name.lower()
            if level == 'FEDERAL':
                if 'bundesliste' in name_lower:
                    scope = 'FEDERAL_LIST'
                    list_id = 'BUND-DE-LIST'
                else:
                    scope = 'FEDERAL_STATE_LIST'
                    # Extract state code from name if possible (e.g., "Bayern" → "BY")
                    # For now, leave as None - will need to be enriched
                    list_id = None
            elif level == 'STATE':
                if 'regional' in name_lower or 'wahlkreis' in name_lower:
                    scope = 'STATE_REGIONAL_LIST'
                    list_id = None  # No standard format for regional lists
                else:
                    scope = 'STATE_LIST'
                    list_id = None  # Will need state code
            elif level == 'EU':
                scope = 'EU_AT_LARGE'
                list_id = 'DE'
            else:
                scope = 'OTHER'
                list_id = None

            # Create or update constituency
            constituency, created = Constituency.objects.update_or_create(
                external_id=external_id,
                defaults={
                    'parliament_term': term,
                    'name': label,
                    'scope': scope,
                    'list_id': list_id,
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

    def _handle_api_sync(self):
        """Sync constituencies from Abgeordnetenwatch API for all parliaments."""
        from letters.services.abgeordnetenwatch_api_client import AbgeordnetenwatchAPI

        self.stdout.write("Syncing constituencies from Abgeordnetenwatch API...")

        # Track overall statistics
        total_stats = {
            'parliaments_processed': 0,
            'parliaments_failed': 0,
            'total_created': 0,
            'total_updated': 0,
            'failed_parliaments': []
        }

        # Get all parliaments
        try:
            parliaments_data = AbgeordnetenwatchAPI.get_parliaments()
        except requests.RequestException as e:
            error_msg = f"Failed to fetch parliaments list: {e}"
            self.stdout.write(self.style.ERROR(error_msg))
            self.stdout.write(self.style.ERROR("Cannot proceed without parliaments list. Aborting."))
            return
        except Exception as e:
            error_msg = f"Unexpected error fetching parliaments list: {e}"
            self.stdout.write(self.style.ERROR(error_msg))
            self.stdout.write(self.style.ERROR("Cannot proceed without parliaments list. Aborting."))
            return

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

            try:
                # Get parliament periods
                try:
                    periods = AbgeordnetenwatchAPI.get_parliament_periods(parliament_id)
                except requests.RequestException as e:
                    error_msg = f"Failed to fetch periods for {parliament_name}: {e}"
                    self.stdout.write(self.style.ERROR(f"  {error_msg}"))
                    total_stats['parliaments_failed'] += 1
                    total_stats['failed_parliaments'].append((parliament_name, error_msg))
                    continue
                except Exception as e:
                    error_msg = f"Unexpected error fetching periods for {parliament_name}: {e}"
                    self.stdout.write(self.style.ERROR(f"  {error_msg}"))
                    total_stats['parliaments_failed'] += 1
                    total_stats['failed_parliaments'].append((parliament_name, error_msg))
                    continue

                if not periods:
                    self.stdout.write(f"  No periods found")
                    total_stats['parliaments_processed'] += 1
                    continue

                # Sync current period only
                current_period = periods[0]
                period_id = current_period['id']
                period_name = current_period['label']

                self.stdout.write(f"  Period: {period_name}")

                stats = self._sync_constituencies_from_api(parliament_id, period_id, level)

                if stats.get('errors'):
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Created {stats['created']}, Updated {stats['updated']} constituencies ({len(stats['errors'])} errors)"
                        )
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  Created {stats['created']}, Updated {stats['updated']} constituencies"
                        )
                    )

                total_stats['total_created'] += stats['created']
                total_stats['total_updated'] += stats['updated']
                total_stats['parliaments_processed'] += 1

            except Exception as e:
                error_msg = f"Unexpected error processing {parliament_name}: {e}"
                self.stdout.write(self.style.ERROR(f"  {error_msg}"))
                total_stats['parliaments_failed'] += 1
                total_stats['failed_parliaments'].append((parliament_name, error_msg))
                continue

        # Print summary
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("Sync Summary:")
        self.stdout.write(f"  Parliaments processed: {total_stats['parliaments_processed']}")
        self.stdout.write(f"  Parliaments failed: {total_stats['parliaments_failed']}")
        self.stdout.write(f"  Total constituencies created: {total_stats['total_created']}")
        self.stdout.write(f"  Total constituencies updated: {total_stats['total_updated']}")

        if total_stats['failed_parliaments']:
            self.stdout.write(self.style.WARNING("\nFailed parliaments:"))
            for name, error in total_stats['failed_parliaments']:
                self.stdout.write(f"  {name}: {error[:100]}")

        if total_stats['parliaments_failed'] == 0:
            self.stdout.write(self.style.SUCCESS("\nAll parliaments processed successfully!"))
        elif total_stats['parliaments_processed'] > 0:
            self.stdout.write(self.style.WARNING("\nPartial success - some parliaments failed."))
        else:
            self.stdout.write(self.style.ERROR("\nAll parliaments failed to process."))

    def _handle_enrich_from_geojson(self):
        """Handle --enrich-from-geojson flag."""
        self.stdout.write("Enriching constituencies with list_id from GeoJSON files...")
        stats = self._enrich_constituencies_from_geojson()
        self.stdout.write(
            self.style.SUCCESS(
                f"Enriched {stats['enriched']} constituencies, skipped {stats['skipped']}"
            )
        )

    @transaction.atomic
    def _enrich_constituencies_from_geojson(self) -> dict:
        """
        Enrich constituencies that were created from API with list_id values from GeoJSON files.

        Returns:
            dict with stats: {'enriched': int, 'skipped': int}
        """
        from letters.services.geocoding import WahlkreisLocator

        stats = {'enriched': 0, 'skipped': 0}

        # Get the data directory containing GeoJSON files
        geojson_path = Path(getattr(settings, "CONSTITUENCY_BOUNDARIES_PATH", "wahlkreise.geojson"))
        data_dir = geojson_path.parent

        # Load federal GeoJSON
        federal_features = []
        if geojson_path.exists():
            with open(geojson_path, 'r', encoding='utf-8') as f:
                federal_data = json.load(f)
                federal_features = federal_data.get('features', [])
            self.stdout.write(f"Loaded {len(federal_features)} federal constituencies from GeoJSON")
        else:
            self.stdout.write(self.style.WARNING(f"Federal GeoJSON not found at {geojson_path}"))

        # Load state GeoJSON files
        state_features = {}
        state_codes = ['BW', 'BY', 'BE', 'HB', 'NI', 'NW', 'ST', 'SH', 'TH']
        for state_code in state_codes:
            state_file = data_dir / f'wahlkreise_{state_code.lower()}.geojson'
            if state_file.exists():
                with open(state_file, 'r', encoding='utf-8') as f:
                    state_data = json.load(f)
                    state_features[state_code] = state_data.get('features', [])
                self.stdout.write(f"Loaded {len(state_features[state_code])} constituencies for {state_code}")

        # Enrich federal constituencies
        federal_constituencies = Constituency.objects.filter(
            scope='FEDERAL_DISTRICT',
            list_id__isnull=True
        )

        for constituency in federal_constituencies:
            wkr_nr = constituency.metadata.get('WKR_NR') if constituency.metadata else None
            if not wkr_nr:
                self.stdout.write(
                    self.style.WARNING(f"  Skipping {constituency.name}: no WKR_NR in metadata")
                )
                stats['skipped'] += 1
                continue

            # Match in federal GeoJSON
            matched = False
            for feature in federal_features:
                props = feature.get('properties', {})
                feature_wkr_nr = props.get('WKR_NR')

                if feature_wkr_nr == wkr_nr:
                    # Set list_id (3-digit zero-padded for federal)
                    constituency.list_id = str(wkr_nr).zfill(3)
                    constituency.save(update_fields=['list_id'])
                    self.stdout.write(f"  Enriched {constituency.name} with list_id={constituency.list_id}")
                    stats['enriched'] += 1
                    matched = True
                    break

            if not matched:
                self.stdout.write(
                    self.style.WARNING(f"  No GeoJSON match for {constituency.name} (WKR_NR={wkr_nr})")
                )
                stats['skipped'] += 1

        # Enrich state constituencies
        state_constituencies = Constituency.objects.filter(
            scope='STATE_DISTRICT',
            list_id__isnull=True
        )

        for constituency in state_constituencies:
            metadata = constituency.metadata or {}
            wkr_nr = metadata.get('WKR_NR')
            state_code = metadata.get('LAND_CODE')

            if not wkr_nr:
                self.stdout.write(
                    self.style.WARNING(f"  Skipping {constituency.name}: no WKR_NR in metadata")
                )
                stats['skipped'] += 1
                continue

            if not state_code:
                # Try to infer state code from parliament region
                parliament = constituency.parliament_term.parliament
                state_code = get_state_code(parliament.region)
                if not state_code:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  Skipping {constituency.name}: cannot determine state code"
                        )
                    )
                    stats['skipped'] += 1
                    continue

            # Match in state GeoJSON
            if state_code not in state_features:
                self.stdout.write(
                    self.style.WARNING(
                        f"  Skipping {constituency.name}: no GeoJSON file for {state_code}"
                    )
                )
                stats['skipped'] += 1
                continue

            matched = False
            for feature in state_features[state_code]:
                props = feature.get('properties', {})

                # Normalize properties using WahlkreisLocator
                feature_wkr_nr, _ = WahlkreisLocator._normalize_properties(props)

                if feature_wkr_nr == wkr_nr:
                    # Set list_id (state code + 4-digit number)
                    constituency.list_id = f"{state_code}-{str(wkr_nr).zfill(4)}"
                    constituency.save(update_fields=['list_id'])
                    self.stdout.write(f"  Enriched {constituency.name} with list_id={constituency.list_id}")
                    stats['enriched'] += 1
                    matched = True
                    break

            if not matched:
                self.stdout.write(
                    self.style.WARNING(
                        f"  No GeoJSON match for {constituency.name} (WKR_NR={wkr_nr}, state={state_code})"
                    )
                )
                stats['skipped'] += 1

        return stats
