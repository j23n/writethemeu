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
import mimetypes
from datetime import datetime, date
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests
from tqdm import tqdm
from django.db import transaction
from django.db.models import Q
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.html import strip_tags

from .constants import GERMAN_STATE_ALIASES, normalize_german_state, normalize_party_name
from .models import (
    Committee,
    CommitteeMembership,
    Constituency,
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
    def get_politician(cls, politician_id: int) -> Dict:
        return cls._request(f'politicians/{politician_id}')['data']

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
            'photos_downloaded': 0,
        }
        self._politician_cache: Dict[str, Dict[str, Any]] = {}
        self._photo_url_cache: Dict[str, Optional[str]] = {}

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
        for mandate in tqdm(mandates, desc="Bundestag representatives", unit="rep"):
            self._import_representative(mandate, parliament, term)
        self._sync_committees_for_term(term)

    def _sync_eu(self, parliament_data: Dict[str, Any]) -> None:
        logger.info("Syncing EU parliament representatives …")
        parliament, term = self._ensure_parliament_and_term(parliament_data, level='EU', region='EU')
        mandates = self._fetch_active_mandates(term)
        for mandate in tqdm(mandates, desc="EU Parliament representatives", unit="rep"):
            self._import_representative(mandate, parliament, term)
        self._sync_committees_for_term(term)

    def _sync_state(self, parliament_data: Dict[str, Any]) -> None:
        label = parliament_data.get('label', '')
        logger.info("Syncing Landtag representatives for %s …", label)
        region = normalize_german_state(label)
        parliament, term = self._ensure_parliament_and_term(parliament_data, level='STATE', region=region)
        mandates = self._fetch_active_mandates(term)
        for mandate in tqdm(mandates, desc=f"{label} representatives", unit="rep"):
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
        parliament.last_synced_at = timezone.now()
        parliament.save(update_fields=['last_synced_at'])
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
        term.last_synced_at = timezone.now()
        term.save(update_fields=['last_synced_at'])
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

    def _get_politician_details(self, politician_id: Optional[int]) -> Dict[str, Any]:
        if not politician_id:
            return {}
        cache_key = str(politician_id)
        if cache_key in self._politician_cache:
            return self._politician_cache[cache_key]
        try:
            details = AbgeordnetenwatchAPI.get_politician(politician_id)
        except Exception:
            logger.warning("Failed to fetch politician %s", politician_id, exc_info=True)
            details = {}
        self._politician_cache[cache_key] = details
        return details

    def _find_photo_url(self, politician: Dict[str, Any]) -> Optional[str]:
        image_data = politician.get('image')
        candidates: List[str] = []
        if isinstance(image_data, dict):
            candidates.extend([
                image_data.get('url'),
                image_data.get('original'),
                image_data.get('source'),
            ])
            versions = image_data.get('versions')
            if isinstance(versions, dict):
                for value in versions.values():
                    if isinstance(value, str):
                        candidates.append(value)
                    elif isinstance(value, dict):
                        candidates.append(value.get('url'))
        for candidate in candidates:
            if candidate:
                return candidate

        profile_url = politician.get('abgeordnetenwatch_url') or politician.get('url')
        if not profile_url:
            return None
        if profile_url in self._photo_url_cache:
            return self._photo_url_cache[profile_url]
        try:
            response = requests.get(profile_url, timeout=30)
            response.raise_for_status()
        except requests.RequestException:
            logger.debug("Failed to load profile page for %s", profile_url, exc_info=True)
            self._photo_url_cache[profile_url] = None
            return None

        match = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', response.text)
        if not match:
            match = re.search(r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"', response.text)
        photo_url = match.group(1) if match else None
        self._photo_url_cache[profile_url] = photo_url
        return photo_url

    def _download_representative_image(self, photo_url: Optional[str], representative: Representative) -> Optional[str]:
        if not photo_url:
            return None
        try:
            response = requests.get(photo_url, timeout=30)
            response.raise_for_status()
        except requests.RequestException:
            logger.warning("Failed to download photo for %s", representative.full_name, exc_info=True)
            return None

        content_type = (response.headers.get('Content-Type') or '').split(';')[0]
        extension = None
        if content_type:
            extension = mimetypes.guess_extension(content_type)
        if extension in ('.jpe', '.jpeg'):
            extension = '.jpg'
        if not extension:
            extension = Path(photo_url).suffix.split('?')[0] or '.jpg'
        if not extension.startswith('.'):
            extension = f'.{extension}'
        if extension.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
            extension = '.jpg'

        media_dir = Path(settings.MEDIA_ROOT) / 'representatives'
        media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{representative.external_id}{extension}"
        file_path = media_dir / filename
        file_path.write_bytes(response.content)
        self.stats['photos_downloaded'] += 1
        return f"representatives/{filename}"

    def _ensure_photo_reference(self, representative: Representative) -> Optional[Path]:
        if representative.photo_path:
            candidate = Path(settings.MEDIA_ROOT) / representative.photo_path
            if candidate.exists():
                return candidate

        media_dir = Path(settings.MEDIA_ROOT) / 'representatives'
        if not media_dir.exists():
            return None

        for candidate in sorted(media_dir.glob(f"{representative.external_id}.*")):
            if candidate.suffix.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
                continue
            representative.photo_path = f"representatives/{candidate.name}"
            representative.photo_updated_at = representative.photo_updated_at or timezone.now()
            representative.save(update_fields=['photo_path', 'photo_updated_at'])
            return candidate
        return None

    @staticmethod
    def _clean_text(value: Any) -> str:
        if not isinstance(value, str):
            return ''
        return strip_tags(value).strip()

    def _extract_biography(self, politician: Dict[str, Any]) -> str:
        profile = politician.get('profile') or {}
        for key in ('short_description', 'intro', 'text', 'description'):
            bio = profile.get(key) or politician.get(key)
            cleaned = self._clean_text(bio)
            if cleaned:
                return cleaned
        return ''

    def _extract_focus_topics(self, politician: Dict[str, Any]) -> List[str]:
        topics: List[str] = []
        seen: Set[str] = set()

        sources = []
        if isinstance(politician.get('politician_topics'), list):
            sources.append(politician['politician_topics'])
        activity_topics = (politician.get('activity') or {}).get('topics')
        if isinstance(activity_topics, list):
            sources.append(activity_topics)

        for source in sources:
            for topic in source:
                if not isinstance(topic, dict):
                    continue
                label = topic.get('label')
                if not label and isinstance(topic.get('topic'), dict):
                    label = topic['topic'].get('label')
                cleaned = self._clean_text(label)
                if cleaned and cleaned not in seen:
                    seen.add(cleaned)
                    topics.append(cleaned)
        return topics

    def _extract_links(self, politician: Dict[str, Any]) -> List[Dict[str, str]]:
        links: List[Dict[str, str]] = []
        for entry in politician.get('links') or []:
            if not isinstance(entry, dict):
                continue
            url = entry.get('url')
            if not url:
                continue
            label = entry.get('label') or entry.get('type') or url
            links.append({'label': label, 'url': url})
        return links

    # --------------------------------------
    def _import_representative(self, mandate: Dict, parliament: Parliament, term: ParliamentTerm) -> None:
        electoral = mandate.get('electoral_data') or {}
        politician = mandate.get('politician') or {}
        mandate_id = str(mandate.get('id'))
        politician_id = politician.get('id')
        detailed_politician = self._get_politician_details(politician_id)
        if detailed_politician:
            politician = {**politician, **detailed_politician}
        first_name, last_name = self._split_name(politician.get('label', ''))
        party_name = normalize_party_name(self._extract_party_name(mandate))
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

        metadata = dict(defaults['metadata'])
        biography = self._extract_biography(politician)
        if biography:
            metadata['biography'] = biography
        focus_topics = self._extract_focus_topics(politician)
        if focus_topics:
            metadata['focus_topics'] = focus_topics
        links = self._extract_links(politician)
        if links:
            metadata['links'] = links
        defaults['metadata'] = metadata

        rep, created = Representative.objects.update_or_create(
            external_id=mandate_id,
            defaults=defaults,
        )
        rep.last_synced_at = timezone.now()
        rep.save(update_fields=['last_synced_at'])
        if created:
            self.stats['representatives_created'] += 1
        else:
            self.stats['representatives_updated'] += 1

        rep.constituencies.clear()
        for constituency in self._determine_constituencies(parliament, term, electoral, rep):
            rep.constituencies.add(constituency)

        if not self.dry_run:
            existing_photo_path = self._ensure_photo_reference(rep)
            needs_download = not (existing_photo_path and existing_photo_path.exists())
            if needs_download:
                photo_url = self._find_photo_url(politician)
                photo_path = self._download_representative_image(photo_url, rep) if photo_url else None
                if photo_path and rep.photo_path != photo_path:
                    rep.photo_path = photo_path
                    rep.photo_updated_at = timezone.now()
                    rep.save(update_fields=['photo_path', 'photo_updated_at'])
            else:
                self._ensure_photo_reference(rep)

        if focus_topics and not rep.focus_areas:
            rep.focus_areas = ', '.join(focus_topics)
            rep.save(update_fields=['focus_areas'])

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

        scope = 'FEDERAL_DISTRICT' if parliament.level == 'FEDERAL' else 'STATE_DISTRICT'
        constituency = self._get_or_create_constituency(
            term,
            scope=scope,
            name=district_name,
            external_id=district_id,
            metadata={'state': state_name}
        )
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
        constituency.last_synced_at = timezone.now()
        constituency.save(update_fields=['last_synced_at'])
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
        for committee_data in tqdm(committees_data, desc=f"Committees for {term.name}", unit="committee"):
            committee = self._import_committee(committee_data, term)
            if committee:
                committee_map[committee_data['id']] = committee

        # Fetch committee memberships for each committee
        logger.info("Syncing committee memberships for %s (fetching %d committees) …", term, len(committee_map))

        # Fetch memberships for each committee individually to avoid timeout
        for committee_id, committee in tqdm(committee_map.items(), desc="Committee memberships", unit="committee"):
            try:
                memberships_data = AbgeordnetenwatchAPI.fetch_paginated(
                    'committee-memberships',
                    {'committee': committee_id}
                )

                for membership_data in memberships_data:
                    self._import_committee_membership(membership_data, committee)

            except Exception as e:
                logger.error("Failed to fetch memberships for committee %s: %s", committee_id, e)

        self._map_committees_to_topics()
        self._update_representative_topics(term)

    def _import_committee(self, committee_data: Dict, term: ParliamentTerm) -> Optional[Committee]:
        """Import a single committee from API data."""
        try:
            external_id = str(committee_data.get('id'))
            name = committee_data.get('label', '')

            if not name:
                logger.warning("Committee %s has no label, skipping", external_id)
                return None

            # Extract topic information
            topics = committee_data.get('field_topics') or []
            topic_labels = [t.get('label', '') for t in topics if isinstance(t, dict)]

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
            committee.last_synced_at = timezone.now()
            committee.save(update_fields=['last_synced_at'])

            if created:
                self.stats['committees_created'] += 1
                logger.debug("Created committee: %s", name)
            else:
                self.stats['committees_updated'] += 1
                logger.debug("Updated committee: %s", name)

            topic_objs: List[TopicArea] = []
            for topic in topics:
                if isinstance(topic, dict):
                    label = (topic.get('label') or '').strip()
                else:
                    label = str(topic).strip()
                if not label:
                    continue
                topic_obj = TopicArea.objects.filter(name__iexact=label).first()
                if topic_obj:
                    topic_objs.append(topic_obj)
            if topic_objs:
                committee.topic_areas.set(topic_objs)
            elif created:
                committee.topic_areas.clear()

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
            membership.last_synced_at = timezone.now()
            membership.save(update_fields=['last_synced_at'])

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

    def _update_representative_topics(self, term: ParliamentTerm) -> None:
        """Update representative topic areas based on committee assignments."""
        reps = term.representatives.prefetch_related(
            'committee_memberships__committee__topic_areas'
        )
        for rep in reps:
            topic_ids: Set[int] = set()
            for membership in rep.committee_memberships.all():
                topic_ids.update(
                    membership.committee.topic_areas.values_list('id', flat=True)
                )
            if topic_ids:
                rep.topic_areas.set(topic_ids)
            else:
                rep.topic_areas.clear()

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

    def _map_committees_to_topics(self) -> None:
        """Map committees to TopicAreas based on keyword overlap."""
        logger.info("Mapping committees to TopicAreas based on keyword overlap...")

        committees = Committee.objects.select_related('parliament_term__parliament').all()

        # Define topic types by parliament level
        level_to_competency = {
            'FEDERAL': ['EXCLUSIVE', 'CONCURRENT', 'DEVIATION', 'JOINT'],
            'STATE': ['RESIDUAL', 'CONCURRENT', 'DEVIATION', 'JOINT'],
            'EU': ['SHARED', 'EXCLUSIVE'],
        }

        mapped_count = 0
        total_mappings = 0

        for committee in committees:
            committee_keywords = set(committee.get_keywords_list())
            if not committee_keywords:
                continue

            # Determine which TopicAreas are relevant for this committee's parliament level
            parliament_level = committee.parliament_term.parliament.level
            competency_types = level_to_competency.get(parliament_level, [])

            if not competency_types:
                logger.debug(
                    "No competency types defined for level %s, skipping committee %s",
                    parliament_level,
                    committee.name
                )
                continue

            topic_areas = TopicArea.objects.filter(competency_type__in=competency_types)

            matched_topics = []
            for topic in topic_areas:
                topic_keywords = set(topic.get_keywords_list())
                overlap = committee_keywords & topic_keywords

                if len(overlap) >= 1:
                    matched_topics.append(topic)

            if matched_topics:
                committee.topic_areas.set(matched_topics)
                mapped_count += 1
                total_mappings += len(matched_topics)

        logger.info(
            "Committee-to-topic mapping complete: %d committees mapped to %d total topics",
            mapped_count,
            total_mappings
        )
        self.stats['committees_mapped'] = mapped_count
        self.stats['committee_topic_mappings'] = total_mappings


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
            'verification_type': 'THIRD_PARTY',
        }

        defaults['constituency'] = constituency
        defaults['federal_constituency'] = located.federal
        defaults['state_constituency'] = located.state

        verification, _ = IdentityVerification.objects.update_or_create(
            user=user,
            defaults=defaults,
        )
        verification._update_parliament_links()
        verification.save(update_fields=[
            'provider',
            'status',
            'street_address',
            'postal_code',
            'city',
            'state',
            'country',
            'verification_data',
            'verified_at',
            'expires_at',
            'constituency',
            'federal_constituency',
            'state_constituency',
            'parliament_term',
            'parliament',
            'verification_type',
        ])
        return verification

    @staticmethod
    def self_declare(
        user,
        federal_constituency: Optional['Constituency'] = None,
        state_constituency: Optional['Constituency'] = None,
    ) -> Optional['IdentityVerification']:
        from .models import IdentityVerification

        verification, _ = IdentityVerification.objects.get_or_create(
            user=user,
            defaults={'provider': 'self_declared'}
        )

        verification.provider = 'self_declared'
        verification.status = 'SELF_DECLARED'
        verification.verification_type = 'SELF_DECLARED'
        verification.federal_constituency = federal_constituency
        verification.state_constituency = state_constituency
        verification.constituency = federal_constituency or state_constituency

        state_value = verification.state
        for constituency in filter(None, [federal_constituency, state_constituency]):
            metadata_state = (constituency.metadata or {}).get('state') if constituency.metadata else None
            if metadata_state:
                state_value = metadata_state
                break

        if state_value:
            verification.state = state_value
        verification.country = verification.country or 'DE'
        verification.verified_at = timezone.now()
        verification.expires_at = None

        verification_data = verification.verification_data or {}
        verification_data['self_declared'] = True
        if federal_constituency:
            verification_data['federal_constituency_id'] = federal_constituency.id
        if state_constituency:
            verification_data['state_constituency_id'] = state_constituency.id
        verification.verification_data = verification_data

        verification._update_parliament_links()
        verification.save()
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

    STOPWORDS = {
        'und', 'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einer', 'einem',
        'für', 'mit', 'von', 'auf', 'bei', 'aus', 'zur', 'zum', 'vom', 'beim', 'ans',
        'ist', 'sind', 'war', 'waren', 'wird', 'werden', 'hat', 'haben', 'kann', 'können',
        'soll', 'sollen', 'muss', 'müssen', 'darf', 'dürfen', 'will', 'wollen',
        'ich', 'du', 'er', 'sie', 'es', 'wir', 'ihr', 'man', 'wie', 'was', 'wer', 'aber',
        'auch', 'nur', 'noch', 'mehr', 'sehr', 'als', 'bis', 'oder', 'doch', 'denn',
    }

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

        relevant_parliament_ids = cls._determine_relevant_parliament_ids(matched_topics, location)

        direct_reps = cls._get_direct_representatives(location, relevant_parliament_ids, limit=5)

        expert_reps = cls._get_expert_representatives(
            tokens,
            matched_topics,
            location,
            relevant_parliament_ids,
            exclude_ids={r.id for r in direct_reps},
            limit=15
        )

        representatives = direct_reps + expert_reps

        suggested_tags = cls._match_tags(tokens, matched_topics)
        suggested_level = cls._infer_level(primary_topic, location, tokens)
        explanation = cls._build_explanation(primary_topic, location, tokens)
        constituencies = location.filtered_constituencies(relevant_parliament_ids) or location.constituencies

        return {
            'suggested_level': suggested_level,
            'primary_topic': primary_topic,
            'matched_topics': matched_topics,
            'representatives': representatives,  # Keep for backward compatibility
            'direct_representatives': direct_reps,
            'expert_representatives': expert_reps,
            'suggested_constituencies': constituencies,
            'constituencies': constituencies,
            'suggested_tags': suggested_tags,
            'keywords': tokens,
            'explanation': explanation,
            'parliament_ids': list(relevant_parliament_ids),
        }

    # ------------------------------------------------------------------
    @classmethod
    def _extract_tokens(cls, text: str) -> List[str]:
        if not text:
            return []
        tokens = []
        for raw_token in cls.KEYWORD_PATTERN.findall(text.lower()):
            token = raw_token.strip('-_')
            if len(token) >= cls.MIN_TOKEN_LENGTH and token not in cls.STOPWORDS:
                tokens.append(token)
        return tokens

    @classmethod
    def _resolve_location(cls, user_location: Dict[str, str]) -> LocationContext:
        postal_code = (user_location.get('postal_code') or '').strip()
        constituencies: List[Constituency] = []

        provided_constituencies = user_location.get('constituencies')
        if provided_constituencies:
            iterable = provided_constituencies if isinstance(provided_constituencies, (list, tuple, set)) else [provided_constituencies]
            for item in iterable:
                constituency = None
                if isinstance(item, Constituency):
                    constituency = item
                else:
                    try:
                        constituency_id = int(item)
                    except (TypeError, ValueError):
                        constituency_id = None
                    if constituency_id:
                        constituency = Constituency.objects.filter(id=constituency_id).first()
                if constituency and all(c.id != constituency.id for c in constituencies):
                    constituencies.append(constituency)

        if not constituencies and postal_code:
            located = ConstituencyLocator.locate(postal_code)
            constituencies.extend(
                constituency
                for constituency in (located.local, located.state, located.federal)
                if constituency
            )
        else:
            located = LocatedConstituencies(None, None, None)

        explicit_state = normalize_german_state(user_location.get('state')) if user_location.get('state') else None
        inferred_state = None
        for constituency in constituencies:
            metadata_state = (constituency.metadata or {}).get('state') if constituency.metadata else None
            if metadata_state:
                inferred_state = normalize_german_state(metadata_state)
                if inferred_state:
                    break

        if not inferred_state and postal_code and not constituencies and located.state:
            metadata_state = (located.state.metadata or {}).get('state') if located.state and located.state.metadata else None
            if metadata_state:
                inferred_state = normalize_german_state(metadata_state)

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
            # Use word boundary matching to avoid substring false positives
            score = 0
            for token in tokens:
                # Match token as whole word (surrounded by word boundaries)
                pattern = r'\b' + re.escape(token) + r'\b'
                matches = re.findall(pattern, haystack)
                score += len(matches)
            scores.append((score, topic))

        ranked = [topic for score, topic in sorted(scores, key=lambda item: (-item[0], item[1].name)) if score > 0]
        if not ranked:
            ranked = sorted(topics, key=lambda item: item.name)
        return ranked[: cls.MAX_TOPICS]

    @classmethod
    def _determine_relevant_parliament_ids(
        cls,
        topics: List[TopicArea],
        location: LocationContext,
    ) -> Set[int]:
        parliament_ids: Set[int] = set()
        location_parliament_ids = location.parliament_ids()
        state_code = location.state

        def add_state_parliaments():
            if not state_code:
                return
            state_matches = Parliament.objects.filter(
                level='STATE',
                region__iexact=state_code
            ).values_list('id', flat=True)
            parliament_ids.update(state_matches)

        def add_federal_parliaments():
            federal_matches = Parliament.objects.filter(level='FEDERAL').values_list('id', flat=True)
            parliament_ids.update(federal_matches)

        for topic in topics:
            level = topic.primary_level
            competency = topic.competency_type

            if level == 'EU' and competency == 'EXCLUSIVE':
                eu_ids = Parliament.objects.filter(level='EU').values_list('id', flat=True)
                parliament_ids.update(eu_ids)
                continue

            if level == 'EU' and competency == 'SHARED':
                eu_ids = Parliament.objects.filter(level='EU').values_list('id', flat=True)
                parliament_ids.update(eu_ids)
                add_federal_parliaments()
                continue

            if level == 'FEDERAL' and competency == 'EXCLUSIVE':
                add_federal_parliaments()
                continue

            if level == 'FEDERAL' and competency in {'CONCURRENT', 'JOINT'}:
                add_federal_parliaments()
                add_state_parliaments()
                continue

            if level == 'FEDERAL' and competency == 'DEVIATION':
                add_state_parliaments()
                add_federal_parliaments()
                continue

            if level == 'STATE' and competency in {'STATE', 'RESIDUAL'}:
                add_state_parliaments()
                continue

        if not parliament_ids:
            parliament_ids.update(location_parliament_ids)

        if not parliament_ids:
            add_federal_parliaments()

        if parliament_ids and location_parliament_ids:
            intersection = parliament_ids & location_parliament_ids
            if intersection:
                parliament_ids = intersection

        return parliament_ids

    @classmethod
    def _topic_terms(cls, topics: List[TopicArea]) -> Set[str]:
        terms: Set[str] = set()
        for topic in topics:
            terms.update(cls._extract_tokens(topic.name))
            if topic.keywords:
                terms.update(cls._extract_tokens(topic.keywords))
        return terms

    @classmethod
    def _split_representatives(
        cls,
        representatives: List[Representative],
        location: LocationContext
    ) -> Tuple[List[Representative], List[Representative]]:
        """
        Split representatives into two groups:
        1. Direct representatives: Those with geographic connection to user
        2. Subject experts: Those with relevant committee expertise
        """
        direct_reps = []
        expert_reps = []

        constituency_ids = {c.id for c in location.constituencies}

        for rep in representatives:
            is_direct = cls._is_direct_representative(rep, location, constituency_ids)

            if is_direct:
                direct_reps.append(rep)
            else:
                # Only include in experts if they have committee memberships
                if rep.committee_memberships.exists():
                    expert_reps.append(rep)

        return direct_reps, expert_reps

    @classmethod
    def _is_direct_representative(
        cls,
        representative: Representative,
        location: LocationContext,
        constituency_ids: Set[int]
    ) -> bool:
        """
        Determine if a representative is a 'direct' representative for the user.
        Direct means: represents a specific geographic area (constituency or state),
        not a general list representative.
        """
        # Federal-wide list representatives represent everyone, not direct
        if representative.election_mode == 'FEDERAL_LIST':
            return False

        # EU representatives represent all EU citizens, not direct
        if representative.election_mode == 'EU_LIST':
            return False

        # Representatives explicitly linked to one of the user's constituencies qualify
        rep_constituencies = list(representative.constituencies.all())
        rep_constituency_ids = {c.id for c in rep_constituencies}
        if constituency_ids & rep_constituency_ids:
            return True

        # Only list mandates can fall back to the overall state alignment
        if location.state and representative.election_mode in {'STATE_LIST', 'STATE_REGIONAL_LIST'}:
            rep_states = {
                normalize_german_state((c.metadata or {}).get('state'))
                for c in rep_constituencies
                if (c.metadata or {}).get('state')
            }
            if location.state in rep_states:
                return True

        return False

    @classmethod
    def _get_direct_representatives(
        cls,
        location: LocationContext,
        parliament_ids: Set[int],
        limit: int = 5
    ) -> List[Representative]:
        """
        Get direct representatives based purely on geographic location.
        Returns representatives from the user's constituency/state regardless of topic.
        Only includes direct mandate representatives (DIRECT election mode).
        """
        if not location.has_constituencies and not location.state:
            return []

        base_qs = Representative.objects.filter(
            is_active=True,
            election_mode='DIRECT'
        ).select_related(
            'parliament', 'parliament_term'
        ).prefetch_related(
            'constituencies',
            'topic_areas',
            'committee_memberships__committee',
            'committee_memberships__committee__topic_areas'
        )

        if parliament_ids:
            base_qs = base_qs.filter(parliament_id__in=parliament_ids)

        relevant_constituencies = location.filtered_constituencies(parliament_ids)
        if relevant_constituencies:
            constituencies = relevant_constituencies
        elif parliament_ids:
            constituencies = []
        else:
            constituencies = location.constituencies

        location_filter = Q()
        if constituencies:
            location_filter |= Q(constituencies__in=constituencies)
        if location.state:
            location_filter |= Q(constituencies__metadata__state__iexact=location.state) | Q(parliament__region__iexact=location.state)

        candidates = list(base_qs.filter(location_filter).distinct()[:50])

        if not candidates:
            return []

        constituency_ids = {c.id for c in constituencies}
        direct_reps = []

        for rep in candidates:
            if cls._is_direct_representative(rep, location, constituency_ids):
                rep_constituencies = list(rep.constituencies.all())
                rep_constituency_ids = {c.id for c in rep_constituencies}
                # Set suggested constituency
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
                rep.suggested_constituency = matched_constituency
                rep._primary_constituency_match = bool(rep_constituency_ids & constituency_ids)
                direct_reps.append(rep)

        # Prioritise constituency matches (all are already DIRECT election mode)
        def direct_rank(rep: Representative) -> Tuple[int, str, str]:
            primary_match = getattr(rep, '_primary_constituency_match', False)
            priority = 0 if primary_match else 1
            return (priority, rep.last_name, rep.first_name)

        direct_reps.sort(key=direct_rank)

        return direct_reps[:limit]

    @classmethod
    def _get_expert_representatives(
        cls,
        tokens: List[str],
        matched_topics: List[TopicArea],
        location: LocationContext,
        parliament_ids: Set[int],
        exclude_ids: Set[int],
        limit: int = 15
    ) -> List[Representative]:
        """
        Get expert representatives based on topic expertise.
        Simply returns representatives who have the matched TopicAreas assigned.
        """
        if not matched_topics:
            return []

        # Find representatives with the matched topic areas
        reps = Representative.objects.filter(
            is_active=True,
            topic_areas__in=matched_topics
        ).exclude(
            id__in=exclude_ids
        ).select_related(
            'parliament', 'parliament_term'
        ).prefetch_related(
            'constituencies',
            'committee_memberships__committee__topic_areas'
        ).distinct()

        if parliament_ids:
            reps = reps.filter(parliament_id__in=parliament_ids)

        # Enrich with metadata and score for sorting
        scored_reps = []
        for rep in reps:
            # Find a relevant committee
            matched_topic_ids = {t.id for t in matched_topics}
            relevant_committees = []
            best_score = 0

            for membership in rep.committee_memberships.all():
                committee_topic_ids = set(membership.committee.topic_areas.values_list('id', flat=True))
                if committee_topic_ids & matched_topic_ids:
                    relevant_committees.append(membership)
                    # Score based on role
                    role_scores = {
                        'chair': 3,
                        'deputy_chair': 2,
                        'foreperson': 2,
                        'member': 1,
                        'alternate_member': 0,
                    }
                    score = role_scores.get(membership.role, 0)
                    best_score = max(best_score, score)

            rep.relevant_committees = relevant_committees[:1]
            rep.committee_score = best_score

            # Set suggested constituency
            rep_constituencies = list(rep.constituencies.all())
            rep.suggested_constituency = rep_constituencies[0] if rep_constituencies else None

            scored_reps.append(rep)

        # Sort by committee score (higher first), then by name
        scored_reps.sort(key=lambda r: (-r.committee_score, r.last_name, r.first_name))

        return scored_reps[:limit]

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
            'topic_areas',
            'committee_memberships__committee',
            'committee_memberships__committee__topic_areas'
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
            fallback_qs = fallback_qs.select_related('parliament', 'parliament_term').prefetch_related(
                'constituencies',
                'topic_areas',
                'committee_memberships__committee',
                'committee_memberships__committee__topic_areas'
            )
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

            is_direct = cls._is_direct_representative(representative, location, constituency_ids)

            # Calculate geographic relevance score (for direct representatives)
            geo_score = 0
            if is_direct:
                if constituency_ids and any(c.id in constituency_ids for c in rep_constituencies):
                    geo_score += 20  # Exact constituency match
                elif location.state and location.state in rep_states:
                    geo_score += 10  # State match

            # Calculate subject expertise score (for all representatives)
            expertise_score = 0

            # Committee expertise (primary indicator)
            committee_keywords = []
            for membership in representative.committee_memberships.all():
                if membership.committee.keywords:
                    committee_keywords.extend(membership.committee.get_keywords_list())
            committee_blob = ' '.join(committee_keywords).lower()

            for term in search_terms:
                if term and term in committee_blob:
                    expertise_score += 5

            # Focus areas (secondary indicator)
            focus_blob = ' '.join(filter(None, [representative.party, representative.focus_areas or ''])).lower()
            for term in search_terms:
                if term and term in focus_blob:
                    expertise_score += 2

            # Total score combines geography and expertise
            score = geo_score + expertise_score

            # Store separate scores for potential display/sorting
            representative.geo_score = geo_score
            representative.expertise_score = expertise_score

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


class CommitteeTopicMappingService:
    """Maps committees to TopicAreas based on keyword overlap."""

    MIN_KEYWORD_OVERLAP = 1

    @classmethod
    def map_all_committees(cls, min_overlap: int = MIN_KEYWORD_OVERLAP) -> Dict[str, Any]:
        """
        Map all committees to their relevant TopicAreas based on keyword overlap.

        Args:
            min_overlap: Minimum number of overlapping keywords required for a match

        Returns:
            Dictionary with mapping statistics and details
        """
        committees = Committee.objects.all()
        federal_types = ['EXCLUSIVE', 'CONCURRENT', 'DEVIATION', 'JOINT']
        topic_areas = TopicArea.objects.filter(competency_type__in=federal_types)

        stats = {
            'total_committees': 0,
            'mapped_committees': 0,
            'total_mappings': 0,
            'committees_by_topic_count': {},
            'details': []
        }

        for committee in tqdm(committees, desc="Mapping committees to topics", unit="committee"):
            committee_keywords = set(committee.get_keywords_list())
            if not committee_keywords:
                continue

            stats['total_committees'] += 1
            matched_topics = []

            for topic in topic_areas:
                topic_keywords = set(topic.get_keywords_list())
                overlap = committee_keywords & topic_keywords

                if len(overlap) >= min_overlap:
                    matched_topics.append({
                        'topic': topic,
                        'overlap_count': len(overlap),
                        'overlap_keywords': sorted(overlap)
                    })

            if matched_topics:
                matched_topics.sort(key=lambda x: x['overlap_count'], reverse=True)

                committee.topic_areas.set([m['topic'] for m in matched_topics])

                stats['mapped_committees'] += 1
                stats['total_mappings'] += len(matched_topics)

                topic_count = len(matched_topics)
                stats['committees_by_topic_count'][topic_count] = \
                    stats['committees_by_topic_count'].get(topic_count, 0) + 1

                stats['details'].append({
                    'committee': committee.name,
                    'committee_keywords': sorted(committee_keywords),
                    'matched_topics': [
                        {
                            'name': m['topic'].name,
                            'overlap_count': m['overlap_count'],
                            'overlap_keywords': m['overlap_keywords']
                        }
                        for m in matched_topics
                    ]
                })

        return stats

    @classmethod
    def get_committee_mapping_report(cls, committee: Committee) -> Dict[str, Any]:
        """Get detailed mapping report for a specific committee."""
        committee_keywords = set(committee.get_keywords_list())
        topic_areas = list(committee.topic_areas.all())

        matches = []
        for topic in topic_areas:
            topic_keywords = set(topic.get_keywords_list())
            overlap = committee_keywords & topic_keywords
            matches.append({
                'topic_name': topic.name,
                'topic_type': topic.competency_type,
                'overlap_count': len(overlap),
                'overlap_keywords': sorted(overlap),
                'topic_keywords': sorted(topic_keywords),
            })

        return {
            'committee_name': committee.name,
            'committee_keywords': sorted(committee_keywords),
            'matched_topics': matches,
            'match_count': len(matches),
        }
