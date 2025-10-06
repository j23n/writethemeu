"""
Management command to map committees to TopicArea taxonomy.
Uses keyword matching to suggest mappings between committees and topic areas.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from letters.models import Committee, TopicArea


class Command(BaseCommand):
    help = 'Map committees to TopicArea taxonomy using keyword matching'

    def add_arguments(self, parser):
        parser.add_argument(
            '--auto',
            action='store_true',
            help='Automatically apply high-confidence mappings (>= 3 keyword matches)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show suggested mappings without saving'
        )

    def handle(self, *args, **options):
        auto_apply = options['auto']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - no changes will be saved'))

        # Get all committees without topic mappings
        unmapped_committees = Committee.objects.filter(topic_areas__isnull=True).distinct()
        self.stdout.write(f'Found {unmapped_committees.count()} unmapped committees')

        topic_areas = TopicArea.objects.all()
        mappings_applied = 0

        for committee in unmapped_committees:
            suggestions = self.find_topic_matches(committee, topic_areas)

            if not suggestions:
                continue

            # Show top suggestion
            top_match = suggestions[0]
            parliament_name = committee.parliament_term.parliament.name
            self.stdout.write(f'\n{committee.name} ({parliament_name})')
            self.stdout.write(f'  → {top_match["topic"].name} (score: {top_match["score"]}, matched: {", ".join(top_match["matched_keywords"][:3])})')

            # Auto-apply if score is high enough
            if auto_apply and top_match['score'] >= 3 and not dry_run:
                committee.topic_areas.set([top_match['topic']])
                mappings_applied += 1
                self.stdout.write(self.style.SUCCESS('    ✓ Applied'))
            elif top_match['score'] >= 3:
                self.stdout.write(self.style.SUCCESS('    (Would apply with --auto)'))

            # Show other suggestions
            for match in suggestions[1:3]:
                self.stdout.write(f'     • {match["topic"].name} (score: {match["score"]})')

        if mappings_applied > 0:
            self.stdout.write(self.style.SUCCESS(f'\n✓ Applied {mappings_applied} mappings'))
        else:
            self.stdout.write('\n Use --auto to automatically apply high-confidence mappings (score >= 3)')

    def find_topic_matches(self, committee: Committee, topic_areas):
        """Find matching topic areas for a committee based on keywords"""
        committee_name_lower = committee.name.lower()
        matches = []

        for topic in topic_areas:
            keywords = topic.get_keywords_list()
            score = 0
            matched_keywords = []

            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in committee_name_lower:
                    score += 1
                    matched_keywords.append(keyword)

            if score > 0:
                matches.append({
                    'topic': topic,
                    'score': score,
                    'matched_keywords': matched_keywords
                })

        # Sort by score (descending)
        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches
