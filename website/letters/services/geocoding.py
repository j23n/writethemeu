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
        street: str,
        postal_code: str,
        city: str,
        country: str = 'DE'
    ) -> Tuple[Optional[float], Optional[float], bool, Optional[str]]:
        """
        Geocode a German address to latitude/longitude coordinates.

        Args:
            street: Street name and number
            postal_code: Postal code (PLZ)
            city: City name
            country: Country code (default: 'DE')

        Returns:
            Tuple of (latitude, longitude, success, error_message)
            - On success: (lat, lon, True, None)
            - On failure: (None, None, False, error_message)
        """
        # Normalize inputs
        street = (street or '').strip()
        postal_code = (postal_code or '').strip()
        city = (city or '').strip()
        country = (country or 'DE').upper()

        # Generate cache key
        address_hash = self._generate_cache_key(street, postal_code, city, country)

        # Check cache first
        cached = self._get_from_cache(address_hash)
        if cached is not None:
            return cached

        # Make API request with rate limiting
        try:
            self._apply_rate_limit()
            result = self._query_nominatim(street, postal_code, city, country)

            if result:
                lat, lon = result
                self._store_in_cache(
                    address_hash, street, postal_code, city, country,
                    lat, lon, success=True, error_message=None
                )
                return lat, lon, True, None
            else:
                error_msg = 'Address not found'
                self._store_in_cache(
                    address_hash, street, postal_code, city, country,
                    None, None, success=False, error_message=error_msg
                )
                return None, None, False, error_msg

        except Exception as e:
            error_msg = f'Geocoding API error: {str(e)}'
            logger.warning('Geocoding failed for %s, %s %s: %s', street, postal_code, city, error_msg)

            # Cache the failure to avoid repeated attempts
            self._store_in_cache(
                address_hash, street, postal_code, city, country,
                None, None, success=False, error_message=error_msg
            )
            return None, None, False, error_msg

    def _generate_cache_key(
        self,
        street: str,
        postal_code: str,
        city: str,
        country: str
    ) -> str:
        """Generate SHA256 hash of normalized address for cache lookup."""
        # Normalize address components for consistent hashing
        normalized = f"{street}|{postal_code}|{city}|{country}"
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
        street: str,
        postal_code: str,
        city: str,
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
                'street': street,
                'postal_code': postal_code,
                'city': city,
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
        street: str,
        postal_code: str,
        city: str,
        country: str
    ) -> Optional[Tuple[float, float]]:
        """
        Query Nominatim API for address coordinates.

        Returns:
            (latitude, longitude) on success, None if not found

        Raises:
            requests.RequestException on API errors
        """
        # Build query string
        query_parts = []
        if street:
            query_parts.append(street)
        if postal_code:
            query_parts.append(postal_code)
        if city:
            query_parts.append(city)

        query = ', '.join(query_parts)

        params = {
            'q': query,
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
