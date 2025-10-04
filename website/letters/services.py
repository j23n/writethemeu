"""
Core business services for the letters application.

This module provides:
- Abgeordnetenwatch API client utilities
- ConstituencyLocator: coarse mapping from addresses/PLZ to constituencies
- RepresentativeSyncService: imports parliaments, terms, electoral districts, constituencies and representatives
- IdentityVerificationService: stubbed identity workflow
- ConstituencySuggestionService / TopicSuggestionService: lightweight suggestion helpers
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, date
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from .constants import GERMAN_STATE_ALIASES, normalize_german_state
from .models import (
    Committee,
    CommitteeMembership,
    Constituency,
    ElectoralDistrict,
    Parliament,
    ParliamentTerm,
    Representative,
    Tag,
    TopicArea,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abgeordnetenwatch API client helpers
# ---------------------------------------------------------------------------


class AbgeordnetenwatchAPI:
    """Thin client for the public Abgeordnetenwatch v2 API."""

    BASE_URL = "https://www.abgeordnetenwatch.de/api/v2"
    DEFAULT_PAGE_SIZE = 100

    @classmethod
    def _request(cls, endpoint: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        url = f"{cls.BASE_URL}/{endpoint}"
        logger.debug("GET %s params=%s", url, params)
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    @classmethod
    def fetch_paginated(cls, endpoint: str, params: Optional[Dict] = None) -> List[Dict]:
        params = params or {}
        params.setdefault('page', 0)
        params.setdefault('pager_limit', cls.DEFAULT_PAGE_SIZE)

        results: List[Dict] = []
        while True:
            payload = cls._request(endpoint, params)
            data = payload.get('data', [])
            if not data:
                break
            results.extend(data)

            meta = payload.get('meta', {}).get('result', {})
            total = meta.get('total', len(results))
            if len(results) >= total:
                break
            params['page'] += 1
        return results

    @classmethod
    def get_parliaments(cls) -> List[Dict]:
        return cls.fetch_paginated('parliaments')

    @classmethod
    def get_parliament_periods(cls, parliament_id: int) -> List[Dict]:
        return cls.fetch_paginated('parliament-periods', {'parliament': parliament_id})

    @classmethod
    def get_candidacies_mandates(cls, parliament_period_id: int) -> List[Dict]:
        return cls.fetch_paginated('candidacies-mandates', {'parliament_period': parliament_period_id})

    @classmethod
    def get_electoral_list(cls, list_id: int) -> Dict:
        return cls._request(f'electoral-lists/{list_id}')['data']

    @classmethod
    def get_committees(cls, parliament_period_id: Optional[int] = None) -> List[Dict]:
        """Fetch committees, optionally filtered by parliament period."""
        params = {}
        if parliament_period_id:
            params['field_legislature'] = parliament_period_id
        return cls.fetch_paginated('committees', params)

    @classmethod
    def get_committee_memberships(cls, parliament_period_id: Optional[int] = None) -> List[Dict]:
        """Fetch committee memberships, optionally filtered by parliament period."""
        params = {}
        if parliament_period_id:
            # Need to fetch committees first to filter memberships
            # For now, fetch all and filter in Python
            pass
        return cls.fetch_paginated('committee-memberships', params)


# ---------------------------------------------------------------------------
# Constituency / address helper
# ---------------------------------------------------------------------------


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

    @property
    def has_constituencies(self) -> bool:
        return bool(self.constituencies)


class ConstituencyLocator:
    """Heuristic mapping from postal codes to broad constituencies."""

    # Rough PLZ -> state mapping (first two digits).
    STATE_BY_PLZ_PREFIX: Dict[str, str] = {
        **{prefix: 'Berlin' for prefix in ['10', '11']},
        **{prefix: 'Bayern' for prefix in ['80', '81', '82', '83', '84', '85', '86', '87', '88', '89', '90', '91']} ,
        **{prefix: 'Baden-Württemberg' for prefix in ['70', '71', '72', '73', '74', '75', '76', '77', '78', '79']},
        **{prefix: 'Nordrhein-Westfalen' for prefix in ['40', '41', '42', '43', '44', '45', '46', '47', '48', '49', '50', '51', '52', '53', '57']},
        **{prefix: 'Hessen' for prefix in ['34', '35', '36', '60', '61', '62', '63', '64', '65']},
        **{prefix: 'Niedersachsen' for prefix in ['26', '27', '28', '29', '30', '31', '32', '33', '37', '38', '49']},
    }

    @classmethod
    def locate(cls, postal_code: str) -> LocatedConstituencies:
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


# ---------------------------------------------------------------------------
# Representative synchronisation
# ---------------------------------------------------------------------------


class RepresentativeSyncService:
    """Imports parliaments/terms/constituencies/representatives from Abgeordnetenwatch."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.stats = {
            'parliaments_created': 0,
            'parliaments_updated': 0,
            'terms_created': 0,
            'terms_updated': 0,
            'districts_created': 0,
            'districts_updated': 0,
            'constituencies_created': 0,
            'constituencies_updated': 0,
            'representatives_created': 0,
            'representatives_updated': 0,
            'committees_created': 0,
            'committees_updated': 0,
            'memberships_created': 0,
            'memberships_updated': 0,
        }

    # --------------------------------------
    @classmethod
    @transaction.atomic
    def sync(cls, level: str = 'all', state: Optional[str] = None, dry_run: bool = False) -> Dict[str, int]:
        importer = cls(dry_run=dry_run)
        importer._sync(level=level, state=state)
        if dry_run:
            transaction.set_rollback(True)
        return importer.stats

    def _sync(self, level: str = 'all', state: Optional[str] = None) -> None:
        parliaments = AbgeordnetenwatchAPI.get_parliaments()
        for parliament_data in parliaments:
            label = parliament_data.get('label', '')
            if level in ('all', 'eu') and label == 'EU-Parlament':
                self._sync_eu(parliament_data)
            elif level in ('all', 'federal') and label == 'Bundestag':
                self._sync_federal(parliament_data)
            elif level in ('all', 'state') and label not in ('Bundestag', 'EU-Parlament'):
                if state and normalize_german_state(label) != normalize_german_state(state):
                    continue
                self._sync_state(parliament_data)

    # --------------------------------------
    def _sync_federal(self, parliament_data: Dict[str, Any]) -> None:
        logger.info("Syncing Bundestag representatives …")
        parliament, term = self._ensure_parliament_and_term(parliament_data, level='FEDERAL', region='DE')
        mandates = self._fetch_active_mandates(term)
        for mandate in mandates:
            self._import_representative(mandate, parliament, term)
        self._sync_committees_for_term(term)

    def _sync_eu(self, parliament_data: Dict[str, Any]) -> None:
        logger.info("Syncing EU parliament representatives …")
        parliament, term = self._ensure_parliament_and_term(parliament_data, level='EU', region='EU')
        mandates = self._fetch_active_mandates(term)
        for mandate in mandates:
            self._import_representative(mandate, parliament, term)
        self._sync_committees_for_term(term)

    def _sync_state(self, parliament_data: Dict[str, Any]) -> None:
        label = parliament_data.get('label', '')
        logger.info("Syncing Landtag representatives for %s …", label)
        region = normalize_german_state(label)
        parliament, term = self._ensure_parliament_and_term(parliament_data, level='STATE', region=region)
        mandates = self._fetch_active_mandates(term)
        for mandate in mandates:
            self._import_representative(mandate, parliament, term)
        self._sync_committees_for_term(term)

    # --------------------------------------
    def _ensure_parliament_and_term(self, parliament_data: Dict, level: str, region: str) -> Tuple[Parliament, ParliamentTerm]:
        metadata = {
            'api_id': parliament_data.get('id'),
            'source': 'abgeordnetenwatch',
            'raw': parliament_data,
        }
        defaults = {
            'level': level,
            'legislative_body': parliament_data.get('label', ''),
            'region': region,
            'metadata': metadata,
            'parent': None,
        }
        parliament, created = Parliament.objects.update_or_create(
            name=parliament_data.get('label', ''),
            defaults=defaults,
        )
        if created:
            self.stats['parliaments_created'] += 1
        else:
            self.stats['parliaments_updated'] += 1

        periods = AbgeordnetenwatchAPI.get_parliament_periods(parliament_data['id'])
        current_period = self._select_current_period(parliament_data, periods)
        if not current_period:
            term, _ = ParliamentTerm.objects.get_or_create(
                parliament=parliament,
                name='Aktuelle Wahlperiode',
                defaults={'metadata': {'source': 'abgeordnetenwatch'}}
            )
            return parliament, term
        term_defaults = {
            'start_date': self._parse_date(current_period.get('start_date_period')),
            'end_date': self._parse_date(current_period.get('end_date_period')),
            'metadata': {
                'period_id': current_period.get('id'),
                'source': 'abgeordnetenwatch',
                'raw': current_period,
            }
        }
        term, term_created = ParliamentTerm.objects.update_or_create(
            parliament=parliament,
            name=current_period.get('label', 'Aktuelle Wahlperiode'),
            defaults=term_defaults,
        )
        if term_created:
            self.stats['terms_created'] += 1
        else:
            self.stats['terms_updated'] += 1
        return parliament, term

    @staticmethod
    def _select_current_period(parliament_data: Dict, periods: List[Dict]) -> Dict:
        if not periods:
            return {}

        current_project = parliament_data.get('current_project')
        if current_project:
            for period in periods:
                if period.get('id') == current_project.get('id'):
                    return period
            return current_project

        return max(periods, key=lambda p: p.get('id', 0))

    def _fetch_active_mandates(self, term: ParliamentTerm) -> List[Dict]:
        period_id = term.metadata.get('period_id')
        if not period_id:
            return []
        mandates = AbgeordnetenwatchAPI.get_candidacies_mandates(period_id)
        return [
            m for m in mandates
            if m.get('type') == 'mandate' and m.get('electoral_data', {}).get('mandate_won')
        ]

    # --------------------------------------
    def _import_representative(self, mandate: Dict, parliament: Parliament, term: ParliamentTerm) -> None:
        electoral = mandate.get('electoral_data') or {}
        politician = mandate.get('politician') or {}
        mandate_id = str(mandate.get('id'))
        politician_id = politician.get('id')
        first_name, last_name = self._split_name(politician.get('label', ''))
        party_name = self._extract_party_name(mandate)
        election_mode = self._derive_election_mode(parliament, electoral)

        defaults = {
            'parliament_term': term,
            'parliament': parliament,
            'election_mode': election_mode,
            'first_name': first_name,
            'last_name': last_name,
            'party': party_name,
            'term_start': self._parse_date(mandate.get('start_date')) or term.start_date,
            'term_end': self._parse_date(mandate.get('end_date')) or term.end_date,
            'is_active': True,
            'metadata': {
                'mandate': mandate,
                'politician_id': politician_id,
                'abgeordnetenwatch_url': (
                    politician.get('abgeordnetenwatch_url')
                    or politician.get('url')
                ),
                'wikipedia_url': self._extract_wikipedia_link(politician),
            }
        }

        rep, created = Representative.objects.update_or_create(
            external_id=mandate_id,
            defaults=defaults,
        )
        if created:
            self.stats['representatives_created'] += 1
        else:
            self.stats['representatives_updated'] += 1

        rep.constituencies.clear()
        for constituency in self._determine_constituencies(parliament, term, electoral, rep):
            rep.constituencies.add(constituency)

    # --------------------------------------
    def _determine_constituencies(
        self,
        parliament: Parliament,
        term: ParliamentTerm,
        electoral: Dict,
        representative: Representative,
    ) -> Iterable[Constituency]:
        mandate_won = electoral.get('mandate_won')
        if parliament.level == 'EU':
            yield self._get_or_create_constituency(
                term,
                scope='EU_AT_LARGE',
                name='Europäische Union',
                metadata={'state': 'Deutschland'}
            )
            return

        if mandate_won == 'constituency':
            yield self._handle_direct_mandate(parliament, term, electoral)
            return

        if parliament.level == 'FEDERAL':
            list_scope, state_name = self._determine_federal_list_scope(parliament, electoral)
            yield self._get_or_create_constituency(
                term,
                scope=list_scope,
                name=self._build_list_name(term, list_scope, state_name),
                metadata={'state': state_name} if state_name else {}
            )
            return

        # State parliament list seats
        state_name = normalize_german_state(parliament.name)
        yield self._get_or_create_constituency(
            term,
            scope='STATE_LIST',
            name=f"Landesliste {state_name or parliament.name}",
            metadata={'state': state_name}
        )

    # --------------------------------------
    def _handle_direct_mandate(self, parliament: Parliament, term: ParliamentTerm, electoral: Dict) -> Constituency:
        const_data = electoral.get('constituency') or {}
        district_name = const_data.get('label', 'Direktmandat')
        district_id = const_data.get('id')
        state_name = normalize_german_state(self._extract_state_from_electoral(electoral, parliament))

        district = self._get_or_create_district(
            parliament,
            name=district_name,
            external_id=district_id,
            metadata={'state': state_name, 'source': 'abgeordnetenwatch'},
        )
        scope = 'FEDERAL_DISTRICT' if parliament.level == 'FEDERAL' else 'STATE_DISTRICT'
        constituency = self._get_or_create_constituency(
            term,
            scope=scope,
            name=district_name,
            external_id=district_id,
            metadata={'state': state_name}
        )
        constituency.districts.add(district)
        return constituency

    # --------------------------------------
    @staticmethod
    def _build_list_name(term: ParliamentTerm, scope: str, state_name: Optional[str]) -> str:
        if scope == 'FEDERAL_LIST':
            return f"Bundesliste {term.parliament.name}"
        if scope == 'FEDERAL_STATE_LIST':
            state_label = state_name or term.parliament.metadata.get('state') or term.parliament.region
            return f"Landesliste {state_label}"
        if scope == 'STATE_REGIONAL_LIST':
            return f"Regionalliste {state_name or term.name}"
        if scope == 'STATE_LIST':
            return f"Landesliste {state_name or term.parliament.name}"
        return state_name or term.name

    def _determine_federal_list_scope(
        self,
        parliament: Parliament,
        electoral: Dict,
    ) -> Tuple[str, Optional[str]]:
        list_info = electoral.get('electoral_list') or {}
        label = (list_info.get('label') or '').lower()

        if 'bundesliste' in label:
            return 'FEDERAL_LIST', None

        state_name = normalize_german_state(
            self._extract_state_from_electoral(electoral, parliament)
        )
        return 'FEDERAL_STATE_LIST', state_name

    # --------------------------------------
    def _get_or_create_district(
        self,
        parliament: Parliament,
        name: str,
        external_id: Optional[int],
        metadata: Dict,
    ) -> ElectoralDistrict:
        defaults = {
            'parliament': parliament,
            'name': name,
            'level': 'FEDERAL' if parliament.level == 'FEDERAL' else 'STATE',
            'metadata': metadata,
        }
        if external_id:
            district, created = ElectoralDistrict.objects.update_or_create(
                external_id=str(external_id),
                defaults=defaults,
            )
        else:
            district, created = ElectoralDistrict.objects.update_or_create(
                parliament=parliament,
                name=name,
                defaults=defaults,
            )
        if created:
            self.stats['districts_created'] += 1
        else:
            self.stats['districts_updated'] += 1
        return district

    def _get_or_create_constituency(
        self,
        term: ParliamentTerm,
        scope: str,
        name: str,
        metadata: Optional[Dict] = None,
        external_id: Optional[int] = None,
    ) -> Constituency:
        metadata = metadata or {}
        defaults = {
            'parliament_term': term,
            'scope': scope,
            'name': name,
            'metadata': metadata,
        }
        if external_id:
            constituency, created = Constituency.objects.update_or_create(
                external_id=str(external_id),
                defaults=defaults,
            )
        else:
            constituency, created = Constituency.objects.update_or_create(
                parliament_term=term,
                scope=scope,
                name=name,
                defaults={**defaults, 'name': name},
            )
        if created:
            self.stats['constituencies_created'] += 1
        else:
            self.stats['constituencies_updated'] += 1
        return constituency

    # --------------------------------------
    @staticmethod
    def _split_name(label: str) -> Tuple[str, str]:
        parts = label.strip().split()
        if len(parts) >= 2:
            return " ".join(parts[:-1]), parts[-1]
        if parts:
            return parts[0], ''
        return '', ''

    @staticmethod
    def _extract_party_name(mandate: Dict) -> str:
        memberships = mandate.get('fraction_membership') or []
        if memberships:
            fraction = memberships[0].get('fraction', {})
            label = fraction.get('label', '')
            return label.split(' (')[0]
        return ''

    @staticmethod
    def _extract_wikipedia_link(politician: Dict) -> Optional[str]:
        links = politician.get('links') or []
        for link in links:
            label = (link.get('label') or '').lower()
            url = link.get('url') or link.get('href')
            if 'wikipedia' in label and url:
                return url
        # Some entries label the type separately
        for link in links:
            if link.get('type') == 'wikipedia' and link.get('url'):
                return link['url']
        return None

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).date()
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _extract_state_from_electoral(electoral: Dict, parliament: Parliament) -> Optional[str]:
        if parliament.level == 'STATE':
            return parliament.name
        elec_list = electoral.get('electoral_list') or {}
        label = elec_list.get('label', '')
        for state, aliases in GERMAN_STATE_ALIASES.items():
            if state in label:
                return state
            for alias in aliases:
                if alias in label:
                    return state
        return None

    @staticmethod
    def _derive_election_mode(parliament: Parliament, electoral: Dict) -> str:
        mandate_won = electoral.get('mandate_won')
        if parliament.level == 'EU':
            return 'EU_LIST'
        if mandate_won == 'constituency':
            return 'DIRECT'
        list_label = (electoral.get('electoral_list') or {}).get('label', '').lower()
        if parliament.level == 'FEDERAL':
            if 'bundesliste' in list_label:
                return 'FEDERAL_LIST'
            return 'STATE_LIST'
        if parliament.level == 'STATE':
            if 'regional' in list_label:
                return 'STATE_REGIONAL_LIST'
            return 'STATE_LIST'
        return 'DIRECT'

    # --------------------------------------
    # Committee sync methods
    # --------------------------------------

    def _sync_committees_for_term(self, term: ParliamentTerm) -> None:
        """Sync committees and memberships for a given parliament term."""
        period_id = term.metadata.get('period_id')
        if not period_id:
            logger.warning("No period_id found for term %s, skipping committee sync", term)
            return

        logger.info("Syncing committees for %s …", term)

        # Fetch committees for this parliament period
        committees_data = AbgeordnetenwatchAPI.get_committees(period_id)

        # Create a mapping of external committee IDs to Committee objects
        committee_map = {}
        for committee_data in committees_data:
            committee = self._import_committee(committee_data, term)
            if committee:
                committee_map[committee_data['id']] = committee

        # Fetch committee memberships for each committee
        logger.info("Syncing committee memberships for %s (fetching %d committees) …", term, len(committee_map))

        # Fetch memberships for each committee individually to avoid timeout
        for committee_id, committee in committee_map.items():
            try:
                memberships_data = AbgeordnetenwatchAPI.fetch_paginated(
                    'committee-memberships',
                    {'committee': committee_id}
                )

                for membership_data in memberships_data:
                    self._import_committee_membership(membership_data, committee)

            except Exception as e:
                logger.error("Failed to fetch memberships for committee %s: %s", committee_id, e)

    def _import_committee(self, committee_data: Dict, term: ParliamentTerm) -> Optional[Committee]:
        """Import a single committee from API data."""
        try:
            external_id = str(committee_data.get('id'))
            name = committee_data.get('label', '')

            if not name:
                logger.warning("Committee %s has no label, skipping", external_id)
                return None

            # Extract topic information
            topics = committee_data.get('field_topics', [])
            topic_labels = [t.get('label', '') for t in topics]

            # Extract keywords from committee name and topics
            keywords = self._extract_committee_keywords(name, topic_labels)

            # Store all metadata from API
            metadata = {
                'api_id': committee_data.get('id'),
                'entity_type': committee_data.get('entity_type'),
                'source': 'abgeordnetenwatch',
                'api_url': committee_data.get('api_url', ''),
                'abgeordnetenwatch_url': committee_data.get('abgeordnetenwatch_url', ''),
                'field_legislature': committee_data.get('field_legislature'),
                'field_topics': topics,
                'topic_labels': topic_labels,
                'raw': committee_data,
            }

            defaults = {
                'name': name,
                'parliament_term': term,
                'keywords': ', '.join(keywords),
                'metadata': metadata,
            }

            committee, created = Committee.objects.update_or_create(
                external_id=external_id,
                defaults=defaults,
            )

            if created:
                self.stats['committees_created'] += 1
                logger.debug("Created committee: %s", name)
            else:
                self.stats['committees_updated'] += 1
                logger.debug("Updated committee: %s", name)

            return committee

        except Exception as e:
            logger.error("Failed to import committee %s: %s", committee_data.get('id'), e)
            return None

    @staticmethod
    def _extract_committee_keywords(name: str, topics: List[str]) -> List[str]:
        """Extract meaningful keywords from committee name and topics."""
        import re

        # Common German stopwords to exclude
        stopwords = {
            'für', 'und', 'der', 'die', 'das', 'den', 'dem', 'des',
            'ein', 'eine', 'einen', 'einem', 'eines',
            'von', 'zu', 'im', 'am', 'auf', 'mit', 'bei',
            'ausschuss', 'unterausschuss', 'kommission', 'enquetekommission',
            'beirat', 'gremium', 'rat'
        }

        keywords = set()

        # Extract from committee name
        # Split on common delimiters and extract meaningful words
        words = re.findall(r'\b\w+\b', name.lower())
        for word in words:
            if len(word) > 3 and word not in stopwords:
                keywords.add(word)

        # Add topic labels as keywords
        for topic in topics:
            # Clean and add the topic
            topic_clean = topic.lower().strip()
            if topic_clean:
                keywords.add(topic_clean)
                # Also extract words from topic
                topic_words = re.findall(r'\b\w+\b', topic_clean)
                for word in topic_words:
                    if len(word) > 3 and word not in stopwords:
                        keywords.add(word)

        return sorted(list(keywords))

    def _import_committee_membership(
        self,
        membership_data: Dict,
        committee: Committee
    ) -> Optional[CommitteeMembership]:
        """Import a committee membership linking a representative to a committee."""
        try:
            # Get the mandate info to find the representative
            mandate_info = membership_data.get('candidacy_mandate', {})
            mandate_id = str(mandate_info.get('id', ''))

            if not mandate_id:
                logger.warning("Membership %s has no mandate ID", membership_data.get('id'))
                return None

            # Find the representative by external_id (which is the mandate_id)
            try:
                representative = Representative.objects.get(external_id=mandate_id)
            except Representative.DoesNotExist:
                logger.warning(
                    "Representative with mandate ID %s not found for membership %s",
                    mandate_id,
                    membership_data.get('id')
                )
                return None

            # Map API role to our role choices
            api_role = membership_data.get('committee_role', 'member')
            role = self._map_committee_role(api_role)

            # Get additional roles if any
            additional_roles = membership_data.get('committee_roles_additional') or []

            metadata = {
                'api_id': membership_data.get('id'),
                'source': 'abgeordnetenwatch',
                'api_role': api_role,
                'raw': membership_data,
            }

            defaults = {
                'role': role,
                'additional_roles': additional_roles,
                'metadata': metadata,
            }

            membership, created = CommitteeMembership.objects.update_or_create(
                representative=representative,
                committee=committee,
                defaults=defaults,
            )

            if created:
                self.stats['memberships_created'] += 1
                logger.debug(
                    "Created membership: %s -> %s (%s)",
                    representative.full_name,
                    committee.name,
                    role
                )
            else:
                self.stats['memberships_updated'] += 1
                logger.debug(
                    "Updated membership: %s -> %s (%s)",
                    representative.full_name,
                    committee.name,
                    role
                )

            return membership

        except Exception as e:
            logger.error("Failed to import committee membership %s: %s", membership_data.get('id'), e)
            return None

    @staticmethod
    def _map_committee_role(api_role: str) -> str:
        """Map Abgeordnetenwatch committee role to our role choices."""
        role_mapping = {
            'chairperson': 'chair',
            'vice_chairperson': 'deputy_chair',
            'foreperson': 'foreperson',
            'member': 'member',
            'alternate_member': 'alternate_member',
            'spokesperson': 'member',  # Map to member as we don't have spokesperson
            'alternate_spokesperson': 'alternate_member',
            'secretary': 'member',
            'alternate_secretary': 'alternate_member',
            'advisory_member': 'member',
            'eligible_member': 'member',
        }
        return role_mapping.get(api_role, 'member')


# ---------------------------------------------------------------------------
# Identity verification (stub)
# ---------------------------------------------------------------------------


class IdentityVerificationService:
    """Stubbed identity service (kept for API compatibility)."""

    @staticmethod
    def initiate_verification(user, provider='stub_provider') -> Dict[str, str]:
        return {
            'status': 'initiated',
            'provider': provider,
            'verification_url': '/verify/stub/',
            'session_id': 'stub-session',
        }

    @staticmethod
    def complete_verification(user, verification_data: Dict[str, str]) -> Optional['IdentityVerification']:
        from .models import IdentityVerification

        postal_code = (verification_data.get('postal_code') or '').strip()
        located = ConstituencyLocator.locate(postal_code) if postal_code else LocatedConstituencies(None, None, None)
        constituency = located.local or located.state or located.federal

        expires_at_value = verification_data.get('expires_at')
        expires_at = None
        if expires_at_value:
            try:
                candidate = datetime.fromisoformat(expires_at_value)
                expires_at = timezone.make_aware(candidate) if timezone.is_naive(candidate) else candidate
            except (TypeError, ValueError):
                expires_at = None

        defaults = {
            'status': 'VERIFIED',
            'provider': verification_data.get('provider', 'stub_provider'),
            'street_address': verification_data.get('street', ''),
            'postal_code': postal_code,
            'city': verification_data.get('city', ''),
            'state': verification_data.get('state', ''),
            'country': (verification_data.get('country') or 'DE').upper(),
            'verification_data': verification_data,
            'verified_at': timezone.now(),
            'expires_at': expires_at,
        }

        if constituency:
            defaults['constituency'] = constituency
            defaults['parliament_term'] = constituency.parliament_term
            defaults['parliament'] = constituency.parliament_term.parliament

        verification, _ = IdentityVerification.objects.update_or_create(
            user=user,
            defaults=defaults,
        )
        return verification


# ---------------------------------------------------------------------------
# Suggestions (simplified for new schema)
# ---------------------------------------------------------------------------


class ConstituencySuggestionService:
    """Provide lightweight representative/tag suggestions based on title and location."""

    KEYWORD_PATTERN = re.compile(r"[\wÄÖÜäöüß-]+", re.UNICODE)
    MIN_TOKEN_LENGTH = 3
    MAX_TOPICS = 3
    MAX_REPRESENTATIVES = 5
    MAX_TAGS = 5

    @classmethod
    def suggest_from_concern(
        cls,
        concern_text: str,
        user_location: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        tokens = cls._extract_tokens(concern_text)
        location = cls._resolve_location(user_location or {})
        matched_topics = cls._match_topics(tokens)
        primary_topic = matched_topics[0] if matched_topics else None
        representatives = cls._rank_representatives(
            tokens,
            matched_topics,
            location,
            limit=cls.MAX_REPRESENTATIVES,
            primary_topic=primary_topic,
        )
        suggested_tags = cls._match_tags(tokens, matched_topics)
        suggested_level = cls._infer_level(primary_topic, location, tokens)
        explanation = cls._build_explanation(primary_topic, location, tokens)
        constituencies = location.constituencies

        return {
            'suggested_level': suggested_level,
            'primary_topic': primary_topic,
            'matched_topics': matched_topics,
            'representatives': representatives,
            'suggested_constituencies': constituencies,
            'constituencies': constituencies,
            'suggested_tags': suggested_tags,
            'keywords': tokens,
            'explanation': explanation,
        }

    # ------------------------------------------------------------------
    @classmethod
    def _extract_tokens(cls, text: str) -> List[str]:
        if not text:
            return []
        tokens = []
        for raw_token in cls.KEYWORD_PATTERN.findall(text.lower()):
            token = raw_token.strip('-_')
            if len(token) >= cls.MIN_TOKEN_LENGTH:
                tokens.append(token)
        return tokens

    @classmethod
    def _resolve_location(cls, user_location: Dict[str, str]) -> LocationContext:
        postal_code = (user_location.get('postal_code') or '').strip()
        located = ConstituencyLocator.locate(postal_code) if postal_code else LocatedConstituencies(None, None, None)
        constituencies = [
            constituency
            for constituency in (located.local, located.state, located.federal)
            if constituency
        ]

        explicit_state = normalize_german_state(user_location.get('state')) if user_location.get('state') else None
        inferred_state = None
        for constituency in constituencies:
            metadata_state = (constituency.metadata or {}).get('state')
            if metadata_state:
                inferred_state = normalize_german_state(metadata_state)
                if inferred_state:
                    break

        state = explicit_state or inferred_state

        return LocationContext(
            postal_code=postal_code or None,
            state=state,
            constituencies=constituencies,
        )

    @classmethod
    def _match_topics(cls, tokens: List[str]) -> List[TopicArea]:
        if not tokens:
            return []

        topic_query = Q()
        for token in tokens:
            topic_query |= Q(name__icontains=token) | Q(keywords__icontains=token)

        if not topic_query:
            return []

        topics = list(TopicArea.objects.filter(topic_query).distinct())
        if not topics:
            return []

        scores: List[Tuple[int, TopicArea]] = []
        for topic in topics:
            haystack = ' '.join(
                filter(None, [topic.name, topic.description, topic.keywords])
            ).lower()
            score = sum(haystack.count(token) for token in tokens)
            scores.append((score, topic))

        ranked = [topic for score, topic in sorted(scores, key=lambda item: (-item[0], item[1].name)) if score > 0]
        if not ranked:
            ranked = sorted(topics, key=lambda item: item.name)
        return ranked[: cls.MAX_TOPICS]

    @classmethod
    def _topic_terms(cls, topics: List[TopicArea]) -> Set[str]:
        terms: Set[str] = set()
        for topic in topics:
            terms.update(cls._extract_tokens(topic.name))
            if topic.keywords:
                terms.update(cls._extract_tokens(topic.keywords))
        return terms

    @classmethod
    def _rank_representatives(
        cls,
        tokens: List[str],
        matched_topics: List[TopicArea],
        location: LocationContext,
        limit: int,
        primary_topic: Optional[TopicArea] = None,
    ) -> List[Representative]:
        base_qs = Representative.objects.filter(is_active=True).select_related(
            'parliament', 'parliament_term'
        ).prefetch_related(
            'constituencies',
            'committee_memberships__committee'
        )

        location_filter = Q()
        if location.has_constituencies:
            location_filter |= Q(constituencies__in=location.constituencies)
        if location.state:
            location_filter |= Q(constituencies__metadata__state__iexact=location.state) | Q(parliament__region__iexact=location.state)

        if location_filter:
            base_qs = base_qs.filter(location_filter).distinct()

        candidates = list(base_qs[:50])

        if not candidates:
            fallback_qs = Representative.objects.filter(is_active=True)
            inferred_level = cls._infer_level(primary_topic, location, tokens)
            if inferred_level:
                fallback_qs = fallback_qs.filter(parliament__level__iexact=inferred_level)
            fallback_qs = fallback_qs.select_related('parliament', 'parliament_term').prefetch_related('constituencies')
            candidates = list(fallback_qs[:50])

        if not candidates:
            return []

        search_terms = set(tokens)
        search_terms.update(cls._topic_terms(matched_topics))
        search_terms = {term for term in search_terms if len(term) >= cls.MIN_TOKEN_LENGTH}

        constituency_ids = {constituency.id for constituency in location.constituencies}
        scored: List[Tuple[int, Representative]] = []

        for representative in candidates:
            rep_constituencies = list(representative.constituencies.all())
            rep_states = {
                normalize_german_state((constituency.metadata or {}).get('state'))
                for constituency in rep_constituencies
                if (constituency.metadata or {}).get('state')
            }

            matched_constituency = None
            if constituency_ids:
                for constituency in rep_constituencies:
                    if constituency.id in constituency_ids:
                        matched_constituency = constituency
                        break
            if not matched_constituency and location.state:
                for constituency in rep_constituencies:
                    metadata_state = normalize_german_state((constituency.metadata or {}).get('state'))
                    if metadata_state and metadata_state == location.state:
                        matched_constituency = constituency
                        break
            if not matched_constituency and rep_constituencies:
                matched_constituency = rep_constituencies[0]
            representative.suggested_constituency = matched_constituency

            focus_blob = ' '.join(filter(None, [representative.party, representative.focus_areas or ''])).lower()

            # Build committee keywords blob
            committee_keywords = []
            for membership in representative.committee_memberships.all():
                if membership.committee.keywords:
                    committee_keywords.extend(membership.committee.get_keywords_list())
            committee_blob = ' '.join(committee_keywords).lower()

            score = 0
            direct_state_match = False
            if constituency_ids and any(c.id in constituency_ids for c in rep_constituencies):
                score += 6
                if representative.election_mode == 'DIRECT':
                    score += 10
            elif location.state and location.state in rep_states:
                score += 3
                if representative.election_mode == 'DIRECT':
                    score += 10
                    direct_state_match = True

            # Score based on focus areas
            for term in search_terms:
                if term and term in focus_blob:
                    score += 2

            # Score based on committee work - higher weight for committee expertise
            for term in search_terms:
                if term and term in committee_blob:
                    score += 4  # Higher score for committee expertise

            if representative.election_mode == 'DIRECT' and not direct_state_match:
                score += 2

            scored.append((score, representative))

        scored.sort(key=lambda item: (-item[0], item[1].last_name, item[1].first_name))

        ranked = [rep for score, rep in scored if score > 0][:limit]
        if len(ranked) < limit:
            supplemental = [rep for score, rep in scored if rep not in ranked][: limit - len(ranked)]
            ranked.extend(supplemental)
        return ranked[:limit]

    @classmethod
    def _match_tags(cls, tokens: List[str], matched_topics: List[TopicArea]) -> List[Tag]:
        search_terms = set(tokens)
        search_terms.update(cls._topic_terms(matched_topics))
        if not search_terms:
            return []

        tag_query = Q()
        for term in search_terms:
            tag_query |= Q(name__icontains=term) | Q(slug__icontains=term)

        if not tag_query:
            return []

        candidates = list(Tag.objects.filter(tag_query).distinct())
        if not candidates:
            return []

        scored: List[Tuple[int, Tag]] = []
        for tag in candidates:
            name_lower = tag.name.lower()
            slug_lower = tag.slug.lower()
            score = 0
            for term in search_terms:
                if term in name_lower:
                    score += 2
                elif term in slug_lower:
                    score += 1
            scored.append((score, tag))

        scored.sort(key=lambda item: (-item[0], item[1].name))
        ranked = [tag for score, tag in scored if score > 0][: cls.MAX_TAGS]
        if len(ranked) < cls.MAX_TAGS:
            ranked.extend(
                [tag for score, tag in scored if tag not in ranked][: cls.MAX_TAGS - len(ranked)]
            )
        return ranked

    @classmethod
    def _infer_level(
        cls,
        primary_topic: Optional[TopicArea],
        location: LocationContext,
        tokens: List[str],
    ) -> str:
        if primary_topic and primary_topic.primary_level:
            return primary_topic.primary_level
        if location.has_constituencies:
            parliament = location.constituencies[0].parliament_term.parliament
            return parliament.level
        if location.state:
            return 'STATE'
        if any(term in {'eu', 'europa', 'brüssel'} for term in tokens):
            return 'EU'
        return 'FEDERAL'

    @classmethod
    def _build_explanation(
        cls,
        primary_topic: Optional[TopicArea],
        location: LocationContext,
        tokens: List[str],
    ) -> str:
        parts: List[str] = []
        if primary_topic:
            parts.append(
                _('Detected policy area: %(topic)s.') % {'topic': primary_topic.name}
            )
        if location.has_constituencies:
            constituency_label = ', '.join({c.name for c in location.constituencies})
            parts.append(
                _('Prioritising representatives for %(constituencies)s.')
                % {'constituencies': constituency_label}
            )
        elif location.state:
            parts.append(
                _('Filtering by state %(state)s.') % {'state': location.state}
            )
        elif location.postal_code:
            parts.append(
                _('Postal code %(plz)s had no direct match; showing broader representatives.')
                % {'plz': location.postal_code}
            )
        if not parts:
            parts.append(_('Showing generally relevant representatives.'))
        return ' '.join(parts)

    @staticmethod
    def get_example_queries() -> List[Dict[str, str]]:
        return [
            {
                'query': 'Investitionen in den öffentlichen Nahverkehr in Berlin',
                'expected_level': 'STATE',
                'topic': 'Verkehr / ÖPNV',
            },
            {
                'query': 'Klimaschutzgesetz und CO2 Ziele für Deutschland',
                'expected_level': 'FEDERAL',
                'topic': 'Klimaschutz',
            },
            {
                'query': 'Mehr Unterstützung für unsere lokale Grundschule',
                'expected_level': 'STATE',
                'topic': 'Bildung',
            },
            {
                'query': 'EU Datenschutzrichtlinien müssen verbessert werden',
                'expected_level': 'EU',
                'topic': 'Datenschutz',
            },
        ]


class TopicSuggestionService:
    """Expose topic-based suggestions for external callers."""

    @staticmethod
    def suggest_representatives_for_concern(
        concern_text: str,
        user_address: Optional[Dict[str, str]] = None,
        limit: int = 5,
    ) -> Dict[str, Any]:
        suggestion = ConstituencySuggestionService.suggest_from_concern(
            concern_text,
            user_location=user_address,
        )
        return {
            'matched_topics': suggestion.get('matched_topics', []),
            'suggested_level': suggestion.get('suggested_level'),
            'suggested_constituencies': suggestion.get('suggested_constituencies', []),
            'suggested_representatives': suggestion.get('representatives', [])[:limit],
            'suggested_tags': suggestion.get('suggested_tags', []),
            'explanation': suggestion.get('explanation'),
        }
