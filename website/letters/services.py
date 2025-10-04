"""
Services for the letters application - REAL IMPLEMENTATION

This module contains business logic for:
- Address to constituency mapping (with geocoding)
- Identity verification
- Representative data syncing (Abgeordnetenwatch API)
"""

import logging
import re
import time
from datetime import datetime, date
from typing import Any, Dict, List, Optional

import requests
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from django.utils.translation import gettext as _
from geopy.geocoders import Nominatim

from .constants import GERMAN_STATE_ALIASES, normalize_german_state
from .geo import BoundaryRepository
from .models import Constituency, Representative, TopicArea, Committee, CommitteeMembership

logger = logging.getLogger(__name__)


class AbgeordnetenwatchAPI:
    """
    Client for Abgeordnetenwatch.de API v2

    API Documentation: https://www.abgeordnetenwatch.de/api
    License: CC0 1.0 (Public Domain)
    """

    BASE_URL = "https://www.abgeordnetenwatch.de/api/v2"

    @classmethod
    def fetch_paginated(cls, endpoint: str, params: Dict = None) -> List[Dict]:
        """
        Fetch all pages of a paginated endpoint.

        Args:
            endpoint: API endpoint (e.g., 'politicians', 'candidacies-mandates')
            params: Query parameters

        Returns:
            List of all results across all pages
        """
        all_results = []
        page = 0
        params = params or {}
        params['pager_limit'] = 100  # Max per page

        while True:
            params['page'] = page
            url = f"{cls.BASE_URL}/{endpoint}"

            try:
                logger.debug(f"API Request: GET {url} with params: {params}")
                response = requests.get(url, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()

                # Log response preview
                if logger.isEnabledFor(logging.DEBUG):
                    import json
                    json_str = json.dumps(data, indent=2)
                    preview = json_str[:500] + "..." if len(json_str) > 500 else json_str
                    logger.debug(f"API Response preview: {preview}")

                results = data.get('data', [])
                if not results:
                    logger.debug(f"No more results for {endpoint} at page {page}")
                    break

                all_results.extend(results)

                # Check pagination
                meta = data.get('meta', {})
                result_meta = meta.get('result', {})
                total = result_meta.get('total', 0)
                count = len(all_results)

                logger.info(f"Fetched {len(results)} items from {endpoint} (page {page}, total so far: {count}/{total})")

                # Check if there are more pages
                if count >= total:
                    logger.debug(f"Fetched all items for {endpoint}")
                    break

                page += 1

            except requests.RequestException as e:
                logger.error(f"API request error for {endpoint}: {e}")
                break

        logger.info(f"Total fetched from {endpoint}: {len(all_results)} items")
        return all_results

    @classmethod
    def get_parliaments(cls) -> List[Dict]:
        """Fetch all parliaments"""
        return cls.fetch_paginated('parliaments')

    @classmethod
    def get_parliament_periods(cls, parliament_id: int = None) -> List[Dict]:
        """Fetch parliament periods, optionally filtered by parliament"""
        params = {}
        if parliament_id:
            params['parliament'] = parliament_id
        return cls.fetch_paginated('parliament-periods', params)

    @classmethod
    def get_politicians(cls, parliament_period_id: int = None) -> List[Dict]:
        """Fetch politicians, optionally filtered by parliament period"""
        params = {}
        if parliament_period_id:
            params['parliament_period'] = parliament_period_id
        return cls.fetch_paginated('politicians', params)

    @classmethod
    def get_candidacies_mandates(cls, parliament_period_id: int = None) -> List[Dict]:
        """
        Fetch candidacies and mandates.
        This provides the link between politicians and their constituencies.
        """
        params = {}
        if parliament_period_id:
            params['parliament_period'] = parliament_period_id
        return cls.fetch_paginated('candidacies-mandates', params)


class AddressConstituencyMapper:
    """
    Maps German addresses to electoral constituencies using geocoding.

    This service uses Nominatim (OpenStreetMap) for geocoding and matches
    addresses to constituencies based on administrative boundaries.

    Note: For precise Wahlkreis matching, consider integrating shapefiles
    from bundeswahlleiterin.de with PostGIS.
    """

    POSTAL_CODE_SANITIZER = re.compile(r"[^0-9]")

    _boundary_index_cache = None

    @classmethod
    def geocode_address(cls, street_address: str, postal_code: str, city: str) -> Optional[Dict[str, Any]]:
        """
        Geocode a German address using Nominatim.

        Returns:
            Dictionary with lat, lon, and administrative info, or None if geocoding fails
        """
        try:
            geolocator = Nominatim(user_agent="writethem_eu")
            components: List[str] = []
            if street_address:
                components.append(street_address)
            location_line = " ".join(
                filter(
                    None,
                    [postal_code.strip() if postal_code else None, city.strip() if city else None]
                )
            )
            if location_line:
                components.append(location_line)
            components.append("Germany")
            full_address = ", ".join(components)

            location = geolocator.geocode(full_address, addressdetails=True)

            if location:
                return {
                    'latitude': location.latitude,
                    'longitude': location.longitude,
                    'raw': location.raw,
                    'address': location.raw.get('address', {})
                }
            return None
        except Exception as e:
            logger.error(f"Geocoding error for {full_address}: {e}")
            return None

    @classmethod
    def _get_boundary_index(cls):
        boundary_path = getattr(settings, 'CONSTITUENCY_BOUNDARIES_PATH', None)
        if not boundary_path:
            return None
        if cls._boundary_index_cache is None:
            cls._boundary_index_cache = BoundaryRepository.get_index(boundary_path)
        return cls._boundary_index_cache

    @classmethod
    def _match_federal_constituency_from_geo(cls, geo_data: Optional[Dict[str, Any]]) -> Optional[Constituency]:
        if not geo_data:
            return None

        latitude = geo_data.get('latitude')
        longitude = geo_data.get('longitude')
        if latitude is None or longitude is None:
            return None

        index = cls._get_boundary_index()
        if not index:
            return None

        properties = index.lookup(latitude, longitude)
        if not properties:
            return None

        return cls._lookup_constituency_from_properties(properties)

    @classmethod
    def _lookup_constituency_from_properties(cls, properties: Dict[str, Any]) -> Optional[Constituency]:
        wahlkreis_number = properties.get('wahlkreis_number') or properties.get('WKR_NR') or properties.get('wk_nr')
        if wahlkreis_number is None:
            return None

        number_raw = str(wahlkreis_number).strip()
        candidates = {number_raw}
        if number_raw.isdigit():
            normalized = str(int(number_raw))
            candidates.add(normalized)
            candidates.add(normalized.zfill(3))

        conditions = [Q(metadata__wahlkreis_number=candidate) for candidate in candidates]
        if not conditions:
            return None

        query = conditions[0]
        for condition in conditions[1:]:
            query |= condition

        return Constituency.objects.filter(level='FEDERAL').filter(query).first()

    @classmethod
    def normalize_state_name(cls, state: str) -> Optional[str]:
        """Normalize state name to canonical form"""
        return normalize_german_state(state)

    @classmethod
    def map_address_to_constituency(
        cls,
        street_address: str,
        postal_code: str,
        city: str,
        state: str
    ) -> Optional[Constituency]:
        """
        Map a German address to its constituency using geocoding.

        Args:
            street_address: Street name and number
            postal_code: German postal code (PLZ)
            city: City name
            state: German state (Bundesland)

        Returns:
            Constituency object if found, None otherwise
        """
        # Geocode the address
        geo_data = cls.geocode_address(street_address, postal_code, city)

        # Try precise match using boundary polygons (federal Wahlkreise)
        federal_constituency = cls._match_federal_constituency_from_geo(geo_data)
        if federal_constituency:
            return federal_constituency

        # Normalize state name
        normalized_state = cls.normalize_state_name(
            state or cls._extract_address_component(geo_data, ['state', 'state_district'])
        )
        normalized_city = cls._normalize_city(
            city or cls._extract_address_component(geo_data, ['city', 'town', 'village', 'municipality'])
        )
        sanitized_postal = cls._sanitize_postal_code(
            postal_code or cls._extract_address_component(geo_data, ['postcode'])
        )

        try:
            # Prioritise the most specific match (local Wahlkreis/Bezirk)
            local_constituency = cls._match_local_constituency(
                sanitized_postal,
                normalized_city,
                normalized_state
            )
            if local_constituency:
                return local_constituency

            state_constituency = cls._match_state_constituency(normalized_state)
            if state_constituency:
                return state_constituency

            return cls._fallback_federal_constituency()

        except Exception as e:
            logger.error(f"Constituency mapping error: {e}")
            return cls._fallback_federal_constituency()

    @classmethod
    def get_constituencies_for_address(
        cls,
        street_address: str,
        postal_code: str,
        city: str,
        state: str
    ) -> Dict[str, Optional[Constituency]]:
        """
        Get all relevant constituencies (federal, state, local) for an address.

        Returns:
            Dictionary with 'federal', 'state', and 'local' keys mapping to
            Constituency objects or None
        """
        geo_data = cls.geocode_address(street_address, postal_code, city)
        normalized_state = cls.normalize_state_name(
            state or cls._extract_address_component(geo_data, ['state', 'state_district'])
        )
        normalized_city = cls._normalize_city(
            city or cls._extract_address_component(geo_data, ['city', 'town', 'village', 'municipality'])
        )
        sanitized_postal = cls._sanitize_postal_code(
            postal_code or cls._extract_address_component(geo_data, ['postcode'])
        )

        result: Dict[str, Optional[Constituency]] = {
            'federal': None,
            'state': cls._match_state_constituency(normalized_state),
            'local': cls._match_local_constituency(
                sanitized_postal,
                normalized_city,
                normalized_state
            )
        }

        federal_constituency = cls._match_federal_constituency_from_geo(geo_data)
        if not federal_constituency:
            federal_constituency = cls._fallback_federal_constituency()
        result['federal'] = federal_constituency

        return result

    @classmethod
    def constituencies_from_postal_code(cls, postal_code: str) -> Dict[str, Optional[Constituency]]:
        """Resolve constituencies using only a postal code."""
        sanitized_postal = cls._sanitize_postal_code(postal_code)
        if not sanitized_postal:
            return {
                'federal': cls._fallback_federal_constituency(),
                'state': None,
                'local': None,
            }

        return cls.get_constituencies_for_address(
            street_address='',
            postal_code=sanitized_postal,
            city='',
            state=''
        )

    @classmethod
    def select_preferred_constituency(cls, matches: Dict[str, Optional[Constituency]]) -> Optional[Constituency]:
        """Pick the most relevant constituency from a mapping of levels."""
        for level in ('federal', 'local', 'state'):
            constituency = matches.get(level)
            if constituency:
                return constituency
        return None

    @classmethod
    def _sanitize_postal_code(cls, postal_code: Optional[str]) -> Optional[str]:
        if not postal_code:
            return None
        cleaned = cls.POSTAL_CODE_SANITIZER.sub('', str(postal_code))
        return cleaned[:5] if cleaned else None

    @classmethod
    def _normalize_city(cls, city: Optional[str]) -> Optional[str]:
        if not city:
            return None
        return city.strip().lower()

    @classmethod
    def _extract_address_component(cls, geo_data: Optional[Dict[str, Any]], keys: List[str]) -> Optional[str]:
        if not geo_data:
            return None
        address = geo_data.get('address', {})
        for key in keys:
            value = address.get(key)
            if value:
                return value
        return None

    @classmethod
    def _match_state_constituency(cls, normalized_state: Optional[str]) -> Optional[Constituency]:
        if not normalized_state:
            return None

        return Constituency.objects.filter(
            level='STATE'
        ).filter(
            Q(name__iexact=normalized_state) |
            Q(region__iexact=normalized_state) |
            Q(metadata__state__iexact=normalized_state) |
            Q(metadata__state_code__iexact=normalized_state)
        ).first()

    @classmethod
    def _match_local_constituency(
        cls,
        postal_code: Optional[str],
        normalized_city: Optional[str],
        normalized_state: Optional[str]
    ) -> Optional[Constituency]:
        queryset = Constituency.objects.filter(level__in=['LOCAL', 'FEDERAL']).order_by('level')

        if normalized_state:
            queryset = queryset.filter(
                Q(region__icontains=normalized_state) |
                Q(metadata__state__iexact=normalized_state) |
                Q(metadata__state_code__iexact=normalized_state)
            )

        candidates = list(queryset)

        if postal_code:
            prefixes = [postal_code[:length] for length in range(len(postal_code), 0, -1)]
            for candidate in candidates:
                metadata = candidate.metadata or {}
                postal_prefixes = metadata.get('postal_code_prefixes') or metadata.get('plz_prefixes') or []
                if any(postal_code.startswith(prefix) for prefix in postal_prefixes):
                    return candidate

                region = (candidate.region or '').strip()
                if region and postal_code.startswith(region):
                    return candidate

        if normalized_city:
            for candidate in candidates:
                if normalized_city in (candidate.name or '').lower():
                    return candidate
                metadata = candidate.metadata or {}
                cities = metadata.get('cities') or []
                if any(normalized_city == city for city in cities):
                    return candidate

        return None

    @classmethod
    def _fallback_federal_constituency(cls) -> Optional[Constituency]:
        return Constituency.objects.filter(level='FEDERAL').order_by('id').first()


class RepresentativeDataService:
    """
    Service for syncing representative data from Abgeordnetenwatch API.
    """

    @staticmethod
    def _match_state_from_text(text: Optional[str]) -> Optional[str]:
        if not text:
            return None
        lower_text = text.lower()
        for canonical, aliases in GERMAN_STATE_ALIASES.items():
            if canonical.lower() in lower_text:
                return canonical
            for alias in aliases:
                if alias.lower() in lower_text:
                    return canonical
        return None

    @classmethod
    def _detect_list_scope(cls, electoral_data: Dict[str, Any]) -> Dict[str, Any]:
        scope_info = {
            'constituency_scope': 'district',
            'list_state_normalized': None,
            'list_scope_raw': None,
        }

        if not electoral_data:
            return scope_info

        mandate_won = electoral_data.get('mandate_won')
        scope_info['mandate_won'] = mandate_won

        if mandate_won not in {'list', 'moved_up'}:
            return scope_info

        list_level = (electoral_data.get('list_level') or '').lower()
        list_label = electoral_data.get('list_label') or ''
        list_scope = None

        if list_level == 'federal':
            list_scope = 'federal'
        elif list_level == 'state':
            list_scope = 'state'

        if not list_scope:
            if 'bund' in list_label.lower():
                list_scope = 'federal'
            else:
                state_from_label = cls._match_state_from_text(list_label)
                if state_from_label:
                    list_scope = 'state'
                    scope_info['list_state_normalized'] = state_from_label

        if not scope_info['list_state_normalized']:
            possible_state = electoral_data.get('list_state') or electoral_data.get('state')
            normalized_state = normalize_german_state(possible_state)
            if normalized_state:
                scope_info['list_state_normalized'] = normalized_state
                list_scope = list_scope or 'state'

        if not list_scope:
            list_scope = 'federal'

        scope_info['constituency_scope'] = 'state' if list_scope == 'state' else 'federal'
        scope_info['list_scope_raw'] = list_scope

        return scope_info

    @classmethod
    def _build_representative_metadata(
        cls,
        mandate: Dict[str, Any],
        base_metadata: Dict[str, Any],
        default_scope: Optional[str] = None,
        default_state: Optional[str] = None,
    ) -> Dict[str, Any]:
        electoral_data = mandate.get('electoral_data') or {}
        scope_info = cls._detect_list_scope(electoral_data)

        if default_scope:
            mandate_won = electoral_data.get('mandate_won')
            if mandate_won in {'list', 'moved_up'}:
                scope_info['constituency_scope'] = default_scope
                if default_scope == 'state':
                    if default_state:
                        scope_info['list_state_normalized'] = default_state
                        scope_info['list_scope_raw'] = 'state'
                    elif scope_info.get('list_state_normalized'):
                        scope_info['list_scope_raw'] = 'state'
                elif default_scope == 'federal':
                    scope_info['list_scope_raw'] = 'federal'

        metadata = {
            **base_metadata,
            'electoral_data': electoral_data,
            'constituency_scope': scope_info.get('constituency_scope', 'district'),
            'mandate_won': scope_info.get('mandate_won'),
            'list_scope_raw': scope_info.get('list_scope_raw'),
        }

        if scope_info.get('list_state_normalized'):
            metadata['list_state_normalized'] = scope_info['list_state_normalized']

        return metadata

    @classmethod
    @transaction.atomic
    def sync_federal_representatives(cls, dry_run: bool = False) -> Dict[str, int]:
        """
        Sync Bundestag representatives from Abgeordnetenwatch API.

        Returns:
            Dictionary with counts of created/updated constituencies and representatives
        """
        stats = {
            'constituencies_created': 0,
            'constituencies_updated': 0,
            'representatives_created': 0,
            'representatives_updated': 0,
        }

        # Get Bundestag parliament
        logger.info("Fetching parliaments from API...")
        parliaments = AbgeordnetenwatchAPI.get_parliaments()
        bundestag = next((p for p in parliaments if 'Bundestag' in p.get('label', '')), None)

        if not bundestag:
            logger.error("Bundestag parliament not found in API")
            return stats

        logger.info(f"Found Bundestag: {bundestag.get('label')} (ID: {bundestag.get('id')})")

        # Get current parliament period
        logger.info(f"Fetching parliament periods for Bundestag (ID: {bundestag['id']})...")
        periods = AbgeordnetenwatchAPI.get_parliament_periods(bundestag['id'])
        current_period = max(periods, key=lambda p: p.get('id', 0)) if periods else None

        if not current_period:
            logger.error("No parliament period found")
            return stats

        logger.info(f"Current period: {current_period.get('label')} (ID: {current_period.get('id')})")

        # Create/update Bundestag constituency (unless dry run)
        if not dry_run:
            bundestag_constituency, created = Constituency.objects.update_or_create(
                name='Deutscher Bundestag',
                level='FEDERAL',
                defaults={
                    'legislative_body': 'Deutscher Bundestag',
                    'legislative_period_start': date.fromisoformat(current_period['start_date_period']) if current_period.get('start_date_period') else date.today(),
                    'legislative_period_end': date.fromisoformat(current_period['end_date_period']) if current_period.get('end_date_period') else None,
                    'region': 'DE',
                    'metadata': {
                        'api_id': bundestag['id'],
                        'period_id': current_period['id'],
                        'source': 'abgeordnetenwatch',
                    }
                }
            )

            if created:
                stats['constituencies_created'] += 1
                logger.info("Created Bundestag constituency")
            else:
                stats['constituencies_updated'] += 1
                logger.info("Updated Bundestag constituency")
        else:
            # In dry run, just get existing or create a temporary one for processing
            bundestag_constituency, _ = Constituency.objects.get_or_create(
                name='Deutscher Bundestag',
                level='FEDERAL',
                defaults={'legislative_body': 'Deutscher Bundestag', 'region': 'DE', 'legislative_period_start': date.today()}
            )
            logger.info("[DRY RUN] Would create/update Bundestag constituency")

        # Get candidacies/mandates for current period
        logger.info(f"Fetching mandates for period {current_period.get('id')}...")
        mandates = AbgeordnetenwatchAPI.get_candidacies_mandates(current_period['id'])

        # Filter for current mandates only
        # mandate_won can be: 'constituency' (direct), 'list' (party list), 'moved_up' (substitute), etc.
        active_mandates = [
            m for m in mandates
            if m.get('type') == 'mandate' and
            m.get('electoral_data', {}).get('mandate_won')  # Any value means mandate was won
        ]

        logger.info(f"Found {len(active_mandates)} active mandates out of {len(mandates)} total")

        for i, mandate in enumerate(active_mandates, 1):
            politician_ref = mandate.get('politician', {})

            if not politician_ref:
                logger.debug(f"Mandate {i}/{len(active_mandates)}: No politician reference, skipping")
                continue

            politician_id = politician_ref.get('id')
            if not politician_id:
                logger.debug(f"Mandate {i}/{len(active_mandates)}: No politician ID, skipping")
                continue

            # Parse name from label (format: "FirstName LastName")
            label = politician_ref.get('label', '')
            name_parts = label.rsplit(' ', 1)  # Split from right to handle multi-word first names
            if len(name_parts) == 2:
                first_name, last_name = name_parts
            elif len(name_parts) == 1:
                first_name = name_parts[0]
                last_name = ''
            else:
                logger.warning(f"Could not parse name from label: {label}")
                continue

            # Extract party from fraction_membership (parliamentary group)
            fraction_memberships = mandate.get('fraction_membership', [])
            if fraction_memberships and len(fraction_memberships) > 0:
                fraction = fraction_memberships[0].get('fraction', {})
                party_label = fraction.get('label', '')
                # Extract party name (remove period info in parentheses)
                party_name = party_label.split(' (')[0] if party_label else ''
            else:
                party_name = ''

            logger.info(f"Processing {i}/{len(active_mandates)}: {first_name} {last_name} ({party_name})")

            # Create/update representative (unless dry run)
            if not dry_run:
                # Use mandate dates if available, otherwise use parliament period dates
                term_start = None
                if mandate.get('start_date'):
                    term_start = date.fromisoformat(mandate['start_date'])
                elif current_period.get('start_date_period'):
                    term_start = date.fromisoformat(current_period['start_date_period'])

                term_end = None
                if mandate.get('end_date'):
                    term_end = date.fromisoformat(mandate['end_date'])
                elif current_period.get('end_date_period'):
                    term_end = date.fromisoformat(current_period['end_date_period'])

                # Fetch full politician data to get URLs (abgeordnetenwatch, wikipedia)
                abgeordnetenwatch_url = ''
                wikipedia_url = ''
                try:
                    response = requests.get(
                        f"{AbgeordnetenwatchAPI.BASE_URL}/politicians/{politician_id}",
                        timeout=10
                    )
                    if response.status_code == 200:
                        politician_full = response.json().get('data', {})
                        abgeordnetenwatch_url = politician_full.get('abgeordnetenwatch_url', '')
                        qid_wikidata = politician_full.get('qid_wikidata', '')
                        if qid_wikidata:
                            # Wikidata QID - construct wikidata URL (will redirect to language-specific Wikipedia)
                            wikipedia_url = f"https://www.wikidata.org/wiki/{qid_wikidata}"
                        logger.debug(f"  Fetched URLs for {first_name} {last_name}")
                except Exception as e:
                    logger.warning(f"  Failed to fetch politician URLs: {e}")

                metadata_base = {
                    'api_id': politician_id,
                    'mandate_id': mandate.get('id'),
                    'source': 'abgeordnetenwatch',
                    'abgeordnetenwatch_url': abgeordnetenwatch_url,
                    'wikipedia_url': wikipedia_url,
                }

                rep_metadata = cls._build_representative_metadata(mandate, metadata_base)

                rep, created = Representative.objects.update_or_create(
                    first_name=first_name,
                    last_name=last_name,
                    constituency=bundestag_constituency,
                    defaults={
                        'party': party_name,
                        'role': 'Member of Parliament',
                        'email': '',  # Not available in mandate data
                        'term_start': term_start,
                        'term_end': term_end,
                        'is_active': True,
                        'metadata': rep_metadata,
                    }
                )

                if created:
                    stats['representatives_created'] += 1
                    logger.debug(f"  Created representative: {first_name} {last_name}")
                else:
                    stats['representatives_updated'] += 1
                    logger.debug(f"  Updated representative: {first_name} {last_name}")

                # Sync committee memberships for this representative
                mandate_id = mandate.get('id')
                committee_stats = cls.sync_committee_memberships_for_representative(
                    representative=rep,
                    mandate_id=mandate_id,
                    parliament_label='Bundestag'
                )

                # Aggregate committee stats (only track for logging, not in main stats)
                if i == 1:  # Initialize on first iteration
                    stats['total_committees_created'] = 0
                    stats['total_committees_updated'] = 0
                    stats['total_memberships_created'] = 0
                    stats['total_memberships_updated'] = 0

                stats['total_committees_created'] += committee_stats.get('committees_created', 0)
                stats['total_committees_updated'] += committee_stats.get('committees_updated', 0)
                stats['total_memberships_created'] += committee_stats.get('memberships_created', 0)
                stats['total_memberships_updated'] += committee_stats.get('memberships_updated', 0)

            else:
                stats['representatives_created'] += 1  # Count as "would create"
                logger.debug(f"  [DRY RUN] Would create/update: {first_name} {last_name}")

        return stats

    @classmethod
    @transaction.atomic
    def sync_state_representatives(cls, state_name: str = None, dry_run: bool = False) -> Dict[str, int]:
        """
        Sync state parliament (Landtag) representatives.

        Args:
            state_name: Optional state name to filter by
            dry_run: If True, only preview changes
        """
        stats = {
            'constituencies_created': 0,
            'constituencies_updated': 0,
            'representatives_created': 0,
            'representatives_updated': 0,
        }

        logger.info("Fetching parliaments from API...")
        parliaments = AbgeordnetenwatchAPI.get_parliaments()

        normalized_filter = normalize_german_state(state_name) if state_name else None

        state_parliaments: List[Dict[str, Any]] = []
        for parliament in parliaments:
            label = parliament.get('label', '') or ''
            normalized_label = normalize_german_state(label)
            if normalized_label and normalized_label in GERMAN_STATE_ALIASES:
                if normalized_filter and normalized_label != normalized_filter:
                    continue
                state_parliaments.append({**parliament, '_normalized_state': normalized_label})

        logger.info(
            "Found %s state parliaments%s",
            len(state_parliaments),
            f" (filter='{normalized_filter}')" if normalized_filter else ''
        )

        for parliament in state_parliaments:
            logger.info(f"Syncing {parliament.get('label')} (ID: {parliament.get('id')})")

            # Get current period
            periods = AbgeordnetenwatchAPI.get_parliament_periods(parliament['id'])
            if not periods:
                logger.warning(f"No periods found for {parliament.get('label')}")
                continue

            current_project = parliament.get('current_project') or {}
            current_period = None
            if current_project:
                current_period = next(
                    (p for p in periods if p.get('id') == current_project.get('id')),
                    None
                )
                if not current_period:
                    current_period = current_project

            if not current_period:
                current_period = max(periods, key=lambda p: p.get('id', 0))
            logger.info(f"  Current period: {current_period.get('label')} (ID: {current_period.get('id')})")

            # Extract state name from parliament label
            state = parliament.get('_normalized_state') or normalize_german_state(parliament.get('label', ''))

            # Create/update constituency (unless dry run)
            if not dry_run:
                constituency, created = Constituency.objects.update_or_create(
                    name=parliament.get('label', ''),
                    level='STATE',
                    defaults={
                        'legislative_body': parliament.get('label', ''),
                        'legislative_period_start': date.fromisoformat(current_period['start_date_period']) if current_period.get('start_date_period') else date.today(),
                        'legislative_period_end': date.fromisoformat(current_period['end_date_period']) if current_period.get('end_date_period') else None,
                        'region': state,
                        'metadata': {
                            'api_id': parliament['id'],
                            'period_id': current_period['id'],
                            'source': 'abgeordnetenwatch',
                        }
                    }
                )

                if created:
                    stats['constituencies_created'] += 1
                    logger.info(f"  Created constituency: {parliament.get('label')}")
                else:
                    stats['constituencies_updated'] += 1
                    logger.info(f"  Updated constituency: {parliament.get('label')}")
            else:
                constituency, _ = Constituency.objects.get_or_create(
                    name=parliament.get('label', ''),
                    level='STATE',
                    defaults={'legislative_body': parliament.get('label', ''), 'region': state, 'legislative_period_start': date.today()}
                )
                logger.info(f"  [DRY RUN] Would create/update constituency: {parliament.get('label')}")

            # Get mandates
            logger.info(f"  Fetching mandates for period {current_period.get('id')}...")
            mandates = AbgeordnetenwatchAPI.get_candidacies_mandates(current_period['id'])
            active_mandates = [
                m for m in mandates
                if m.get('type') == 'mandate' and
                m.get('electoral_data', {}).get('mandate_won')  # Any value means mandate was won
            ]

            logger.info(f"  Found {len(active_mandates)} active mandates")

            for i, mandate in enumerate(active_mandates, 1):
                politician_ref = mandate.get('politician', {})

                if not politician_ref:
                    continue

                politician_id = politician_ref.get('id')
                if not politician_id:
                    continue

                # Parse name from label
                label = politician_ref.get('label', '')
                name_parts = label.rsplit(' ', 1)
                if len(name_parts) == 2:
                    first_name, last_name = name_parts
                elif len(name_parts) == 1:
                    first_name = name_parts[0]
                    last_name = ''
                else:
                    continue

                # Extract party from fraction_membership
                fraction_memberships = mandate.get('fraction_membership', [])
                if fraction_memberships and len(fraction_memberships) > 0:
                    fraction = fraction_memberships[0].get('fraction', {})
                    party_label = fraction.get('label', '')
                    party_name = party_label.split(' (')[0] if party_label else ''
                else:
                    party_name = ''

                logger.debug(f"    {i}/{len(active_mandates)}: {first_name} {last_name} ({party_name})")

                if not dry_run:
                    metadata_base = {
                        'api_id': politician_id,
                        'mandate_id': mandate.get('id'),
                        'source': 'abgeordnetenwatch',
                    }
                    rep_metadata = cls._build_representative_metadata(
                        mandate,
                        metadata_base,
                        default_scope='state',
                        default_state=state,
                    )

                    rep, created = Representative.objects.update_or_create(
                        first_name=first_name,
                        last_name=last_name,
                        constituency=constituency,
                        defaults={
                            'party': party_name,
                            'role': 'Member of State Parliament',
                            'email': '',
                            'term_start': date.fromisoformat(mandate['start_date']) if mandate.get('start_date') else date.today(),
                            'term_end': date.fromisoformat(mandate['end_date']) if mandate.get('end_date') else None,
                            'is_active': True,
                            'metadata': rep_metadata,
                        }
                    )

                    if created:
                        stats['representatives_created'] += 1
                    else:
                        stats['representatives_updated'] += 1
                else:
                    stats['representatives_created'] += 1

                # Respectful rate limiting
                time.sleep(0.15)

        return stats

    @classmethod
    @transaction.atomic
    def sync_eu_representatives(cls, dry_run: bool = False) -> Dict[str, int]:
        """
        Sync European Parliament representatives (MEPs) from Germany.

        Returns:
            Dictionary with counts of created/updated constituencies and representatives
        """
        stats = {
            'constituencies_created': 0,
            'constituencies_updated': 0,
            'representatives_created': 0,
            'representatives_updated': 0,
        }

        # Get EU Parliament
        logger.info("Fetching parliaments from API...")
        parliaments = AbgeordnetenwatchAPI.get_parliaments()
        eu_parliament = next((p for p in parliaments if 'EU' in p.get('label', '') or 'Europ' in p.get('label', '')), None)

        if not eu_parliament:
            logger.error("EU Parliament not found in API")
            return stats

        logger.info(f"Found EU Parliament: {eu_parliament.get('label')} (ID: {eu_parliament.get('id')})")

        # Get current parliament period
        logger.info(f"Fetching parliament periods for EU Parliament (ID: {eu_parliament['id']})...")
        periods = AbgeordnetenwatchAPI.get_parliament_periods(eu_parliament['id'])
        current_period = max(periods, key=lambda p: p.get('id', 0)) if periods else None

        if not current_period:
            logger.error("No EU parliament period found")
            return stats

        logger.info(f"Current period: {current_period.get('label')} (ID: {current_period.get('id')})")

        # Create/update EU Parliament constituency (unless dry run)
        if not dry_run:
            eu_constituency, created = Constituency.objects.update_or_create(
                name='European Parliament (Germany)',
                level='EU',
                defaults={
                    'legislative_body': 'European Parliament',
                    'legislative_period_start': date.fromisoformat(current_period['start_date_period']) if current_period.get('start_date_period') else date.today(),
                    'legislative_period_end': date.fromisoformat(current_period['end_date_period']) if current_period.get('end_date_period') else None,
                    'region': 'DE',
                    'metadata': {
                        'api_id': eu_parliament['id'],
                        'period_id': current_period['id'],
                        'source': 'abgeordnetenwatch',
                    }
                }
            )

            if created:
                stats['constituencies_created'] += 1
                logger.info("Created EU Parliament constituency")
            else:
                stats['constituencies_updated'] += 1
                logger.info("Updated EU Parliament constituency")
        else:
            eu_constituency, _ = Constituency.objects.get_or_create(
                name='European Parliament (Germany)',
                level='EU',
                defaults={'legislative_body': 'European Parliament', 'region': 'DE', 'legislative_period_start': date.today()}
            )
            logger.info("[DRY RUN] Would create/update EU Parliament constituency")

        # Get candidacies/mandates for current period
        logger.info(f"Fetching mandates for period {current_period.get('id')}...")
        mandates = AbgeordnetenwatchAPI.get_candidacies_mandates(current_period['id'])

        # Filter for current mandates only (MEPs from Germany)
        active_mandates = [
            m for m in mandates
            if m.get('type') == 'mandate' and
            m.get('electoral_data', {}).get('mandate_won')  # Any value means mandate was won
        ]

        logger.info(f"Found {len(active_mandates)} active MEP mandates out of {len(mandates)} total")

        for i, mandate in enumerate(active_mandates, 1):
            politician_ref = mandate.get('politician', {})

            if not politician_ref:
                continue

            politician_id = politician_ref.get('id')
            if not politician_id:
                continue

            # Parse name from label
            label = politician_ref.get('label', '')
            name_parts = label.rsplit(' ', 1)
            if len(name_parts) == 2:
                first_name, last_name = name_parts
            elif len(name_parts) == 1:
                first_name = name_parts[0]
                last_name = ''
            else:
                continue

            # Extract party from fraction_membership
            fraction_memberships = mandate.get('fraction_membership', [])
            if fraction_memberships and len(fraction_memberships) > 0:
                fraction = fraction_memberships[0].get('fraction', {})
                party_label = fraction.get('label', '')
                party_name = party_label.split(' (')[0] if party_label else ''
            else:
                party_name = ''

            logger.info(f"Processing {i}/{len(active_mandates)}: {first_name} {last_name} ({party_name})")

            # Create/update representative (MEP) (unless dry run)
            if not dry_run:
                metadata_base = {
                    'api_id': politician_id,
                    'mandate_id': mandate.get('id'),
                    'source': 'abgeordnetenwatch',
                }
                rep_metadata = cls._build_representative_metadata(mandate, metadata_base)

                rep, created = Representative.objects.update_or_create(
                    first_name=first_name,
                    last_name=last_name,
                    constituency=eu_constituency,
                    defaults={
                        'party': party_name,
                        'role': 'Member of European Parliament (MEP)',
                        'email': '',
                        'term_start': date.fromisoformat(mandate['start_date']) if mandate.get('start_date') else date.today(),
                        'term_end': date.fromisoformat(mandate['end_date']) if mandate.get('end_date') else None,
                        'is_active': True,
                        'metadata': rep_metadata,
                    }
                )

                if created:
                    stats['representatives_created'] += 1
                    logger.debug(f"  Created MEP: {first_name} {last_name}")
                else:
                    stats['representatives_updated'] += 1
                    logger.debug(f"  Updated MEP: {first_name} {last_name}")
            else:
                stats['representatives_created'] += 1  # Count as "would create"
                logger.debug(f"  [DRY RUN] Would create/update: {first_name} {last_name}")

        return stats

    @classmethod
    def sync_committee_memberships_for_representative(
        cls,
        representative: Representative,
        mandate_id: int,
        parliament_label: str
    ) -> Dict[str, int]:
        """
        Sync committee memberships for a specific representative.

        Args:
            representative: The Representative object
            mandate_id: The API mandate ID for this representative
            parliament_label: Parliament name (for Committee.parliament field)

        Returns:
            Dictionary with counts of committees and memberships created/updated
        """
        stats = {
            'committees_created': 0,
            'committees_updated': 0,
            'memberships_created': 0,
            'memberships_updated': 0,
        }

        # Fetch committee memberships from API
        try:
            response = requests.get(
                f"{AbgeordnetenwatchAPI.BASE_URL}/committee-memberships",
                params={'candidacy_mandate': mandate_id},
                timeout=10
            )
            response.raise_for_status()
            memberships_data = response.json().get('data', [])
        except requests.RequestException as e:
            logger.debug(f"No committee memberships for {representative.full_name}: {e}")
            return stats

        if not memberships_data:
            return stats

        logger.debug(f"Found {len(memberships_data)} committee memberships for {representative.full_name}")

        # Process each membership
        for membership_data in memberships_data:
            committee_data = membership_data.get('committee', {})
            if not committee_data:
                continue

            committee_name = committee_data.get('label', '')
            committee_api_id = committee_data.get('id')

            if not committee_name:
                continue

            # Create/update committee
            committee, created = Committee.objects.update_or_create(
                name=committee_name,
                parliament=parliament_label,
                defaults={
                    'metadata': {
                        'api_id': committee_api_id,
                        'api_url': committee_data.get('api_url', ''),
                        'abgeordnetenwatch_url': committee_data.get('abgeordnetenwatch_url', ''),
                    }
                }
            )

            if created:
                stats['committees_created'] += 1
            else:
                stats['committees_updated'] += 1

            # Create/update membership
            role = membership_data.get('committee_role', 'member')
            additional_roles = membership_data.get('committee_roles_additional') or []

            membership, created = CommitteeMembership.objects.update_or_create(
                representative=representative,
                committee=committee,
                defaults={
                    'role': role,
                    'additional_roles': additional_roles if isinstance(additional_roles, list) else [],
                    'metadata': {
                        'api_id': membership_data.get('id'),
                        'api_url': membership_data.get('api_url', ''),
                    }
                }
            )

            if created:
                stats['memberships_created'] += 1
                logger.debug(f"  Created membership: {committee_name} ({role})")
            else:
                stats['memberships_updated'] += 1
                logger.debug(f"  Updated membership: {committee_name} ({role})")

        return stats


class IdentityVerificationService:
    """
    Handles identity verification for users.

    This is currently stubbed. In production, this would integrate with
    a real identity verification provider (e.g., eID, POSTIDENT, etc.)
    """

    @staticmethod
    def initiate_verification(user, provider='stub_provider') -> Dict[str, Any]:
        """
        Initiate identity verification for a user.

        Returns:
            Dictionary with verification session details
        """
        # STUB: In production, this would:
        # 1. Call the verification provider's API
        # 2. Return a verification URL or session ID
        # 3. Store the session details

        return {
            'status': 'initiated',
            'provider': provider,
            'verification_url': '/verify/stub/',  # Stub URL
            'session_id': 'stub_session_123'
        }

    @staticmethod
    def complete_verification(
        user,
        verification_data: Dict[str, Any]
    ) -> Optional['IdentityVerification']:
        """
        Complete verification after provider callback and link user to a constituency.

        Args:
            user: User object
            verification_data: Data from verification provider

        Returns:
            IdentityVerification instance if verification is stored, None on failure
        """
        from .models import IdentityVerification

        street = verification_data.get('street_address', '')
        postal_code = verification_data.get('postal_code', '')
        city = verification_data.get('city', '')
        state = verification_data.get('state', '')

        normalized_state = AddressConstituencyMapper.normalize_state_name(state)

        constituency_matches = AddressConstituencyMapper.get_constituencies_for_address(
            street_address=street,
            postal_code=postal_code,
            city=city,
            state=normalized_state or state
        )
        constituency = AddressConstituencyMapper.select_preferred_constituency(constituency_matches)

        verification_payload = dict(verification_data)
        verification_payload['normalized_state'] = normalized_state
        verification_payload['matched_constituencies'] = {
            level: match.pk if match else None
            for level, match in constituency_matches.items()
        }

        defaults = {
            'status': 'VERIFIED',
            'provider': verification_data.get('provider', 'stub_provider'),
            'street_address': street,
            'postal_code': postal_code,
            'city': city,
            'state': normalized_state or state,
            'constituency': constituency,
            'verified_at': timezone.now(),
            'verification_data': verification_payload,
        }

        verification, _ = IdentityVerification.objects.update_or_create(
            user=user,
            defaults=defaults
        )

        return verification


class TopicSuggestionService:
    """
    Service for suggesting constituencies and representatives based on user concerns.

    Uses the topic taxonomy to intelligently map user input to the appropriate
    government level and representatives based on German competency distribution.
    """

    @staticmethod
    def suggest_representatives_for_concern(
        concern_text: str,
        user_address: Optional[Dict[str, str]] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Suggest representatives based on a user's concern.

        Args:
            concern_text: The user's concern description (e.g., "better train connections")
            user_address: Optional address dict with keys: street_address, postal_code, city, state
            limit: Maximum number of representatives to suggest

        Returns:
            Dictionary with:
                - matched_topics: List of matched TopicArea objects with scores
                - suggested_level: Primary government level (EU/FEDERAL/STATE)
                - suggested_constituencies: List of relevant Constituency objects
                - suggested_representatives: List of Representative objects
                - explanation: Human-readable explanation of the suggestion
        """
        from .topic_taxonomy import TopicMatcher

        # Match the concern text to topics
        matcher = TopicMatcher()
        topic_matches = matcher.match_topics(concern_text, threshold=1)
        primary_level = matcher.get_primary_level(concern_text)
        level_suggestions = matcher.suggest_levels(concern_text)

        # Get constituencies for the suggested level
        suggested_constituencies = []

        if primary_level == 'EU':
            # EU level - suggest European Parliament
            suggested_constituencies = list(Constituency.objects.filter(level='EU'))

        elif primary_level == 'FEDERAL':
            # Federal level - suggest Bundestag
            suggested_constituencies = list(Constituency.objects.filter(level='FEDERAL'))

        elif primary_level == 'STATE':
            # State level - need user's address to determine which state
            if user_address:
                state_constituencies = AddressConstituencyMapper.get_constituencies_for_address(
                    street_address=user_address.get('street_address', ''),
                    postal_code=user_address.get('postal_code', ''),
                    city=user_address.get('city', ''),
                    state=user_address.get('state', '')
                )
                if state_constituencies.get('state'):
                    suggested_constituencies = [state_constituencies['state']]
            else:
                # No address provided - suggest all state constituencies
                suggested_constituencies = list(Constituency.objects.filter(level='STATE'))

        elif primary_level == 'MULTIPLE':
            # Multiple levels involved - suggest federal + state
            if user_address:
                multi_constituencies = AddressConstituencyMapper.get_constituencies_for_address(
                    street_address=user_address.get('street_address', ''),
                    postal_code=user_address.get('postal_code', ''),
                    city=user_address.get('city', ''),
                    state=user_address.get('state', '')
                )
                suggested_constituencies = [
                    c for c in [multi_constituencies.get('federal'), multi_constituencies.get('state')]
                    if c is not None
                ]
            else:
                suggested_constituencies = list(Constituency.objects.filter(level__in=['FEDERAL', 'STATE']))

        # Get representatives from suggested constituencies
        suggested_representatives = []
        for constituency in suggested_constituencies[:3]:  # Limit constituencies
            reps = Representative.objects.filter(
                constituency=constituency,
                is_active=True
            ).order_by('?')[:limit]  # Random sample
            suggested_representatives.extend(reps)

        # Limit total representatives
        suggested_representatives = suggested_representatives[:limit]

        # Generate explanation
        explanation = TopicSuggestionService._generate_explanation(
            topic_matches,
            primary_level,
            suggested_constituencies,
            user_address
        )

        return {
            'matched_topics': topic_matches,
            'suggested_level': primary_level,
            'suggested_constituencies': suggested_constituencies,
            'suggested_representatives': suggested_representatives,
            'explanation': explanation,
        }

    @staticmethod
    def _generate_explanation(
        topic_matches: List[tuple],
        primary_level: str,
        constituencies: List[Constituency],
        user_address: Optional[Dict[str, str]]
    ) -> str:
        """Generate a human-readable explanation for the suggestion."""

        if not topic_matches:
            return "We couldn't identify a specific policy area. We suggest contacting your federal representatives."

        top_topic, score = topic_matches[0]

        level_names = {
            'EU': 'European Union',
            'FEDERAL': 'Federal',
            'STATE': 'State',
            'MULTIPLE': 'multiple government'
        }

        level_name = level_names.get(primary_level, 'Federal')

        explanation_parts = [
            f"Your concern appears to be related to '{top_topic.name}', which is primarily a {level_name} level responsibility."
        ]

        if top_topic.description:
            explanation_parts.append(f"This covers: {top_topic.description}.")

        if constituencies:
            if len(constituencies) == 1:
                explanation_parts.append(f"We suggest contacting representatives from {constituencies[0].name}.")
            elif primary_level == 'STATE' and not user_address:
                explanation_parts.append("To get more specific representatives, please provide your address.")
            else:
                explanation_parts.append(f"We suggest contacting representatives from {len(constituencies)} relevant constituencies.")

        return ' '.join(explanation_parts)

    @staticmethod
    def get_topic_suggestions(concern_text: str) -> List[Dict[str, Any]]:
        """
        Get just the topic matches without representative suggestions.

        Useful for showing users what topics their concern relates to.

        Args:
            concern_text: The user's concern description

        Returns:
            List of dictionaries with topic information
        """
        from .topic_taxonomy import TopicMatcher

        matcher = TopicMatcher()
        matches = matcher.match_topics(concern_text, threshold=1)

        return [
            {
                'name': topic.name,
                'level': topic.level,
                'description': topic.description,
                'examples': topic.examples,
                'match_score': score,
            }
            for topic, score in matches[:5]  # Top 5 matches
        ]


class ConstituencySuggestionService:
    """
    Service to suggest constituencies and representatives based on user concerns.
    Uses TopicArea taxonomy to match user queries to governmental levels.
    """

    @classmethod
    def suggest_from_concern(cls, concern_text: str, user_location: Dict[str, str] = None) -> Dict[str, Any]:
        """
        Suggest constituencies and representatives for a given concern text.

        Two-step process:
        1. Determine relevant parliamentary body based on topic keywords
        2. Filter representatives by committee memberships related to the topic
        """

        concern_lower = concern_text.lower()

        # STEP 1: Match topics by keyword scoring to determine parliamentary body
        matched_topics: List[Dict[str, Any]] = []
        for topic in TopicArea.objects.all():
            score = sum(1 for keyword in topic.get_keywords_list() if keyword.lower() in concern_lower)
            if score:
                matched_topics.append({'topic': topic, 'score': score})

        matched_topics.sort(key=lambda item: item['score'], reverse=True)

        if not matched_topics:
            return {
                'matched_topics': [],
                'suggested_level': None,
                'constituencies': [],
                'representatives': [],
                'explanation': _('No matching policy areas found. Please try different keywords.'),
                'location_constituencies': {},
            }

        top_match = matched_topics[0]
        primary_topic: TopicArea = top_match['topic']
        suggested_level = primary_topic.primary_level

        # Prepare location-aware data
        location_constituencies: Dict[str, Optional[Constituency]] = {}
        preferred_location_constituency: Optional[Constituency] = None
        if user_location and user_location.get('postal_code'):
            location_constituencies = AddressConstituencyMapper.constituencies_from_postal_code(
                user_location['postal_code']
            )
            preferred_location_constituency = AddressConstituencyMapper.select_preferred_constituency(
                location_constituencies
            )

        constituencies: List[Constituency] = []
        representatives: List[Representative] = []
        explanation_parts = [
            _('Your concern relates to **%(topic)s** (%(type)s).') % {
                'topic': primary_topic.name,
                'type': primary_topic.get_competency_type_display()
            }
        ]

        if primary_topic.legal_basis:
            explanation_parts.append(_('Legal basis: %(basis)s') % {'basis': primary_topic.legal_basis})

        # Derive constituencies according to competence level
        if suggested_level == 'FEDERAL':
            if preferred_location_constituency and preferred_location_constituency.level == 'FEDERAL':
                constituencies = [preferred_location_constituency]
            else:
                constituencies = list(Constituency.objects.filter(level='FEDERAL'))
            explanation_parts.append(
                _('This is a **federal (Bund) responsibility**. You should contact federal representatives in the Bundestag.')
            )
        elif suggested_level == 'STATE':
            if user_location and user_location.get('state'):
                constituencies = list(Constituency.objects.filter(
                    level='STATE',
                    region__icontains=user_location['state']
                ))
            elif preferred_location_constituency and preferred_location_constituency.level == 'STATE':
                constituencies = [preferred_location_constituency]
            else:
                constituencies = list(Constituency.objects.filter(level='STATE'))
                explanation_parts.append(
                    _('This is a **state (Land) responsibility**. Provide your state or postal code for tailored suggestions.')
                )
        elif suggested_level == 'LOCAL':
            if preferred_location_constituency and preferred_location_constituency.level == 'LOCAL':
                constituencies = [preferred_location_constituency]
            else:
                constituencies = list(Constituency.objects.filter(level='LOCAL'))
                if user_location and user_location.get('postal_code'):
                    explanation_parts.append(
                        _('We could not map your PLZ to a local body. Please verify it or provide more address detail.')
                    )
                else:
                    explanation_parts.append(
                        _('This is a **local (municipal) responsibility**. Provide your PLZ for precise matches.')
                    )
        elif suggested_level == 'MIXED':
            explanation_parts.append(
                _('This topic has **mixed competency** across multiple governmental levels.')
            )
        elif suggested_level == 'EU':
            explanation_parts.append(
                _('This is an **EU-level responsibility**. You should contact Members of the European Parliament (MEPs).')
            )

        # STEP 2: Within the determined parliamentary body, filter by committee relevance
        if constituencies:
            from .models import Committee

            # Find committees related to the primary topic
            relevant_committees = Committee.objects.filter(
                topic_area=primary_topic
            ).values_list('id', flat=True)

            # Also check if concern text mentions any committee names
            committee_name_matches = Committee.objects.filter(
                Q(name__icontains=concern_text) | Q(name__icontains=concern_lower),
                parliament__in=[c.legislative_body for c in constituencies]
            ).values_list('id', flat=True)

            all_relevant_committee_ids = set(list(relevant_committees) + list(committee_name_matches))

            # Get all representatives from the constituencies
            all_reps = Representative.objects.filter(
                constituency__in=constituencies,
                is_active=True
            ).select_related('constituency').prefetch_related(
                'committee_memberships__committee__topic_area'
            )

            # Separate into two groups: those with relevant committees, and others
            reps_with_committees = []
            reps_without_committees = []

            for rep in all_reps:
                rep.relevant_committees = []
                has_relevant_committee = False
                has_relevant_focus = False

                # Check committee memberships
                for membership in rep.committee_memberships.all():
                    # Check if this committee is relevant
                    if membership.committee.id in all_relevant_committee_ids or \
                       membership.committee.topic_area == primary_topic:
                        rep.relevant_committees.append({
                            'committee': membership.committee,
                            'role': membership.get_role_display(),
                        })
                        has_relevant_committee = True

                # Check focus areas (if populated)
                if rep.focus_areas:
                    focus_areas_lower = rep.focus_areas.lower()
                    # Check if any topic keyword matches the focus areas
                    for keyword in primary_topic.get_keywords_list():
                        if keyword.lower() in focus_areas_lower:
                            has_relevant_focus = True
                            break
                    # Also check if concern text keywords match focus areas
                    concern_words = concern_lower.split()
                    for word in concern_words:
                        if len(word) >= 4 and word in focus_areas_lower:
                            has_relevant_focus = True
                            break

                if has_relevant_committee or has_relevant_focus:
                    reps_with_committees.append(rep)
                else:
                    reps_without_committees.append(rep)

            # Prioritize representatives with relevant committees, then others
            representatives = (reps_with_committees + reps_without_committees)[:10]

            if reps_with_committees:
                explanation_parts.append(
                    _('Showing %(count)d representative(s) with relevant committee assignments first.') % {
                        'count': len(reps_with_committees)
                    }
                )

        return {
            'matched_topics': [match['topic'] for match in matched_topics[:3]],
            'suggested_level': suggested_level,
            'constituencies': constituencies,
            'representatives': representatives,
            'explanation': ' '.join(explanation_parts),
            'primary_topic': primary_topic,
            'location_constituencies': location_constituencies,
        }

    @classmethod
    def get_example_queries(cls) -> List[Dict[str, str]]:
        """
        Return example queries to help users understand the system.
        """
        return [
            {
                'query': 'I want better train connections between cities',
                'expected_level': 'FEDERAL',
                'topic': 'Federal Transportation (Deutsche Bahn, ICE)',
            },
            {
                'query': 'Our school building needs renovation',
                'expected_level': 'LOCAL',
                'topic': 'Local Schools (building maintenance)',
            },
            {
                'query': 'We need better education standards and curriculum',
                'expected_level': 'STATE',
                'topic': 'Primary and Secondary Education',
            },
            {
                'query': 'Immigration policy needs reform',
                'expected_level': 'FEDERAL',
                'topic': 'Immigration and Asylum',
            },
            {
                'query': 'We need more bike lanes in our city',
                'expected_level': 'LOCAL',
                'topic': 'Local Transportation',
            },
            {
                'query': 'Climate policy and emissions targets',
                'expected_level': 'FEDERAL',
                'topic': 'Environmental Protection',
            },
        ]
