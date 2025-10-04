"""
Management command to populate the TopicArea taxonomy with German governmental competencies.
Based on the Grundgesetz (German Basic Law) division of powers.
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify
from letters.models import TopicArea


class Command(BaseCommand):
    help = 'Load topic taxonomy based on German constitutional division of powers'

    def handle(self, *args, **options):
        self.stdout.write('Loading topic taxonomy...')

        # Clear existing data
        TopicArea.objects.all().delete()

        topics_data = [
            # FEDERAL EXCLUSIVE COMPETENCIES (Art. 73 GG)
            {
                'name': 'Foreign Affairs',
                'description': 'International relations, treaties, diplomatic missions',
                'primary_level': 'FEDERAL',
                'competency_type': 'EXCLUSIVE',
                'keywords': 'foreign policy, diplomacy, international relations, treaties, EU policy, foreign affairs, external relations',
                'legal_basis': 'Art. 73(1) GG',
            },
            {
                'name': 'Defense',
                'description': 'Military, civil defense, protection of civilian population',
                'primary_level': 'FEDERAL',
                'competency_type': 'EXCLUSIVE',
                'keywords': 'defense, military, Bundeswehr, armed forces, NATO, civil defense, emergency preparedness',
                'legal_basis': 'Art. 73(1) GG',
            },
            {
                'name': 'Citizenship',
                'description': 'German citizenship and naturalization',
                'primary_level': 'FEDERAL',
                'competency_type': 'EXCLUSIVE',
                'keywords': 'citizenship, naturalization, nationality, passport, immigration status',
                'legal_basis': 'Art. 73(2) GG',
            },
            {
                'name': 'Currency and Monetary Policy',
                'description': 'Currency, money, coinage, central banking',
                'primary_level': 'FEDERAL',
                'competency_type': 'EXCLUSIVE',
                'keywords': 'currency, Euro, monetary policy, Bundesbank, central bank, inflation, interest rates',
                'legal_basis': 'Art. 73(4) GG',
            },
            {
                'name': 'Customs and Trade',
                'description': 'Customs, foreign trade, tariffs',
                'primary_level': 'FEDERAL',
                'competency_type': 'EXCLUSIVE',
                'keywords': 'customs, tariffs, trade, imports, exports, border control, free trade',
                'legal_basis': 'Art. 73(5) GG',
            },

            # FEDERAL CONCURRENT COMPETENCIES (Art. 74 GG)
            {
                'name': 'Civil and Criminal Law',
                'description': 'Civil law, criminal law, court procedures',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'civil law, criminal law, justice, courts, prosecution, legal system, judiciary',
                'legal_basis': 'Art. 74(1) GG',
            },
            {
                'name': 'Immigration and Asylum',
                'description': 'Residence and establishment of foreign nationals, refugees',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'immigration, asylum, refugees, residence permits, visa, migration, foreign nationals',
                'legal_basis': 'Art. 74(4,6) GG',
            },
            {
                'name': 'Social Welfare',
                'description': 'Public welfare, social security, unemployment',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'social welfare, public welfare, welfare benefits, social security, unemployment benefits, Hartz IV',
                'legal_basis': 'Art. 74(7) GG',
            },
            {
                'name': 'Economic Policy',
                'description': 'Mining, industry, energy, commerce, banking',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'economy, industry, energy, mining, commerce, trade, banking, stock exchange, business regulation',
                'legal_basis': 'Art. 74(11) GG',
            },
            {
                'name': 'Labor Law',
                'description': 'Employment law, workplace safety, social security',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'labor law, employment, workers rights, workplace safety, employment agencies, job centers, social insurance',
                'legal_basis': 'Art. 74(12) GG',
            },
            {
                'name': 'Research Funding',
                'description': 'Educational grants and research promotion',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'research funding, research grants, educational grants, BAföG, student aid, science funding',
                'legal_basis': 'Art. 74(13) GG',
            },
            {
                'name': 'Housing Policy',
                'description': 'Housing subsidies, real estate transactions, land law',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'housing, real estate, property, rent control, housing subsidies, land transactions, affordable housing',
                'legal_basis': 'Art. 74(18) GG',
            },
            {
                'name': 'Healthcare Regulation',
                'description': 'Disease control, medical professions, pharmacies',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'healthcare regulation, medical profession, pharmacies, medicines, disease control, public health, doctors, hospitals',
                'legal_basis': 'Art. 74(19,19a) GG',
            },
            {
                'name': 'Food Safety',
                'description': 'Food law, consumer protection, animal protection',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'food safety, consumer protection, food law, animal protection, food standards',
                'legal_basis': 'Art. 74(20) GG',
            },
            {
                'name': 'Federal Transportation',
                'description': 'Long-distance highways, federal railways (Deutsche Bahn)',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'federal highways, Autobahn, Deutsche Bahn, intercity trains, ICE, long-distance rail, federal infrastructure, national transport',
                'legal_basis': 'Art. 74(22,23) GG',
            },
            {
                'name': 'Road Traffic',
                'description': 'Road traffic regulations, motor vehicle transport',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'road traffic, traffic laws, motor vehicles, driving regulations, vehicle registration, traffic safety',
                'legal_basis': 'Art. 74(22) GG',
            },
            {
                'name': 'Environmental Protection',
                'description': 'Waste disposal, air pollution, noise control',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'environment, waste disposal, air pollution, noise control, emissions, climate policy, environmental protection',
                'legal_basis': 'Art. 74(24) GG',
            },
            {
                'name': 'Regional Planning',
                'description': 'Spatial planning and regional development',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'regional planning, spatial planning, land use planning, urban development, regional development',
                'legal_basis': 'Art. 74(31) GG',
            },
            {
                'name': 'Water Management',
                'description': 'Water resources and water law',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'water management, water resources, water law, rivers, lakes, water quality, flood protection',
                'legal_basis': 'Art. 74(32) GG',
            },
            {
                'name': 'Higher Education Admission',
                'description': 'University admission and graduation requirements',
                'primary_level': 'FEDERAL',
                'competency_type': 'CONCURRENT',
                'keywords': 'university admission, higher education access, graduation requirements, NC (Numerus Clausus), university entry',
                'legal_basis': 'Art. 74(33) GG',
            },

            # STATE (LÄNDER) COMPETENCIES
            {
                'name': 'Primary and Secondary Education',
                'description': 'Schools, curricula, teacher employment (Kulturhoheit)',
                'primary_level': 'STATE',
                'competency_type': 'STATE',
                'keywords': 'schools, education, primary school, secondary school, Gymnasium, Realschule, curriculum, teachers, school system, Abitur',
                'legal_basis': 'Kulturhoheit der Länder',
            },
            {
                'name': 'Higher Education',
                'description': 'Universities, research institutions (except admission)',
                'primary_level': 'STATE',
                'competency_type': 'STATE',
                'keywords': 'universities, higher education, research institutions, university funding, professors, academic freedom',
                'legal_basis': 'Kulturhoheit der Länder',
            },
            {
                'name': 'Broadcasting and Media',
                'description': 'Public broadcasting, media regulation',
                'primary_level': 'STATE',
                'competency_type': 'STATE',
                'keywords': 'broadcasting, media, radio, television, public broadcasting, ARD, ZDF, media regulation',
                'legal_basis': 'Kulturhoheit der Länder',
            },
            {
                'name': 'State Police',
                'description': 'Law enforcement, public order, internal security',
                'primary_level': 'STATE',
                'competency_type': 'STATE',
                'keywords': 'police, law enforcement, public order, public safety, crime prevention, state police, Landespolizei',
                'legal_basis': 'Art. 30, 70 GG',
            },
            {
                'name': 'Culture and Arts',
                'description': 'Cultural policy, museums, theaters, monuments',
                'primary_level': 'STATE',
                'competency_type': 'STATE',
                'keywords': 'culture, arts, museums, theaters, cultural heritage, monuments, cultural policy, festivals',
                'legal_basis': 'Kulturhoheit der Länder',
            },
            {
                'name': 'State Administration',
                'description': 'State government structure and administration',
                'primary_level': 'STATE',
                'competency_type': 'STATE',
                'keywords': 'state government, Landtag, state parliament, state administration, ministerial structure',
                'legal_basis': 'Art. 30 GG',
            },
            {
                'name': 'State Roads and Transport',
                'description': 'State roads (Landesstraßen), regional public transport',
                'primary_level': 'STATE',
                'competency_type': 'STATE',
                'keywords': 'state roads, Landesstraßen, regional transport, regional trains, regional buses, S-Bahn, regional infrastructure',
                'legal_basis': 'Art. 30 GG',
            },

            # LOCAL (MUNICIPAL) COMPETENCIES
            {
                'name': 'Local Infrastructure',
                'description': 'Local roads, utilities, waste collection',
                'primary_level': 'LOCAL',
                'competency_type': 'LOCAL',
                'keywords': 'local roads, local infrastructure, utilities, water supply, sewage, waste collection, street lighting',
                'legal_basis': 'Art. 28(2) GG',
            },
            {
                'name': 'Local Transportation',
                'description': 'Local public transport, municipal traffic',
                'primary_level': 'LOCAL',
                'competency_type': 'LOCAL',
                'keywords': 'local transport, city buses, trams, U-Bahn, metro, municipal transport, bike lanes, pedestrian zones',
                'legal_basis': 'Art. 28(2) GG',
            },
            {
                'name': 'Local Planning',
                'description': 'Local development plans, building permits',
                'primary_level': 'LOCAL',
                'competency_type': 'LOCAL',
                'keywords': 'local planning, zoning, building permits, construction permits, urban planning, city development, Bebauungsplan',
                'legal_basis': 'Art. 28(2) GG',
            },
            {
                'name': 'Local Schools',
                'description': 'School buildings, maintenance (not curriculum)',
                'primary_level': 'LOCAL',
                'competency_type': 'LOCAL',
                'keywords': 'school buildings, school maintenance, school facilities, school construction, playground',
                'legal_basis': 'Art. 28(2) GG',
            },
            {
                'name': 'Local Social Services',
                'description': 'Youth services, childcare, elderly care facilities',
                'primary_level': 'LOCAL',
                'competency_type': 'LOCAL',
                'keywords': 'childcare, kindergarten, daycare, youth services, elderly care, social services, community centers',
                'legal_basis': 'Art. 28(2) GG',
            },
            {
                'name': 'Local Culture and Recreation',
                'description': 'Libraries, sports facilities, parks',
                'primary_level': 'LOCAL',
                'competency_type': 'LOCAL',
                'keywords': 'local library, sports facilities, parks, playgrounds, swimming pools, community events, local culture',
                'legal_basis': 'Art. 28(2) GG',
            },
            {
                'name': 'Public Order',
                'description': 'Local public order, markets, noise ordinances',
                'primary_level': 'LOCAL',
                'competency_type': 'LOCAL',
                'keywords': 'public order, noise ordinances, local regulations, markets, street cleaning, public safety regulations',
                'legal_basis': 'Art. 28(2) GG',
            },

            # EU LEVEL
            {
                'name': 'EU Single Market',
                'description': 'European single market, competition policy',
                'primary_level': 'EU',
                'competency_type': 'EXCLUSIVE',
                'keywords': 'EU single market, European market, competition policy, antitrust, EU regulations, free movement',
                'legal_basis': 'EU Treaties',
            },
            {
                'name': 'EU Trade Policy',
                'description': 'Common commercial policy, trade agreements',
                'primary_level': 'EU',
                'competency_type': 'EXCLUSIVE',
                'keywords': 'EU trade, trade agreements, common commercial policy, international trade, EU customs union',
                'legal_basis': 'EU Treaties',
            },
        ]

        created_count = 0
        for topic_data in topics_data:
            topic_data['slug'] = slugify(topic_data['name'])
            topic = TopicArea.objects.create(**topic_data)
            created_count += 1
            self.stdout.write(
                self.style.SUCCESS(f'  ✓ Created: {topic.name} ({topic.get_primary_level_display()})')
            )

        self.stdout.write(
            self.style.SUCCESS(f'\nSuccessfully loaded {created_count} topic areas')
        )
