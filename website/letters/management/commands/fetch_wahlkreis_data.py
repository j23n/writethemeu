import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# Official Bundeswahlleiterin Shapefile URL (2025 election)
DEFAULT_WAHLKREIS_URL = (
    "https://www.bundeswahlleiterin.de/dam/jcr/a3b60aa9-8fa5-4223-9fb4-0a3a3cebd7d1/"
    "btw25_geometrie_wahlkreise_vg250_shp_geo.zip"
)


class Command(BaseCommand):
    """Download and convert Wahlkreis geodata for constituency lookups."""

    help = (
        "Fetch Bundestag constituency (Wahlkreis) boundary data from bundeswahlleiterin.de, "
        "convert from Shapefile to GeoJSON if needed, and store for shapely-based lookup. "
        "The GeoJSON file is cached locally and Shapefile components are not kept."
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

        if output_path.exists() and not force:
            raise CommandError(
                f"Output file {output_path} already exists. Use --force to overwrite."
            )

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
