# ABOUTME: Query management command to find matching topics for letter text.
# ABOUTME: Interactive tool for testing topic keyword matching and scoring.

from django.core.management.base import BaseCommand
from letters.services import TopicSuggestionService


class Command(BaseCommand):
    help = 'Find matching topics for a letter title or text'

    def add_arguments(self, parser):
        parser.add_argument(
            '--text',
            type=str,
            required=True,
            help='Letter title or text to analyze'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=5,
            help='Maximum number of topics to return (default: 5)'
        )

    def handle(self, *args, **options):
        text = options['text']
        limit = options['limit']

        try:
            # Use the suggest_representatives_for_concern method to get topic suggestions
            result = TopicSuggestionService.suggest_representatives_for_concern(
                text,
                limit=limit
            )

            matched_topics = result.get('matched_topics', [])

            if not matched_topics:
                self.stdout.write('No matching topics found')
                return

            # Display matched topics
            for topic in matched_topics[:limit]:
                # TopicArea objects have name, primary_level, and description
                level = getattr(topic, 'primary_level', 'UNKNOWN')
                name = getattr(topic, 'name', str(topic))
                description = getattr(topic, 'description', '')

                self.stdout.write(f"{name} ({level})")
                if description:
                    self.stdout.write(f"  {description}")

            # Also show suggested level and explanation
            if result.get('suggested_level'):
                self.stdout.write('')
                self.stdout.write(f"Suggested Level: {result['suggested_level']}")
            if result.get('explanation'):
                self.stdout.write(f"Explanation: {result['explanation']}")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
            return
