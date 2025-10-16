# ABOUTME: Services for locating constituencies and suggesting representatives based on addresses.
# ABOUTME: Combines geocoding, Wahlkreis mapping, and PLZ fallback for robust constituency resolution.

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from django.db.models import Q
from django.utils.translation import gettext as _

from ..constants import normalize_german_state
from ..models import Constituency, Parliament, ParliamentTerm, Representative, Tag, TopicArea
from .geocoding import AddressGeocoder, WahlkreisLocator
from .wahlkreis import WahlkreisResolver

logger = logging.getLogger('letters.services')


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
        # Extract address components
        postal_code = (user_location.get('postal_code') or '').strip()
        street = (user_location.get('street') or '').strip()
        city = (user_location.get('city') or '').strip()
        country = (user_location.get('country') or 'DE').upper()

        constituencies: List[Constituency] = []

        # First, check if constituencies are provided directly
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

        # If no constituencies provided, try address-based lookup
        if not constituencies and street and postal_code and city:
            from .wahlkreis import WahlkreisResolver
            resolver = WahlkreisResolver()

            # Build full address string
            address = f"{street}, {postal_code} {city}"
            result = resolver.resolve(address=address, country=country)
            constituencies = result['constituencies']

        # Determine state from various sources
        explicit_state = normalize_german_state(user_location.get('state')) if user_location.get('state') else None
        inferred_state = None

        for constituency in constituencies:
            metadata_state = (constituency.metadata or {}).get('state') if constituency.metadata else None
            if metadata_state:
                inferred_state = normalize_german_state(metadata_state)
                if inferred_state:
                    break

        state = explicit_state or inferred_state

        return LocationContext(
            postal_code=postal_code or None,
            state=state,
            constituencies=constituencies,
            street=street or None,
            city=city or None,
            country=country,
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
        Finds representatives who have the matched TopicAreas assigned OR
        serve on committees with those topic areas.
        """
        if not matched_topics:
            return []

        # Find representatives via topic_areas OR committee memberships
        topic_query = Q(topic_areas__in=matched_topics)
        committee_query = Q(committee_memberships__committee__topic_areas__in=matched_topics)

        reps = Representative.objects.filter(
            is_active=True
        ).filter(
            topic_query | committee_query
        ).exclude(
            id__in=exclude_ids
        ).select_related(
            'parliament', 'parliament_term'
        ).prefetch_related(
            'constituencies',
            'topic_areas',
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
