"""
Management command to test topic-to-constituency mapping.

Provides examples of how the topic suggestion service works.
"""

from django.core.management.base import BaseCommand
from letters.services import TopicSuggestionService


class Command(BaseCommand):
    help = 'Test topic-to-constituency mapping with example concerns'

    def add_arguments(self, parser):
        parser.add_argument(
            '--concern',
            type=str,
            help='Custom concern text to test',
        )

    def handle(self, *args, **options):
        custom_concern = options.get('concern')

        if custom_concern:
            # Test custom concern
            self.test_concern(custom_concern)
        else:
            # Test predefined examples
            self.stdout.write(self.style.MIGRATE_HEADING('\nTesting Topic-to-Constituency Mapping\n'))

            test_cases = [
                "I want to see better train connections between cities",
                "We need more affordable housing and rent control",
                "Our school curriculum needs reform",
                "Climate protection and CO2 emissions must be addressed",
                "Better bus services in my town",
                "Deutsche Bahn is always late",
                "University tuition fees should be abolished",
                "We need stronger EU trade agreements",
                "Police funding in our state is too low",
                "Renewable energy expansion is too slow",
            ]

            for concern in test_cases:
                self.test_concern(concern)
                self.stdout.write('')  # Blank line

    def test_concern(self, concern_text: str):
        """Test a single concern and display results."""
        self.stdout.write(self.style.SUCCESS(f'Concern: "{concern_text}"'))

        # Get topic suggestions only (lightweight)
        topics = TopicSuggestionService.get_topic_suggestions(concern_text)

        if topics:
            self.stdout.write(self.style.WARNING('  Matched Topics:'))
            for topic in topics[:3]:  # Show top 3
                self.stdout.write(f'    • {topic["name"]} ({topic["level"]}) - Score: {topic["match_score"]}')
                self.stdout.write(f'      {topic["description"]}')
        else:
            self.stdout.write(self.style.WARNING('  No specific topics matched'))

        # Get full suggestions with representatives
        result = TopicSuggestionService.suggest_representatives_for_concern(
            concern_text,
            limit=3
        )

        self.stdout.write(self.style.WARNING(f'  Suggested Level: {result["suggested_level"]}'))
        self.stdout.write(self.style.WARNING(f'  Explanation: {result["explanation"]}'))

        if result['suggested_constituencies']:
            self.stdout.write(self.style.WARNING('  Suggested Constituencies:'))
            for const in result['suggested_constituencies'][:3]:
                self.stdout.write(f'    • {const.name} ({const.level})')

        if result['suggested_representatives']:
            self.stdout.write(self.style.WARNING('  Suggested Representatives:'))
            for rep in result['suggested_representatives']:
                party = f' ({rep.party})' if rep.party else ''
                constituency = rep.primary_constituency
                constituency_label = constituency.name if constituency else rep.parliament.name
                self.stdout.write(f'    • {rep.full_name}{party} - {constituency_label}')
        else:
            self.stdout.write(self.style.WARNING('  (No representatives found - run sync_representatives first)'))
