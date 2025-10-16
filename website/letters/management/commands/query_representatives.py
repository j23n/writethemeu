# ABOUTME: Query management command to find representatives by address and/or topics.
# ABOUTME: Interactive tool for testing representative suggestion logic.

from django.core.management.base import BaseCommand
from letters.models import Representative
from letters.services.wahlkreis import WahlkreisResolver


class Command(BaseCommand):
    help = 'Find representatives by address and/or topics'

    def add_arguments(self, parser):
        # Address argument
        parser.add_argument(
            'address',
            type=str,
            nargs='?',
            help='Full address string (e.g., "Unter den Linden 1, 10117 Berlin")'
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
        address = options.get('address')
        topics_str = options.get('topics')
        limit = options['limit']

        try:
            # Use WahlkreisResolver if address provided
            if address:
                resolver = WahlkreisResolver()
                result = resolver.resolve(address=address)

                if result['federal_wahlkreis_number']:
                    self.stdout.write(self.style.SUCCESS(
                        f"Found Wahlkreise: "
                        f"Federal={result['federal_wahlkreis_number']}, "
                        f"State={result['state_wahlkreis_number']}, "
                        f"EU={result['eu_wahlkreis']}"
                    ))

                constituencies = result['constituencies']

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
                    filtered_reps = []
                    for rep in representatives:
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

                    committees = list(rep.committees.all()[:3])
                    if committees:
                        committee_names = ', '.join([c.name for c in committees])
                        self.stdout.write(f'  Committees: {committee_names}')

            # Use topic-based search if only topics provided
            elif topics_str:
                self.stdout.write('Topic-based representative search not yet implemented')
                self.stdout.write('Please provide at least an address for location-based search')

            else:
                self.stderr.write(self.style.ERROR(
                    'Error: Please provide an address or --topics'
                ))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
            return
