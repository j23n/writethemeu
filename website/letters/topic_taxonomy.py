"""
Topic Taxonomy for German Political Competencies

Based on German Basic Law (Grundgesetz) competency distribution:
- EU competencies (Treaties, EU law)
- Federal exclusive competencies (Art. 73 GG)
- Federal concurrent competencies (Art. 74 GG)
- State exclusive competencies (Education, culture, police)

This taxonomy maps citizen concerns to the appropriate government level.
"""

from typing import List, Dict, Set
from dataclasses import dataclass


@dataclass
class TopicArea:
    """Represents a policy area with its competent government level"""
    name: str
    level: str  # 'EU', 'FEDERAL', 'STATE', or 'MULTIPLE'
    keywords: Set[str]
    description: str
    examples: List[str]


# EU Level Competencies (based on EU Treaties)
EU_TOPICS = [
    TopicArea(
        name="EU Trade & Customs",
        level="EU",
        keywords={
            "customs", "tariff", "import", "export", "trade agreement", "EU trade",
            "customs union", "trade deal", "international trade", "tariffs"
        },
        description="EU-wide trade policy and customs union",
        examples=["EU trade agreements with other countries", "Customs regulations"]
    ),
    TopicArea(
        name="EU Agricultural Policy",
        level="EU",
        keywords={
            "CAP", "agricultural subsidies", "farming subsidies", "EU farm policy",
            "common agricultural policy", "agricultural support", "EU farming"
        },
        description="Common Agricultural Policy (CAP)",
        examples=["Farm subsidies", "Agricultural regulations"]
    ),
    TopicArea(
        name="EU Competition & Single Market",
        level="EU",
        keywords={
            "single market", "competition law", "antitrust", "monopoly",
            "EU market", "competition policy", "market regulation", "EU competition"
        },
        description="Single market rules and competition law",
        examples=["Antitrust cases", "Market access rules"]
    ),
    TopicArea(
        name="EU Environmental Standards",
        level="EU",
        keywords={
            "EU climate", "emissions trading", "EU Green Deal", "carbon border",
            "EU environmental", "climate targets", "EU emissions", "green transition"
        },
        description="EU-wide environmental and climate policy",
        examples=["EU emissions targets", "Green Deal initiatives"]
    ),
    TopicArea(
        name="EU Immigration & Borders",
        level="EU",
        keywords={
            "Schengen", "EU borders", "asylum policy", "migration policy",
            "EU immigration", "border control", "refugee distribution", "Dublin regulation"
        },
        description="Common immigration and asylum policy",
        examples=["Schengen area", "Asylum seeker distribution"]
    ),
    TopicArea(
        name="EU Consumer Protection",
        level="EU",
        keywords={
            "consumer rights", "product safety", "EU standards", "consumer protection",
            "product standards", "EU regulations", "consumer law"
        },
        description="EU consumer protection standards",
        examples=["Product safety standards", "Consumer rights"]
    ),
]

# Federal Exclusive Competencies (Art. 73 GG)
FEDERAL_EXCLUSIVE_TOPICS = [
    TopicArea(
        name="Defense & Military",
        level="FEDERAL",
        keywords={
            "Bundeswehr", "defense", "military", "armed forces", "NATO",
            "defense budget", "military equipment", "soldier", "army", "defense policy"
        },
        description="Defense and protection of civilian population",
        examples=["Bundeswehr budget", "Military equipment", "Defense strategy"]
    ),
    TopicArea(
        name="Foreign Policy",
        level="FEDERAL",
        keywords={
            "foreign policy", "diplomacy", "international relations", "embassy",
            "foreign affairs", "diplomatic", "bilateral", "international treaty"
        },
        description="Foreign affairs and international relations",
        examples=["Diplomatic relations", "International treaties"]
    ),
    TopicArea(
        name="Citizenship & Passports",
        level="FEDERAL",
        keywords={
            "citizenship", "passport", "nationality", "naturalization",
            "German citizenship", "visa", "residence permit", "immigration status"
        },
        description="Citizenship and naturalization",
        examples=["Passport issuance", "Naturalization process"]
    ),
    TopicArea(
        name="Currency & Federal Finance",
        level="FEDERAL",
        keywords={
            "currency", "Bundesbank", "monetary policy", "federal budget",
            "federal debt", "fiscal policy", "national budget", "federal spending"
        },
        description="Currency, money, and federal budget",
        examples=["Federal budget", "Monetary policy"]
    ),
    TopicArea(
        name="Federal Railways",
        level="FEDERAL",
        keywords={
            "deutsche bahn", "db", "federal railway", "long-distance trains", "train",
            "ice", "intercity", "rail infrastructure", "railway network", "federal trains",
            "railway", "train connection", "rail", "bahn"
        },
        description="Federal railway infrastructure and long-distance rail",
        examples=["Deutsche Bahn services", "ICE connections", "Railway infrastructure"]
    ),
    TopicArea(
        name="Telecommunications & Post",
        level="FEDERAL",
        keywords={
            "5G", "telecommunications", "internet infrastructure", "postal service",
            "broadband", "digital infrastructure", "mobile network", "fiber optic"
        },
        description="Telecommunications and postal services",
        examples=["5G rollout", "Broadband expansion", "Postal regulations"]
    ),
]

# Federal Concurrent Competencies (Art. 74 GG) - Federal often legislates
FEDERAL_CONCURRENT_TOPICS = [
    TopicArea(
        name="Labor Law & Employment",
        level="FEDERAL",
        keywords={
            "labor law", "employment", "minimum wage", "working conditions",
            "workplace", "employee rights", "labor protection", "work hours",
            "unemployment", "job market", "employment protection"
        },
        description="Labor law and employment regulation",
        examples=["Minimum wage", "Working time regulations", "Unemployment benefits"]
    ),
    TopicArea(
        name="Social Security & Welfare",
        level="FEDERAL",
        keywords={
            "pension", "retirement", "social security", "welfare", "Hartz IV",
            "unemployment benefit", "child benefit", "Kindergeld", "Bürgergeld",
            "social insurance", "disability benefits"
        },
        description="Social security, pensions, and welfare",
        examples=["Pension system", "Unemployment benefits", "Social welfare"]
    ),
    TopicArea(
        name="Federal Health Policy",
        level="FEDERAL",
        keywords={
            "health insurance", "Krankenkasse", "medical care", "healthcare system",
            "hospital funding", "pharmaceutical", "drug prices", "health reform"
        },
        description="Health insurance and healthcare system regulation",
        examples=["Health insurance reform", "Drug pricing", "Hospital financing"]
    ),
    TopicArea(
        name="Civil & Criminal Law",
        level="FEDERAL",
        keywords={
            "criminal law", "civil law", "justice", "court system", "legal reform",
            "Bundesgerichtshof", "federal court", "criminal code", "civil code"
        },
        description="Civil and criminal legislation",
        examples=["Criminal code reform", "Civil law changes"]
    ),
    TopicArea(
        name="Immigration Law",
        level="FEDERAL",
        keywords={
            "immigration", "residence law", "work permit", "skilled worker",
            "integration", "asylum law", "deportation", "migration"
        },
        description="Immigration and residence law (national level)",
        examples=["Skilled worker immigration", "Integration programs"]
    ),
    TopicArea(
        name="Federal Infrastructure",
        level="FEDERAL",
        keywords={
            "Autobahn", "federal roads", "infrastructure investment",
            "Bundesstraße", "national infrastructure", "bridge repair",
            "highway", "federal construction"
        },
        description="Federal highways and infrastructure",
        examples=["Autobahn expansion", "Federal road maintenance"]
    ),
    TopicArea(
        name="Energy Policy",
        level="FEDERAL",
        keywords={
            "renewable energy", "coal exit", "nuclear power", "energy transition",
            "Energiewende", "solar", "wind energy", "power grid", "electricity prices"
        },
        description="Energy policy and transition",
        examples=["Renewable energy expansion", "Coal phase-out", "Energy prices"]
    ),
    TopicArea(
        name="Climate Protection",
        level="FEDERAL",
        keywords={
            "climate protection", "CO2 emissions", "climate law", "carbon pricing",
            "climate targets", "emissions reduction", "climate action", "carbon tax"
        },
        description="National climate protection policy",
        examples=["Climate protection law", "Carbon pricing", "Emissions targets"]
    ),
    TopicArea(
        name="Housing Policy",
        level="FEDERAL",
        keywords={
            "affordable housing", "rent control", "Mietpreisbremse", "housing shortage",
            "construction", "building code", "rent cap", "social housing"
        },
        description="Housing and tenancy law",
        examples=["Rent controls", "Affordable housing programs"]
    ),
]

# State (Länder) Exclusive Competencies
STATE_EXCLUSIVE_TOPICS = [
    TopicArea(
        name="Education & Schools",
        level="STATE",
        keywords={
            "school", "education", "Gymnasium", "teacher", "curriculum",
            "school system", "primary school", "Grundschule", "Abitur",
            "vocational school", "Berufsschule", "school policy", "class size"
        },
        description="School system and education policy",
        examples=["School curriculum", "Teacher hiring", "School structure", "Abitur requirements"]
    ),
    TopicArea(
        name="Universities & Higher Education",
        level="STATE",
        keywords={
            "university", "higher education", "tuition fees", "Studium",
            "university funding", "research", "academic", "college", "Hochschule"
        },
        description="Higher education and universities",
        examples=["University funding", "Tuition policies", "Study programs"]
    ),
    TopicArea(
        name="State Police",
        level="STATE",
        keywords={
            "police", "Polizei", "public safety", "law enforcement", "crime prevention",
            "police funding", "police reform", "state police", "Landespolizei"
        },
        description="State police forces (excluding federal police)",
        examples=["State police funding", "Local policing", "Crime prevention"]
    ),
    TopicArea(
        name="State Roads & Transport",
        level="STATE",
        keywords={
            "state roads", "Landesstraße", "local transport", "ÖPNV", "bus", "tram",
            "regional trains", "local traffic", "bike lanes", "pedestrian", "state highway"
        },
        description="State roads and local public transport",
        examples=["State road maintenance", "Local bus services", "Bike infrastructure"]
    ),
    TopicArea(
        name="Culture & Media",
        level="STATE",
        keywords={
            "culture", "museum", "theater", "broadcasting", "public TV", "radio",
            "cultural funding", "arts", "heritage", "monument protection"
        },
        description="Cultural affairs and public broadcasting",
        examples=["Museum funding", "Public broadcasting", "Cultural programs"]
    ),
    TopicArea(
        name="State Health Services",
        level="STATE",
        keywords={
            "hospital", "clinic", "public health", "health services", "emergency care",
            "local health", "health department", "disease prevention", "vaccination"
        },
        description="State health services and hospitals",
        examples=["Hospital operations", "Public health services", "Local clinics"]
    ),
    TopicArea(
        name="Regional Planning",
        level="STATE",
        keywords={
            "regional planning", "zoning", "land use", "urban planning",
            "building permits", "local development", "construction permits"
        },
        description="Regional and urban planning",
        examples=["Zoning regulations", "Building permits", "Urban development"]
    ),
]

# Topics with shared/multiple competencies
SHARED_TOPICS = [
    TopicArea(
        name="Environment (Shared)",
        level="MULTIPLE",
        keywords={
            "environment", "environmental protection", "nature conservation",
            "water protection", "air quality", "waste management", "recycling"
        },
        description="Environmental protection (EU framework, federal law, state implementation)",
        examples=["Water quality standards", "Waste management", "Nature reserves"]
    ),
    TopicArea(
        name="Digitalization",
        level="MULTIPLE",
        keywords={
            "digitalization", "digital", "internet", "online services", "e-government",
            "digital transformation", "tech", "digital infrastructure"
        },
        description="Digital transformation (infrastructure=federal, schools=state)",
        examples=["Digital infrastructure", "Digital education", "E-government"]
    ),
]

# Combine all topics
ALL_TOPICS = (
    EU_TOPICS +
    FEDERAL_EXCLUSIVE_TOPICS +
    FEDERAL_CONCURRENT_TOPICS +
    STATE_EXCLUSIVE_TOPICS +
    SHARED_TOPICS
)


class TopicMatcher:
    """Matches user input text to relevant political topics and government levels"""

    def __init__(self):
        self.topics = ALL_TOPICS

    def match_topics(self, text: str, threshold: int = 1) -> List[tuple[TopicArea, int]]:
        """
        Match text to topics based on keyword matching.

        Args:
            text: User input text (concern description)
            threshold: Minimum keyword matches required

        Returns:
            List of (TopicArea, match_count) tuples, sorted by match count
        """
        text_lower = text.lower()
        matches = []

        for topic in self.topics:
            match_count = sum(1 for keyword in topic.keywords if keyword in text_lower)
            if match_count >= threshold:
                matches.append((topic, match_count))

        # Sort by match count (descending)
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def suggest_levels(self, text: str) -> Dict[str, List[TopicArea]]:
        """
        Suggest government levels based on user concern.

        Returns:
            Dictionary with levels as keys and matching topics as values
        """
        matches = self.match_topics(text)

        result = {
            'EU': [],
            'FEDERAL': [],
            'STATE': [],
            'MULTIPLE': []
        }

        for topic, _ in matches:
            result[topic.level].append(topic)

        return result

    def get_primary_level(self, text: str) -> str:
        """
        Get the most likely government level for a concern.

        Returns:
            'EU', 'FEDERAL', 'STATE', or 'MULTIPLE'
        """
        matches = self.match_topics(text)

        if not matches:
            return 'FEDERAL'  # Default to federal

        # Return level with highest total match count
        level_scores = {}
        for topic, match_count in matches:
            level = topic.level
            level_scores[level] = level_scores.get(level, 0) + match_count

        return max(level_scores.items(), key=lambda x: x[1])[0] if level_scores else 'FEDERAL'
