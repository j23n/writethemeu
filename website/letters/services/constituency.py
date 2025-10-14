# ABOUTME: Services for locating constituencies and suggesting representatives based on addresses.
# ABOUTME: Combines geocoding, Wahlkreis mapping, and PLZ fallback for robust constituency resolution.

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from django.db.models import Q

from ..constants import normalize_german_state
from ..models import Constituency, Parliament, ParliamentTerm, Representative
from .geocoding import AddressGeocoder, WahlkreisLocator

logger = logging.getLogger('letters.services')


@dataclass
class LocatedConstituencies:
    federal: Optional[Constituency]
    state: Optional[Constituency]
    local: Optional[Constituency]


@dataclass
class LocationContext:
    postal_code: Optional[str]
    state: Optional[str]
    constituencies: List[Constituency]
    street: Optional[str] = None
    city: Optional[str] = None
    country: str = 'DE'

    @property
    def has_constituencies(self) -> bool:
        return bool(self.constituencies)

    def parliament_ids(self) -> Set[int]:
        ids: Set[int] = set()
        for constituency in self.constituencies:
            if constituency.parliament_term_id:
                ids.add(constituency.parliament_term.parliament_id)
        return ids

    def filtered_constituencies(self, parliament_ids: Optional[Set[int]]) -> List[Constituency]:
        if parliament_ids:
            matches = [
                constituency
                for constituency in self.constituencies
                if constituency.parliament_term.parliament_id in parliament_ids
            ]
            if matches:
                return matches

        if self.state:
            state_matches = [
                constituency
                for constituency in self.constituencies
                if normalize_german_state((constituency.metadata or {}).get('state')) == self.state
            ]
            if state_matches:
                return state_matches
            return []
        return list(self.constituencies)


class ConstituencyLocator:
    """
    Locate representatives by address or postal code.

    Features:
    - Address-based lookup: Uses AddressGeocoder + WahlkreisLocator for accurate constituency matching
    - PLZ-based fallback: Falls back to PLZ-prefix matching when geocoding fails
    - Backward compatible: Still accepts PLZ-only queries
    """

    # Rough PLZ -> state mapping (first two digits) for fallback
    STATE_BY_PLZ_PREFIX: Dict[str, str] = {
        **{prefix: 'Berlin' for prefix in ['10', '11']},
        **{prefix: 'Bayern' for prefix in ['80', '81', '82', '83', '84', '85', '86', '87', '88', '89', '90', '91']} ,
        **{prefix: 'Baden-Württemberg' for prefix in ['70', '71', '72', '73', '74', '75', '76', '77', '78', '79']},
        **{prefix: 'Nordrhein-Westfalen' for prefix in ['40', '41', '42', '43', '44', '45', '46', '47', '48', '49', '50', '51', '52', '53', '57']},
        **{prefix: 'Hessen' for prefix in ['34', '35', '36', '60', '61', '62', '63', '64', '65']},
        **{prefix: 'Niedersachsen' for prefix in ['26', '27', '28', '29', '30', '31', '32', '33', '37', '38', '49']},
    }

    def __init__(self):
        """Initialize geocoder and wahlkreis locator services."""
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

    def locate(
        self,
        street: Optional[str] = None,
        postal_code: Optional[str] = None,
        city: Optional[str] = None,
        country: str = 'DE'
    ) -> List[Representative]:
        """
        Locate representatives by address or postal code.

        Args:
            street: Street name and number (optional)
            postal_code: Postal code / PLZ (optional)
            city: City name (optional)
            country: Country code (default: 'DE')

        Returns:
            List of Representative objects for the located constituency

        Strategy:
        1. If full address provided (street + postal_code + city):
           - Geocode address to coordinates
           - Use WahlkreisLocator to find constituency
           - Return Representatives for that constituency
        2. Fallback to PLZ-prefix matching if:
           - No street provided
           - Geocoding fails
           - WahlkreisLocator returns no result
        """
        street = (street or '').strip()
        postal_code = (postal_code or '').strip()
        city = (city or '').strip()

        # Try full address-based lookup if we have all components
        if street and postal_code and city:
            try:
                lat, lon, success, error = self.geocoder.geocode(street, postal_code, city, country)

                if success and lat is not None and lon is not None:
                    # Find constituency using coordinates
                    result = self.wahlkreis_locator.locate(lat, lon)

                    if result:
                        wkr_nr, wkr_name, land_name = result
                        logger.info(
                            "Address geocoded to constituency: %s (WK %s, %s)",
                            wkr_name, wkr_nr, land_name
                        )

                        # Find Representatives for this Wahlkreis
                        representatives = self._find_representatives_by_wahlkreis(
                            wkr_nr, wkr_name, land_name
                        )

                        if representatives:
                            return representatives

                        # If no representatives found for direct constituency,
                        # fall through to PLZ-based lookup
                        logger.warning(
                            "No representatives found for WK %s, falling back to PLZ",
                            wkr_nr
                        )
                else:
                    logger.debug(
                        "Geocoding failed for %s, %s %s: %s",
                        street, postal_code, city, error
                    )
            except Exception as e:
                logger.warning(
                    "Error during address-based lookup for %s, %s %s: %s",
                    street, postal_code, city, e
                )

        # Fallback to PLZ-based lookup
        if postal_code:
            return self._locate_by_plz(postal_code)

        # No parameters provided
        return []

    def _find_representatives_by_wahlkreis(
        self,
        wkr_nr: int,
        wkr_name: str,
        land_name: str
    ) -> List[Representative]:
        """
        Find representatives for a given Wahlkreis.

        Strategy:
        1. Look for constituencies with matching WKR_NR in metadata
        2. Look for constituencies with matching name
        3. Return active representatives from matched constituencies
        """
        # Try to find constituency by WKR_NR in metadata
        constituencies = Constituency.objects.filter(
            metadata__WKR_NR=wkr_nr,
            scope='FEDERAL_DISTRICT'
        ).prefetch_related('representatives')

        if not constituencies.exists():
            # Try by name matching
            constituencies = Constituency.objects.filter(
                name__icontains=str(wkr_nr),
                scope='FEDERAL_DISTRICT'
            ).prefetch_related('representatives')

        if not constituencies.exists():
            # Try finding by state and scope
            normalized_state = normalize_german_state(land_name)
            if normalized_state:
                constituencies = Constituency.objects.filter(
                    metadata__state=normalized_state,
                    scope__in=['FEDERAL_DISTRICT', 'FEDERAL_STATE_LIST']
                ).prefetch_related('representatives')

        # Collect all representatives from matched constituencies
        representatives = []
        for constituency in constituencies:
            reps = list(constituency.representatives.filter(is_active=True))
            representatives.extend(reps)

        # Remove duplicates while preserving order
        seen = set()
        unique_reps = []
        for rep in representatives:
            if rep.id not in seen:
                seen.add(rep.id)
                unique_reps.append(rep)

        return unique_reps

    def _locate_by_plz(self, postal_code: str) -> List[Representative]:
        """
        Fallback: Locate representatives using PLZ-prefix matching.

        Returns list of Representatives instead of LocatedConstituencies.
        """
        if len(postal_code) < 2:
            return []

        prefix = postal_code[:2]
        state_name = self.STATE_BY_PLZ_PREFIX.get(prefix)
        normalized_state = normalize_german_state(state_name) if state_name else None

        federal = self._match_federal(normalized_state)
        state = self._match_state(normalized_state)

        # Convert constituencies to representatives
        representatives = []
        for constituency in [federal, state]:
            if constituency:
                reps = list(constituency.representatives.filter(is_active=True))
                representatives.extend(reps)

        # Remove duplicates
        seen = set()
        unique_reps = []
        for rep in representatives:
            if rep.id not in seen:
                seen.add(rep.id)
                unique_reps.append(rep)

        return unique_reps

    @classmethod
    def locate_legacy(cls, postal_code: str) -> LocatedConstituencies:
        """
        Legacy method: Returns LocatedConstituencies for backward compatibility.

        This method maintains the old API for existing code that expects
        LocatedConstituencies instead of List[Representative].
        """
        postal_code = (postal_code or '').strip()
        if len(postal_code) < 2:
            return LocatedConstituencies(None, None, None)

        prefix = postal_code[:2]
        state_name = cls.STATE_BY_PLZ_PREFIX.get(prefix)
        normalized_state = normalize_german_state(state_name) if state_name else None

        federal = cls._match_federal(normalized_state)
        state = cls._match_state(normalized_state)
        local = None  # FIXME: requires finer-grained datasets

        return LocatedConstituencies(federal=federal, state=state, local=local)

    # ------------------------------------------------------------------
    @staticmethod
    def _match_federal(normalized_state: Optional[str]) -> Optional[Constituency]:
        term = ParliamentTerm.objects.filter(parliament__level='FEDERAL').order_by('-start_date').first()
        if not term:
            return None

        if normalized_state:
            constituency = Constituency.objects.filter(
                parliament_term=term,
                scope='FEDERAL_STATE_LIST',
                metadata__state=normalized_state
            ).first()
            if constituency:
                return constituency

        return Constituency.objects.filter(parliament_term=term, scope='FEDERAL_LIST').first()

    # ------------------------------------------------------------------
    @staticmethod
    def _match_state(normalized_state: Optional[str]) -> Optional[Constituency]:
        if not normalized_state:
            return None
        parliament = Parliament.objects.filter(level='STATE', name__icontains=normalized_state).first()
        if not parliament:
            return None
        term = parliament.terms.order_by('-start_date').first()
        if not term:
            return None
        return Constituency.objects.filter(parliament_term=term, scope='STATE_LIST').first()
