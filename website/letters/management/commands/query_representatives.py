# ABOUTME: Query management command to find representatives by address and/or topics.
# ABOUTME: Interactive tool for testing representative suggestion logic.

from django.core.management.base import BaseCommand
from letters.models import Representative
from letters.services import ConstituencyLocator


class Command(BaseCommand):
    help = 'Find representatives by address and/or topics'

    def add_arguments(self, parser):
        # Address arguments
        parser.add_argument(
            '--street',
            type=str,
            help='Street name and number'
        )
        parser.add_argument(
            '--postal-code',
            type=str,
            help='Postal code (PLZ)'
        )
        parser.add_argument(
            '--city',
            type=str,
            help='City name'
        )

        # Topic arguments
        parser.add_argument(
            '--topics',
            type=str,
            help='Comma-separated topic keywords (e.g., "Verkehr,Infrastruktur")'
        )

        parser.add_argument(
            '--limit',
            type=int,
            default=10,
            help='Maximum number of representatives to return (default: 10)'
        )

    def handle(self, *args, **options):
        street = options.get('street')
        postal_code = options.get('postal_code')
        city = options.get('city')
        topics_str = options.get('topics')
        limit = options['limit']

        try:
            # Use constituency locator if address provided
            if postal_code or (street and city):
                locator = ConstituencyLocator()
                constituencies = locator.locate(
                    street=street,
                    postal_code=postal_code,
                    city=city
                )

                if not constituencies:
                    self.stdout.write('No constituencies found for this location')
                    return

                # Get representatives from constituencies
                representatives = []
                for constituency in constituencies:
                    reps = list(constituency.representatives.filter(is_active=True))
                    representatives.extend(reps)

                # Remove duplicates
                seen = set()
                unique_reps = []
                for rep in representatives:
                    if rep.id not in seen:
                        seen.add(rep.id)
                        unique_reps.append(rep)
                representatives = unique_reps

                if not representatives:
                    self.stdout.write('No active representatives found for these constituencies')
                    return

                # Filter by topics if provided
                if topics_str:
                    topic_keywords = [t.strip() for t in topics_str.split(',')]
                    # Simple keyword filter on representative focus areas
                    filtered_reps = []
                    for rep in representatives:
                        # Check if any committee or focus area matches
                        rep_text = ' '.join([
                            rep.full_name,
                            ' '.join([c.name for c in rep.committees.all()]),
                        ]).lower()

                        if any(keyword.lower() in rep_text for keyword in topic_keywords):
                            filtered_reps.append(rep)

                    representatives = filtered_reps if filtered_reps else representatives

                # Display results
                for rep in representatives[:limit]:
                    constituency = rep.primary_constituency
                    constituency_label = constituency.name if constituency else rep.parliament.name
                    self.stdout.write(f'{rep.full_name} ({rep.party}) - {constituency_label}')

                    # Show committees
                    committees = list(rep.committees.all()[:3])
                    if committees:
                        committee_names = ', '.join([c.name for c in committees])
                        self.stdout.write(f'  Committees: {committee_names}')

            # Use topic-based search if only topics provided
            elif topics_str:
                self.stdout.write('Topic-based representative search not yet implemented')
                self.stdout.write('Please provide at least a postal code for location-based search')

            else:
                self.stderr.write(self.style.ERROR(
                    'Error: Please provide either an address (--postal-code required) or --topics'
                ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
            return
