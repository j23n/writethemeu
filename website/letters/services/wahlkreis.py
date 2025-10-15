# ABOUTME: Service for resolving addresses to Wahlkreis identifiers and Constituency objects.
# ABOUTME: Separates geographic Wahlkreise from parliamentary Constituencies.

from typing import Dict, List, Optional
import logging

from django.db.models import Q

from ..models import Constituency
from ..constants import normalize_german_state
from .geocoding import AddressGeocoder, WahlkreisLocator

logger = logging.getLogger('letters.services')


class WahlkreisResolver:
    """
    Resolve addresses to Wahlkreis identifiers and Constituency objects.

    Process:
    1. Geocode address → coordinates
    2. Look up Wahlkreis from GeoJSON → get federal/state Wahlkreis IDs
    3. Query Constituency objects by wahlkreis_id
    4. Add state-level list constituencies for the user's state
    """

    def __init__(self):
        self._geocoder = None
        self._wahlkreis_locator = None

    @property
    def geocoder(self):
        """Lazy-load AddressGeocoder."""
        if self._geocoder is None:
            self._geocoder = AddressGeocoder()
        return self._geocoder

    @property
    def wahlkreis_locator(self):
        """Lazy-load WahlkreisLocator."""
        if self._wahlkreis_locator is None:
            self._wahlkreis_locator = WahlkreisLocator()
        return self._wahlkreis_locator

    def resolve(
        self,
        street: Optional[str] = None,
        postal_code: Optional[str] = None,
        city: Optional[str] = None,
        country: str = 'DE'
    ) -> Dict:
        """
        Resolve address to Wahlkreis identifiers and Constituency objects.

        Returns:
            {
                'federal_wahlkreis_number': str or None,
                'state_wahlkreis_number': str or None,
                'eu_wahlkreis': str (always 'DE'),
                'constituencies': List[Constituency]
            }
        """
        result = {
            'federal_wahlkreis_number': None,
            'state_wahlkreis_number': None,
            'eu_wahlkreis': 'DE',
            'constituencies': []
        }

        if not (street and postal_code and city):
            logger.warning("Incomplete address provided to WahlkreisResolver")
            return result

        # Step 1: Geocode address
        lat, lon, success, error = self.geocoder.geocode(street, postal_code, city, country)

        if not success or lat is None or lon is None:
            logger.warning(f"Geocoding failed: {error}")
            return result

        # Step 2: Look up Wahlkreis
        wahlkreis_result = self.wahlkreis_locator.locate(lat, lon)

        if not wahlkreis_result:
            logger.warning(f"No Wahlkreis found for coordinates {lat}, {lon}")
            return result

        wkr_nr, wkr_name, land_name = wahlkreis_result

        # Normalize to 3-digit string
        federal_wahlkreis_number = str(wkr_nr).zfill(3)
        result['federal_wahlkreis_number'] = federal_wahlkreis_number

        # For state, we use the same number for now (TODO: get actual state Wahlkreis)
        result['state_wahlkreis_number'] = federal_wahlkreis_number

        normalized_state = normalize_german_state(land_name)

        # Step 3: Find constituencies by wahlkreis_id
        constituencies = list(
            Constituency.objects.filter(
                wahlkreis_id=federal_wahlkreis_number,
                scope='FEDERAL_DISTRICT'
            )
        )

        # Step 4: Add state-level list constituencies
        if normalized_state:
            state_constituencies = Constituency.objects.filter(
                scope='STATE_LIST',
                metadata__state=normalized_state
            )
            constituencies.extend(state_constituencies)

        result['constituencies'] = constituencies

        logger.info(
            f"Resolved {street}, {postal_code} {city} to "
            f"Wahlkreis {federal_wahlkreis_number} with {len(constituencies)} constituencies"
        )

        return result
