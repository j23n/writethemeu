# ABOUTME: Geocoding services for converting addresses to coordinates and Wahlkreise.
# ABOUTME: Uses OSM Nominatim for geocoding and GeoJSON boundary data for constituency mapping.

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Optional, Tuple

import requests
from django.conf import settings

from ..models import GeocodeCache

logger = logging.getLogger('letters.services')


class AddressGeocoder:
    """
    Geocode German addresses using OpenStreetMap Nominatim API.

    Features:
    - Caches results using GeocodeCache model
    - Rate limits to 1 request/second for public API compliance
    - Handles errors gracefully
    - Caches both successful and failed lookups to avoid repeated failures
    """

    NOMINATIM_ENDPOINT = 'https://nominatim.openstreetmap.org/search'
    USER_AGENT = 'WriteThem.eu/0.1 (civic engagement platform)'
    RATE_LIMIT_SECONDS = 1.0

    def __init__(self):
        self._last_request_time = 0

    def geocode(
        self,
        address: str,
        country: str = 'DE'
    ) -> Tuple[Optional[float], Optional[float], bool, Optional[str]]:
        """
        Geocode a German address to latitude/longitude coordinates.

        Args:
            address: Full address string (e.g., "Unter den Linden 1, 10117 Berlin")
            country: Country code (default: 'DE')

        Returns:
            Tuple of (latitude, longitude, success, error_message)
            - On success: (lat, lon, True, None)
            - On failure: (None, None, False, error_message)
        """
        address = (address or '').strip()
        country = (country or 'DE').upper()

        if not address:
            return None, None, False, 'Address is required'

        address_hash = self._generate_cache_key(address, country)

        cached = self._get_from_cache(address_hash)
        if cached is not None:
            return cached

        try:
            self._apply_rate_limit()
            result = self._query_nominatim(address, country)

            if result:
                lat, lon = result
                self._store_in_cache(
                    address_hash, address, country,
                    lat, lon, success=True, error_message=None
                )
                return lat, lon, True, None
            else:
                error_msg = 'Address not found'
                self._store_in_cache(
                    address_hash, address, country,
                    None, None, success=False, error_message=error_msg
                )
                return None, None, False, error_msg

        except Exception as e:
            error_msg = f'Geocoding API error: {str(e)}'
            logger.warning('Geocoding failed for %s: %s', address, error_msg)

            self._store_in_cache(
                address_hash, address, country,
                None, None, success=False, error_message=error_msg
            )
            return None, None, False, error_msg

    def _generate_cache_key(
        self,
        address: str,
        country: str
    ) -> str:
        """Generate SHA256 hash of normalized address for cache lookup."""
        normalized = f"{address}|{country}"
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def _get_from_cache(
        self,
        address_hash: str
    ) -> Optional[Tuple[Optional[float], Optional[float], bool, Optional[str]]]:
        """Check cache for existing geocoding result."""
        try:
            cache_entry = GeocodeCache.objects.get(address_hash=address_hash)
            if cache_entry.success:
                return cache_entry.latitude, cache_entry.longitude, True, None
            else:
                return None, None, False, cache_entry.error_message
        except GeocodeCache.DoesNotExist:
            return None

    def _store_in_cache(
        self,
        address_hash: str,
        address: str,
        country: str,
        latitude: Optional[float],
        longitude: Optional[float],
        success: bool,
        error_message: Optional[str]
    ) -> None:
        """Store geocoding result in cache."""
        GeocodeCache.objects.update_or_create(
            address_hash=address_hash,
            defaults={
                'street': '',
                'postal_code': '',
                'city': address,
                'country': country,
                'latitude': latitude,
                'longitude': longitude,
                'success': success,
                'error_message': error_message or '',
            }
        )

    def _apply_rate_limit(self) -> None:
        """Ensure we don't exceed 1 request per second."""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < self.RATE_LIMIT_SECONDS:
            sleep_time = self.RATE_LIMIT_SECONDS - time_since_last
            time.sleep(sleep_time)

        self._last_request_time = time.time()

    def _query_nominatim(
        self,
        address: str,
        country: str
    ) -> Optional[Tuple[float, float]]:
        """
        Query Nominatim API for address coordinates.

        Returns:
            (latitude, longitude) on success, None if not found

        Raises:
            requests.RequestException on API errors
        """
        params = {
            'q': address,
            'format': 'json',
            'addressdetails': 1,
            'limit': 1,
            'countrycodes': country.lower(),
        }

        headers = {
            'User-Agent': self.USER_AGENT
        }

        response = requests.get(
            self.NOMINATIM_ENDPOINT,
            params=params,
            headers=headers,
            timeout=10
        )
        response.raise_for_status()

        results = response.json()

        if results and len(results) > 0:
            result = results[0]
            lat = float(result['lat'])
            lon = float(result['lon'])
            return lat, lon

        return None


class WahlkreisLocator:
    """Locate which Wahlkreis (constituency) a coordinate falls within using Shapely."""

    # Class-level cache for parsed constituencies
    _cached_constituencies = None
    _cached_state_constituencies = None
    _cached_path = None

    # CRS mapping for state GeoJSON files
    # Most states use UTM zones, Bayern uses DHDN Gauss-Kruger
    STATE_CRS = {
        'BE': 'EPSG:25833',  # UTM Zone 33N (Berlin is on zone boundary, uses 33N)
        'BW': 'EPSG:25832',  # UTM Zone 32N
        'BY': 'EPSG:31468',  # DHDN Gauss-Kruger Zone 4
        'HB': 'EPSG:25832',  # UTM Zone 32N
        'NI': 'EPSG:25832',  # UTM Zone 32N
        'NW': 'EPSG:25832',  # UTM Zone 32N
        'SH': 'EPSG:4326',   # WGS84 (no transformation needed)
        'ST': 'EPSG:25833',  # UTM Zone 33N
        'TH': 'EPSG:25833',  # UTM Zone 33N
    }

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

                    # Normalize properties to handle different field names
                    wkr_nr, wkr_name = self._normalize_properties(properties)

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

    def _normalize_properties(self, props: dict) -> tuple:
        """
        Normalize GeoJSON properties to extract WKR_NR and WKR_NAME.

        Handles different field names across various state GeoJSON sources.
        Returns (wkr_nr, wkr_name) tuple.
        """
        import re

        # Normalize WKR_NR from various possible field names
        wkr_nr = props.get("WKR_NR")
        if wkr_nr is None:
            wkr_nr = (
                props.get("Nummer") or         # BW
                props.get("nummer") or
                props.get("SKR_NR") or         # BY (Bayern)
                props.get("AWK") or            # BE (Berlin)
                props.get("wbz") or            # HB (Bremen)
                props.get("WKNum") or          # NI (Niedersachsen)
                props.get("LWKNR") or          # NW (Nordrhein-Westfalen)
                props.get("WK_Nr_21") or       # ST (Sachsen-Anhalt)
                props.get("wahlkreis_nr") or   # SH (Schleswig-Holstein)
                props.get("WK_ID") or          # TH (Thüringen)
                props.get("WK_NR") or
                props.get("WahlkreisNr") or
                props.get("STIMMKREIS") or
                props.get("Nr")
            )

        # Convert to int if string
        if isinstance(wkr_nr, str):
            try:
                wkr_nr = int(wkr_nr)
            except ValueError:
                pass

        # Normalize WKR_NAME from various possible field names
        wkr_name = props.get("WKR_NAME")
        if wkr_name is None:
            wkr_name = (
                props.get("WK Name") or        # BW
                props.get("SKR_NAME") or       # BY (Bayern)
                props.get("AWK") or            # BE (Berlin, uses AWK for both)
                props.get("BEZ_GEM") or        # HB (Bremen)
                props.get("WKName") or         # NI (Niedersachsen)
                props.get("Name") or           # NW (Nordrhein-Westfalen)
                props.get("WK_Name_21") or     # ST (Sachsen-Anhalt)
                props.get("wahlkreis_name") or # SH (Schleswig-Holstein)
                props.get("WK") or             # TH (Thüringen)
                props.get("name") or
                props.get("Wahlkreis") or
                props.get("wahlkreis") or
                props.get("WK_NAME") or
                props.get("WahlkreisName") or
                props.get("STIMMKREISNAME")
            )

        # Strip HTML tags (e.g., <br>) from names
        if isinstance(wkr_name, str):
            wkr_name = re.sub(r'<[^>]+>', '', wkr_name)

        return wkr_nr, wkr_name or ''

    def _locate_detailed(self, latitude, longitude):
        """
        Find both federal and state constituencies for given coordinates.

        Args:
            latitude: WGS84 latitude
            longitude: WGS84 longitude

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
        from pyproj import Transformer

        # Federal constituencies use WGS84 (no transformation needed)
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
                # Get the CRS for this state
                state_crs = self.STATE_CRS.get(land_code, 'EPSG:4326')

                # Transform coordinates if needed
                if state_crs != 'EPSG:4326':
                    # Transform from WGS84 to state CRS
                    transformer = Transformer.from_crs('EPSG:4326', state_crs, always_xy=True)
                    x, y = transformer.transform(longitude, latitude)
                    state_point = Point(x, y)
                else:
                    # No transformation needed for WGS84
                    state_point = point

                # Check state constituencies with transformed coordinates
                for wkr_nr, wkr_name, state_land_code, land_name, geometry in self.state_constituencies[land_code]:
                    if geometry.contains(state_point):
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

    def locate(self, latitude, longitude):
        """
        Find federal and state constituencies for given coordinates.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate

        Returns:
            dict with 'federal' and 'state' keys, each containing:
            {
                'wkr_nr': int,
                'wkr_name': str,
                'land_name': str,
                'land_code': str
            }
            or None if no federal constituency found.
        """
        result = self._locate_detailed(latitude, longitude)

        if result and result['federal']:
            return result

        return None
