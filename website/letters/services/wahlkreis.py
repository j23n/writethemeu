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
        address: str,
        country: str = 'DE'
    ) -> Dict:
        """
        Resolve address to Wahlkreis identifiers and Constituency objects.

        Args:
            address: Full address string (e.g., "Unter den Linden 1, 10117 Berlin")
            country: Country code (default: 'DE')

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

        address = (address or '').strip()
        if not address:
            logger.warning("Empty address provided to WahlkreisResolver")
            return result

        # Step 1: Geocode address
        lat, lon, success, error = self.geocoder.geocode(address, country)

        if not success or lat is None or lon is None:
            logger.warning(f"Geocoding failed: {error}")
            return result

        # Step 2: Look up Wahlkreise (federal and state)
        wahlkreis_result = self.wahlkreis_locator.locate(lat, lon)

        if not wahlkreis_result:
            logger.warning(f"No Wahlkreis found for coordinates {lat}, {lon}")
            return result

        federal_data = wahlkreis_result.get('federal')
        state_data = wahlkreis_result.get('state')

        if not federal_data:
            logger.warning(f"No federal Wahlkreis found for coordinates {lat}, {lon}")
            return result

        # Extract federal Wahlkreis data
        federal_wkr_nr = federal_data['wkr_nr']
        federal_wahlkreis_number = str(federal_wkr_nr).zfill(3)
        land_name = federal_data['land_name']
        normalized_state = normalize_german_state(land_name)

        result['federal_wahlkreis_number'] = federal_wahlkreis_number

        # Extract state Wahlkreis data if available
        if state_data:
            state_wkr_nr = state_data['wkr_nr']
            state_wahlkreis_number = str(state_wkr_nr).zfill(3)
            result['state_wahlkreis_number'] = state_wahlkreis_number

        # Step 3: Find constituencies by wahlkreis_id
        constituencies = []

        # Add federal district constituency
        federal_constituencies = list(
            Constituency.objects.filter(
                wahlkreis_id=federal_wahlkreis_number,
                scope='FEDERAL_DISTRICT'
            )
        )
        constituencies.extend(federal_constituencies)

        # Add state district constituency if we have state Wahlkreis data
        if state_data:
            state_wahlkreis_number = result['state_wahlkreis_number']
            state_district_constituencies = list(
                Constituency.objects.filter(
                    wahlkreis_id=state_wahlkreis_number,
                    scope='STATE_DISTRICT'
                )
            )
            constituencies.extend(state_district_constituencies)

        # Add state list constituency
        if normalized_state:
            state_list_constituencies = Constituency.objects.filter(
                scope='STATE_LIST',
                metadata__state=normalized_state
            )
            constituencies.extend(state_list_constituencies)

        result['constituencies'] = constituencies

        logger.info(
            f"Resolved {address} to "
            f"Federal WK {federal_wahlkreis_number}, State WK {result['state_wahlkreis_number']}, "
            f"with {len(constituencies)} constituencies"
        )

        return result
