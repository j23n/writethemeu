import io
import json
import zipfile
from pathlib import Path
from typing import Optional

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

DEFAULT_WAHLKREIS_URL = (
    "https://raw.githubusercontent.com/dknx01/wahlkreissuche/main/data/wahlkreise.geojson"
)


class Command(BaseCommand):
    """Download and store Wahlkreis geodata for constituency lookups."""

    help = (
        "Fetch Bundestag constituency (Wahlkreis) boundary data and store it as GeoJSON "
        "for shapely-based lookup."
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

        if url.lower().endswith(".zip") or "zip" in content_type:
            geojson_bytes = self._extract_from_zip(data_bytes, zip_member)
        else:
            geojson_bytes = data_bytes

        try:
            geojson_text = geojson_bytes.decode("utf-8")
            json.loads(geojson_text)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CommandError("Downloaded data is not valid UTF-8 GeoJSON") from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(geojson_text, encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Saved Wahlkreis data to {output_path}"))

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
