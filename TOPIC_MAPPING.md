# Topic-to-Constituency Mapping - WriteThem.eu

## ✅ Intelligent Representative Suggestions

WriteThem.eu now features **intelligent topic-to-constituency mapping** based on German constitutional competency distribution (Kompetenzverteilung).

When users describe their concerns, the system automatically suggests:
1. **Which government level** is responsible (EU / Federal / State)
2. **Which constituencies** are relevant
3. **Which representatives** they should contact

## How It Works

The system uses a comprehensive **topic taxonomy** based on:
- **EU Treaties** - EU competencies
- **German Basic Law (Grundgesetz)** - Article 73 (Federal exclusive), Article 74 (Federal concurrent)
- **State competencies** - Education, culture, police, regional planning

### Example Flow

**User Input**: "I want to see better train connections between cities"

**System Response**:
- **Matched Topic**: Federal Railways (FEDERAL)
- **Explanation**: Your concern appears to be related to 'Federal Railways', which is primarily a Federal level responsibility. This covers: Federal railway infrastructure and long-distance rail.
- **Suggested Constituency**: Bundestag (FEDERAL)
- **Suggested Representatives**: Lisa Schubert (Die Linke), Reza Asghari (CDU), etc.

## Topic Coverage

### EU Level (European Parliament)
- EU Trade & Customs
- EU Agricultural Policy (CAP)
- EU Competition & Single Market
- EU Environmental Standards
- EU Immigration & Borders
- EU Consumer Protection

### Federal Exclusive Competencies (Art. 73 GG)
- Defense & Military
- Foreign Policy
- Citizenship & Passports
- Currency & Federal Finance
- Federal Railways (Deutsche Bahn, ICE, long-distance)
- Telecommunications & Post

### Federal Concurrent Competencies (Art. 74 GG)
- Labor Law & Employment
- Social Security & Welfare
- Federal Health Policy
- Civil & Criminal Law
- Immigration Law
- Federal Infrastructure (Autobahn)
- Energy Policy
- Climate Protection
- Housing Policy

### State Exclusive Competencies
- Education & Schools
- Universities & Higher Education
- State Police
- State Roads & Local Transport (ÖPNV, buses, trams)
- Culture & Media
- State Health Services
- Regional Planning

### Shared Topics
- Environment (multiple levels)
- Digitalization (infrastructure=federal, schools=state)

## Usage

### Command Line Testing

Test the topic mapping with example concerns:

```bash
# Run predefined test cases
uv run python manage.py test_topic_mapping

# Test a custom concern
uv run python manage.py test_topic_mapping --concern "We need affordable housing"
uv run python manage.py test_topic_mapping --concern "School curriculum needs reform"
uv run python manage.py test_topic_mapping --concern "Deutsche Bahn is always late"
```

### In Python Code

```python
from letters.services import TopicSuggestionService

# Get full suggestions with representatives
result = TopicSuggestionService.suggest_representatives_for_concern(
    concern_text="I want to see better train connections between cities",
    user_address={
        'street_address': 'Unter den Linden 1',
        'postal_code': '10117',
        'city': 'Berlin',
        'state': 'Berlin'
    },
    limit=5  # Max representatives to suggest
)

print(result['explanation'])
# "Your concern appears to be related to 'Federal Railways', which is primarily
#  a Federal level responsibility..."

for rep in result['suggested_representatives']:
    print(f"{rep.full_name} ({rep.party})")
# Lisa Schubert (Die Linke)
# Reza Asghari (CDU)
# ...

# Or just get topic matches (lightweight)
topics = TopicSuggestionService.get_topic_suggestions(
    "We need better schools"
)

for topic in topics:
    print(f"{topic['name']} ({topic['level']}) - {topic['description']}")
# Education & Schools (STATE) - School system and education policy
```

## Real Examples

### Example 1: Federal Railways
```
Concern: "Deutsche Bahn is always late"
→ Matched: Federal Railways (FEDERAL)
→ Suggests: Bundestag representatives
```

### Example 2: State Education
```
Concern: "Our school curriculum needs reform"
→ Matched: Education & Schools (STATE)
→ Suggests: State parliament (Landtag) representatives
→ Note: Requires user address to determine which state
```

### Example 3: EU Trade
```
Concern: "We need stronger EU trade agreements"
→ Matched: EU Trade & Customs (EU)
→ Suggests: European Parliament MEPs from Germany
```

### Example 4: Federal Housing
```
Concern: "We need more affordable housing and rent control"
→ Matched: Housing Policy (FEDERAL)
→ Suggests: Bundestag representatives
```

### Example 5: State Transport
```
Concern: "Better bus services in my town"
→ Matched: State Roads & Transport (STATE)
→ Suggests: State parliament representatives
```

## Integration with Letter Creation

The topic suggestion service can be integrated into the letter creation workflow:

1. **User starts writing a letter**
2. **As they type their concern**, the system suggests:
   - Relevant policy areas
   - Appropriate government level
   - Specific representatives to contact
3. **User selects suggested representatives** or refines their search
4. **Letter is addressed correctly** to the competent authority

## Technical Details

### TopicSuggestionService

Located in `letters/services.py`:

**Methods**:
- `suggest_representatives_for_concern(concern_text, user_address, limit)` - Full suggestions with representatives
- `get_topic_suggestions(concern_text)` - Lightweight topic matching only

**Returns**:
```python
{
    'matched_topics': [(TopicArea, score), ...],
    'suggested_level': 'EU' | 'FEDERAL' | 'STATE' | 'MULTIPLE',
    'suggested_constituencies': [Constituency, ...],
    'suggested_representatives': [Representative, ...],
    'explanation': 'Human-readable explanation...'
}
```

### Topic Taxonomy

Located in `letters/topic_taxonomy.py`:

**Classes**:
- `TopicArea` - Dataclass representing a policy area
- `TopicMatcher` - Matches user text to topics

**Matching Algorithm**:
1. Convert user input to lowercase
2. Count keyword matches per topic
3. Sort topics by match count
4. Determine primary government level
5. Filter constituencies by level
6. Suggest representatives from those constituencies

### Keyword Matching

Each topic has a set of keywords. Examples:

**Federal Railways**:
- Keywords: "deutsche bahn", "db", "train", "ice", "intercity", "rail", "bahn"
- Matches: "Deutsche Bahn is late", "better train connections", "ICE delays"

**Education & Schools**:
- Keywords: "school", "education", "teacher", "curriculum", "gymnasium", "abitur"
- Matches: "school curriculum", "teacher hiring", "education policy"

## Address Integration

For **state-level topics**, the system can use the user's address to determine the specific state:

```python
result = TopicSuggestionService.suggest_representatives_for_concern(
    concern_text="Our schools need more funding",
    user_address={
        'postal_code': '80331',
        'city': 'München',
        'state': 'Bayern'
    }
)
# Suggests: Landtag Bayern representatives
```

Without an address, state-level suggestions will prompt the user to provide their location.

## Next Steps

### For UI/Frontend Integration

1. **Add topic suggestion to letter form**:
   - Call `get_topic_suggestions()` as user types
   - Show matched topics with explanations
   - Display suggested representatives

2. **Representative selection helper**:
   - Call `suggest_representatives_for_concern()` when user selects a topic
   - Pre-populate recipient field with suggested representatives
   - Show explanation of why these representatives are suggested

3. **Smart defaults**:
   - Use user's verified address from IdentityVerification
   - Auto-suggest state representatives for state topics
   - Guide users to the right level of government

### For Enhanced Matching

1. **Add more keywords** to existing topics based on user feedback
2. **Create new topics** for emerging policy areas
3. **Implement NLP/semantic matching** for better accuracy (optional)
4. **Track suggestion accuracy** and improve over time

## Data Sources

- **German Basic Law (Grundgesetz)**: https://www.gesetze-im-internet.de/gg/
- **EU Treaties**: https://eur-lex.europa.eu/
- **Bundeswahlleiterin**: https://www.bundeswahlleiterin.de/
- **Abgeordnetenwatch API**: https://www.abgeordnetenwatch.de/api

## 🎉 Result

Users can now describe their concerns in natural language, and WriteThem.eu will intelligently suggest the right representatives to contact based on **German constitutional competency distribution**!

Example:
- "Better train connections" → Federal (Deutsche Bahn)
- "School reform" → State (Education)
- "EU trade deals" → EU (European Parliament)
- "Affordable housing" → Federal (Housing policy)

**The system ensures letters are addressed to the right people who actually have the power to act on the concern!**
