# ABOUTME: Topic-related services for suggesting representatives and mapping committees to topics.
# ABOUTME: Provides topic suggestion and committee-topic mapping functionality.

from __future__ import annotations

from typing import Any, Dict, Optional

from tqdm import tqdm

from ..models import Committee, TopicArea
from .constituency import ConstituencySuggestionService


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
