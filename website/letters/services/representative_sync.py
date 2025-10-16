# ABOUTME: Service for synchronizing representatives, parliaments, and committees from Abgeordnetenwatch.
# ABOUTME: Links representatives to constituencies via external_id from API. Run sync_wahlkreise first.

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags
from tqdm import tqdm

from ..constants import GERMAN_STATE_ALIASES, get_state_code, normalize_german_state, normalize_party_name
from ..models import (
    Committee,
    CommitteeMembership,
    Constituency,
    Parliament,
    ParliamentTerm,
    Representative,
    TopicArea,
)
from .abgeordnetenwatch_api_client import AbgeordnetenwatchAPI

logger = logging.getLogger('letters.services')


class RepresentativeSyncService:
    """
    Sync representatives from Abgeordnetenwatch API and link to constituencies.

    Prerequisites:
    - Run sync_wahlkreise first to create constituencies
    - Constituencies are linked by external_id from API
    - Both direct mandates and list seats are supported
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.stats = {
            'parliaments_created': 0,
            'parliaments_updated': 0,
            'terms_created': 0,
            'terms_updated': 0,
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
                self._sync_parliament(parliament_data, level='EU', region='EU', description='EU parliament')
            elif level in ('all', 'federal') and label == 'Bundestag':
                self._sync_parliament(parliament_data, level='FEDERAL', region='DE', description='Bundestag')
            elif level in ('all', 'state') and label not in ('Bundestag', 'EU-Parlament'):
                if state and normalize_german_state(label) != normalize_german_state(state):
                    continue
                region = normalize_german_state(label)
                self._sync_parliament(parliament_data, level='STATE', region=region, description=f"Landtag {label}")

    # --------------------------------------
    def _sync_parliament(self, parliament_data: Dict[str, Any], level: str, region: str, description: str) -> None:
        logger.info("Syncing %s representatives …", description)
        parliament, term = self._ensure_parliament_and_term(parliament_data, level=level, region=region)
        mandates = self._fetch_active_mandates(term)
        for mandate in tqdm(mandates, desc=f"{description} representatives", unit="rep"):
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
        # BUG FIX: Remove the mandate_won filter that was excluding list representatives
        # The old buggy code was:
        #   return [m for m in mandates if m.get('type') == 'mandate' and m.get('electoral_data', {}).get('mandate_won')]
        # This excluded representatives who won through party lists but not direct constituencies,
        # which caused Saarland to only show 7 of 51 representatives.
        return [
            m for m in mandates
            if m.get('type') == 'mandate'
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
        return None

    def _download_representative_image(self, photo_url: Optional[str], representative: Representative) -> Optional[str]:
        if not photo_url:
            return None
        try:
            response = requests.get(photo_url, timeout=30)
            response.raise_for_status()
        except requests.RequestException:
            logger.warning("Failed to download photo for %s", representative.full_name, exc_info=True)
            return None

        extension = Path(photo_url).suffix.split('?')[0]
        if not extension or not extension.startswith('.'):
            logger.warning("No valid extension found in URL %s, defaulting to .jpg", photo_url)
            extension = '.jpg'
        if extension.lower() not in {'.jpg', '.jpeg', '.png', '.webp'}:
            logger.warning("Unusual image extension %s for %s, defaulting to .jpg", extension, photo_url)
            extension = '.jpg'

        media_dir = Path(settings.MEDIA_ROOT) / 'representatives'
        media_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{representative.external_id}{extension}"
        file_path = media_dir / filename
        file_path.write_bytes(response.content)
        self.stats['photos_downloaded'] += 1
        return f"representatives/{filename}"

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
        biography = self._extract_biography(politician)
        focus_topics = self._extract_focus_topics(politician)
        links = self._extract_links(politician)

        metadata = {
            'mandate': mandate,
            'politician_id': politician_id,
            'abgeordnetenwatch_url': (
                politician.get('abgeordnetenwatch_url')
                or politician.get('url')
            ),
            'wikipedia_url': self._extract_wikipedia_link(politician),
        }
        if biography:
            metadata['biography'] = biography
        if focus_topics:
            metadata['focus_topics'] = focus_topics
        if links:
            metadata['links'] = links

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
            'metadata': metadata,
            'focus_areas': ', '.join(focus_topics) if focus_topics else '',
        }

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
            if constituency:
                rep.constituencies.add(constituency)

        if not self.dry_run:
            photo_path_exists = rep.photo_path and (Path(settings.MEDIA_ROOT) / rep.photo_path).exists()
            if not photo_path_exists:
                photo_url = self._find_photo_url(politician)
                photo_path = self._download_representative_image(photo_url, rep) if photo_url else None
                if photo_path and rep.photo_path != photo_path:
                    rep.photo_path = photo_path
                    rep.photo_updated_at = timezone.now()
                    rep.save(update_fields=['photo_path', 'photo_updated_at'])

    # --------------------------------------
    def _determine_constituencies(
        self,
        parliament: Parliament,
        term: ParliamentTerm,
        electoral: Dict,
        representative: Representative,
    ) -> Iterable[Constituency]:
        """Link representative to constituencies by external_id from API."""

        # Try direct constituency (Direktmandat)
        const_data = electoral.get('constituency')
        if const_data:
            const_id = const_data.get('id')
            if const_id:
                try:
                    yield Constituency.objects.get(external_id=str(const_id))
                except Constituency.DoesNotExist:
                    logger.warning(
                        "Constituency external_id=%s not found for %s. Run sync_wahlkreise first.",
                        const_id,
                        representative.full_name
                    )

        # Try electoral list (Listenmandat)
        list_data = electoral.get('electoral_list')
        if list_data:
            list_id = list_data.get('id')
            if list_id:
                try:
                    yield Constituency.objects.get(external_id=str(list_id))
                except Constituency.DoesNotExist:
                    logger.warning(
                        "Electoral list external_id=%s not found for %s. Run sync_wahlkreise first.",
                        list_id,
                        representative.full_name
                    )

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
