# WriteThem.eu - Implementation Documentation

A Django-based platform for citizens to write open letters to their German political representatives, with optional identity verification to prove constituency membership.

## Features

### Core Functionality
- **Open Letters**: Users can write and publish open letters to political representatives
- **Topic Taxonomy**: Smart constituency suggestion based on user concerns using German constitutional division of powers
- **Signature System**: Public signatures with PPI (Personal Identifiable Information) redaction
- **Identity Verification**: Optional verification to prove constituency membership (currently stubbed)
- **Search & Filter**: Browse letters by keyword, tag, or representative
- **Report System**: Flag inappropriate letters for moderation

### Data Models
- **Constituency**: Political constituencies (federal/state/local) with legislative periods
- **Representative**: German political representatives linked to constituencies
- **TopicArea**: Policy taxonomy mapping user keywords to governmental levels (Federal/State/Local/EU)
- **Letter**: Open letters with tags and signature tracking
- **Signature**: User signatures with optional comments and verification status
- **IdentityVerification**: User verification with address-to-constituency mapping
- **Report**: Moderation system for flagging inappropriate content

## Setup

### Prerequisites
- Python 3.13+
- uv (Python package manager)

### Installation

1. Install dependencies:
```bash
uv sync
```

2. Run migrations:
```bash
cd website
uv run python manage.py migrate
```

3. Create a superuser:
```bash
uv run python manage.py createsuperuser
```

4. Load representative data:
```bash
uv run python manage.py sync_representatives
```

5. Run the development server:
```bash
uv run python manage.py runserver
```

6. Access the application:
- Main site: http://localhost:8000/
- Admin panel: http://localhost:8000/admin/

## Architecture

### Apps
- **letters**: Main application containing all models, views, and templates

### Key Components

#### Models (`letters/models.py`)
- Constituency: Electoral districts with hierarchical structure
- Representative: Politicians with term tracking
- TopicArea: Policy topic taxonomy mapping keywords to governmental levels
- Letter: Open letters with tag support
- Signature: User signatures with verification badges
- IdentityVerification: User verification with constituency mapping
- Report: Moderation system

#### Services (`letters/services.py`)
- **AddressConstituencyMapper**: Maps German addresses to constituencies using geocoding
- **IdentityVerificationService**: Handles identity verification flow (stubbed)
- **RepresentativeDataService**: Syncs representative data from Abgeordnetenwatch API
- **ConstituencySuggestionService**: Suggests constituencies and representatives based on user concerns using TopicArea taxonomy

#### Views (`letters/views.py`)
- Letter list with search/filter
- Letter detail with signatures
- Letter creation form
- User registration and authentication
- Profile with verification status
- Report functionality

#### Management Commands
- `sync_representatives`: Sync German political representatives from Abgeordnetenwatch API
- `load_topic_taxonomy`: Load policy topic taxonomy based on German constitutional division of powers
- `test_constituency_suggestion`: Test the constituency suggestion service with example queries

### Templates
- Base template with navigation
- Letter list with search and pagination
- Letter detail with signature form
- User authentication (login/register)
- User profile with verification

## API Integration Research

### Representative Data Sources

#### Federal Level
- **Bundestag API**: Official API with Python wrapper available at https://github.com/jschibberges/Bundestag-API
- **Abgeordnetenwatch API**: CC0-licensed data for federal and state representatives
  - Endpoint: https://www.abgeordnetenwatch.de/api/v2/politicians
  - Provides: Voting records, contact info, candidacies

#### State & Local Level
- State parliaments (Landtag): Abgeordnetenwatch covers major states
- Local representatives: Limited API availability, requires per-municipality implementation

### Topic-to-Constituency Mapping

**Implementation**: `ConstituencySuggestionService` in `letters/services.py`

**How it works**:
1. User describes their concern (e.g., "I want better train connections between cities")
2. Service matches keywords against TopicArea taxonomy (36 pre-loaded policy areas)
3. Returns suggested governmental level (Federal/State/Local/EU) based on German constitutional division of powers
4. Provides relevant constituencies and representatives
5. Explains the legal basis (e.g., "Art. 74(22) GG")

**Examples**:
- "Better intercity trains" → Federal (Deutsche Bahn, Art. 74(22,23) GG)
- "School curriculum reform" → State (Kulturhoheit der Länder)
- "More bike lanes in our city" → Local (Art. 28(2) GG)
- "Immigration policy" → Federal (Art. 74(4,6) GG)

**Data Source**: Based on Grundgesetz (German Basic Law) Articles 30, 70-74, 83 and established constitutional practice

### Address-to-Constituency Mapping

**Current Implementation**: `AddressConstituencyMapper` in `letters/services.py` using geocoding (Nominatim)

**How it works**:
1. Uses geocoding to get coordinates from address
2. Maps to appropriate state/local constituencies
3. Can be enhanced with constituency shapefiles from Bundeswahlleiterin for precise electoral district mapping

## Identity Verification

**Current Status**: Stubbed implementation

**Production Integration Points**:
- eID (German electronic ID)
- POSTIDENT
- Other European identity verification providers

**Flow**:
1. User initiates verification from profile
2. Provider verifies identity and returns address
3. Address is mapped to constituency using AddressConstituencyMapper
4. IdentityVerification record is created/updated
5. User's signatures show verification badge

## Features Implemented

### ✅ Completed
- [x] Core data models with migrations
- [x] Django admin configuration
- [x] Topic taxonomy system (36 policy areas based on Grundgesetz)
- [x] Constituency suggestion service based on user concerns
- [x] Representative sync command (working with Abgeordnetenwatch API)
- [x] API research and documentation
- [x] Address-to-constituency mapping service (geocoding implementation)
- [x] Letter creation and browsing
- [x] Search and filter functionality
- [x] Signature system with PPI redaction
- [x] Identity verification flow (stubbed)
- [x] Report functionality
- [x] User authentication
- [x] Responsive templates with verification badges

### 🔄 Stubbed (Ready for Production Implementation)
- Identity verification provider integration (eID, POSTIDENT)

## Usage

### Admin Panel
1. Log in at `/admin/`
2. Manage constituencies, representatives, letters, and reports
3. Review flagged content in Reports section

### User Flow
1. Register an account
2. Browse existing letters or create a new one
3. Sign letters you support
4. (Optional) Verify your identity to add credibility to your signatures
5. View your profile to see your letters and signatures

### Verification Flow (Stub)
1. Go to Profile
2. Click "Start Verification"
3. Click "Complete Verification (Stub)" to simulate verification
4. Your signatures will now show a "✓ Verified Constituent" badge

## Testing

### Test Credentials
- Username: `admin`
- Password: `admin123`

### Manual Testing Checklist
- [x] Create superuser and access admin
- [x] Run representative sync command
- [x] Register new user account
- [x] Create a letter
- [x] Sign a letter
- [x] Search and filter letters
- [x] Start verification process
- [x] Complete verification (stub)
- [x] Report a letter
- [x] View profile with verified status

## Production Deployment Considerations

### Required Enhancements
1. **Representative Data**:
   - Implement Bundestag API integration
   - Set up Abgeordnetenwatch API calls
   - Create scheduled tasks for data updates

2. **Constituency Mapping**:
   - Download and integrate Wahlkreis shapefiles
   - Implement geocoding service
   - Set up PostGIS for geospatial queries

3. **Identity Verification**:
   - Integrate with German eID or other providers
   - Implement secure callback handling
   - Add verification expiry management

4. **Security**:
   - Enable HTTPS
   - Configure production SECRET_KEY
   - Set up CSRF protection
   - Implement rate limiting

5. **Performance**:
   - Add database indexes
   - Implement caching (Redis)
   - Use CDN for static files
   - Optimize database queries

## License

This project is a proof-of-concept implementation for WriteThem.eu.

## Contributing

To extend the stubbed functionality:

1. **Representative Syncing**: Edit `letters/management/commands/sync_representatives.py`
2. **Address Mapping**: Edit `AddressConstituencyMapper` in `letters/services.py`
3. **Verification**: Edit `IdentityVerificationService` in `letters/services.py`

Refer to the research findings documented in the service files for API endpoints and integration approaches.
