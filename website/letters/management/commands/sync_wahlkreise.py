# ABOUTME: Management command to download Wahlkreis geodata and sync all constituencies to database.
# ABOUTME: Ensures all 299 Bundestag constituencies exist independent of representative assignments.

import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from letters.models import Parliament, ParliamentTerm, Constituency

# Official Bundeswahlleiterin Shapefile URL (2025 election)
DEFAULT_WAHLKREIS_URL = (
    "https://www.bundeswahlleiterin.de/dam/jcr/a3b60aa9-8fa5-4223-9fb4-0a3a3cebd7d1/"
    "btw25_geometrie_wahlkreise_vg250_shp_geo.zip"
)


class Command(BaseCommand):
    """Download Wahlkreis geodata and sync all constituencies to database."""

    help = (
        "Fetch Bundestag constituency (Wahlkreis) boundary data from bundeswahlleiterin.de, "
        "convert from Shapefile to GeoJSON if needed, store for shapely-based lookup, "
        "and populate all 299 constituencies in the database. "
        "This ensures constituencies exist independent of whether they have representatives."
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

    def handle(self, *args, **options):
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
        try:
            import shapefile  # pyshp library
        except ImportError:
            raise CommandError(
                "pyshp library is required to convert Shapefiles. "
                "Install with: pip install pyshp"
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
                    (name for name in archive.namelist() if name.lower().endswith(".geojson")),
                    None,
                )
                if target_name is None:
                    raise CommandError(
                        "ZIP archive does not contain a *.geojson file. Use --zip-member to specify a file."
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

            # Create constituency name matching the format used by sync_representatives
            constituency_name = f"{wkr_nr} - {wkr_name} (Bundestag 2025 - 2029)"

            constituency, created = Constituency.objects.update_or_create(
                external_id=str(wkr_nr),
                defaults={
                    'parliament_term': term,
                    'name': constituency_name,
                    'scope': 'FEDERAL_DISTRICT',
                    'metadata': {
                        'WKR_NR': wkr_nr,
                        'WKR_NAME': wkr_name,
                        'LAND_NAME': land_name,
                        'state': land_name,
                        'source': 'wahlkreise_geojson'
                    }
                }
            )

            constituency.last_synced_at = timezone.now()
            constituency.save(update_fields=['last_synced_at'])

            if created:
                stats['created'] += 1
            else:
                stats['updated'] += 1

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
