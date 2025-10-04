"""
Management command to test the ConstituencySuggestionService with example queries.
"""

from django.core.management.base import BaseCommand
from letters.services import ConstituencySuggestionService


class Command(BaseCommand):
    help = 'Test the constituency suggestion service with example queries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--query',
            type=str,
            help='Custom query to test (if not provided, runs example queries)'
        )

    def handle(self, *args, **options):
        custom_query = options.get('query')

        if custom_query:
            # Test custom query
            self.test_query(custom_query)
        else:
            # Run all example queries
            self.stdout.write(self.style.SUCCESS('Testing ConstituencySuggestionService\n'))
            self.stdout.write('=' * 80)

            examples = ConstituencySuggestionService.get_example_queries()

            for i, example in enumerate(examples, 1):
                self.stdout.write(f"\n{i}. Query: \"{example['query']}\"")
                self.stdout.write(f"   Expected: {example['expected_level']} - {example['topic']}")
                self.stdout.write('-' * 80)

                self.test_query(example['query'])

                self.stdout.write('=' * 80)

    def test_query(self, query):
        """Test a single query and display results"""
        result = ConstituencySuggestionService.suggest_from_concern(query)

        # Display matched topics
        self.stdout.write(self.style.WARNING('\nMatched Topics:'))
        if result['matched_topics']:
            for topic in result['matched_topics']:
                self.stdout.write(
                    f"  • {topic.name} ({topic.get_primary_level_display()}) - {topic.competency_type}"
                )
        else:
            self.stdout.write('  None')

        # Display suggested level
        self.stdout.write(self.style.WARNING('\nSuggested Level:'))
        self.stdout.write(f"  {result['suggested_level']}")

        # Display explanation
        self.stdout.write(self.style.WARNING('\nExplanation:'))
        self.stdout.write(f"  {result['explanation']}")

        # Display constituencies
        self.stdout.write(self.style.WARNING('\nConstituencies:'))
        if result['constituencies']:
            for const in result['constituencies'][:5]:  # Limit to 5
                self.stdout.write(f"  • {const.name} ({const.get_level_display()})")
        else:
            self.stdout.write('  None')

        # Display representatives
        self.stdout.write(self.style.WARNING('\nRepresentatives:'))
        if result['representatives']:
            for rep in result['representatives'][:5]:  # Limit to 5
                constituency = rep.primary_constituency
                constituency_label = constituency.name if constituency else rep.parliament.name
                self.stdout.write(
                    f"  • {rep.full_name} ({rep.party}) - {constituency_label}"
                )
        else:
            self.stdout.write('  None (no representatives in database yet)')
