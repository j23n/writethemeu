# Architecture Overview

## Project Overview
WriteThem.eu is a Django 5.2 project (Python 3.13, dependency-managed with `uv`) that enables citizens to draft open letters to political representatives at EU, federal, and state level. The application is bilingual (German/English) using Django's i18n framework. The single Django app `letters` owns all domain logic: data imports, recommendation services, identity verification, and presentation.

## Directory Structure
- **pyproject.toml / uv.lock** – Python dependency metadata (managed by `uv`)
- **website/** – Django project root
  - **manage.py** – Django management commands (always execute from `website/`)
  - **writethem/** – Project settings, URL routing, ASGI/WSGI configs
  - **letters/** – Core application
    - **models.py** – Domain schema (13 models)
    - **services/** – Business logic organized by domain
      - **abgeordnetenwatch_api_client.py** – API client for Abgeordnetenwatch
      - **constituency.py** – Constituency matching and suggestion engine
      - **geocoding.py** – Address geocoding and GeoJSON lookups
      - **identity.py** – Identity verification (stub)
      - **representative_sync.py** – Representative data import
      - **topics.py** – Topic matching and committee mapping
    - **views.py** – Letter list/detail/create, representative/committee detail, profile
    - **forms.py** – Letter creation, signatures, reports, verification
    - **templates/** – Django templates (base, letters, auth, partials)
    - **management/commands/** – Data sync, queries, utilities
    - **tests/** – Organized test suite (test_auth, test_letters, test_views, etc.)
      - **fixtures/** – Test data (minimal wahlkreise.geojson for geocoding tests)
    - **admin.py** – Django admin customizations
    - **fixtures/** – Seed data for development
  - **locale/** – Translation files (de/en)

## Core Domain Models
- **Parliament** → **ParliamentTerm** → **Constituency** – Hierarchical government structure
- **Representative** – Members of parliament with contact details, committees, metadata
- **Committee** ← **CommitteeMembership** → **Representative** – Committee assignments
- **Letter** → **Representative** – Open letters with title, content, publication date
- **Signature** → **Letter** + **User** – User signatures on letters
- **Tag** / **TopicArea** – Categorization and topic taxonomy
- **IdentityVerification** → **User** – Optional verification status and constituency
- **Report** → **Letter** – User-submitted reports for moderation
- **GeocodeCache** – Cached address-to-coordinates lookups

## Internationalization
The application is bilingual (German/English) using Django's i18n framework. URL patterns include language prefixes (`/de/`, `/en/`). All UI strings use translation functions (`{% trans %}` in templates, `gettext_lazy()` in Python). Translation files are in `website/locale/{de,en}/LC_MESSAGES/django.po`. A language switcher in the base template toggles between languages. The `check_translations` management command verifies translation completeness.

## Data Sync Pipeline

### 1. Constituency Sync (Run First)
`sync_wahlkreise` syncs constituencies from Abgeordnetenwatch API and validates against GeoJSON boundaries:
- Fetches parliaments, terms, districts, and electoral lists from API
- Creates `Parliament`, `ParliamentTerm`, and `Constituency` records
- Assigns `list_id` for geocoding: federal districts (`001`-`299`), state districts (`BY-0101`), EU at-large (`DE`)
- Electoral lists have no `list_id` (no geographic boundaries)
- Validates that all GeoJSON wahlkreise have matching constituencies in database

### 2. Representative Sync (Run Second)
`RepresentativeSyncService` imports representatives from Abgeordnetenwatch API:
- Representatives with contact metadata, party affiliation, election mode
- Links representatives to constituencies by `external_id` from API
- Handles both direct mandates (Direktmandat) and list seats (Listenmandat)
- Committees and committee memberships

Management commands:
- `sync_wahlkreise` – Creates constituencies from API (run first)
- `sync_representatives --level [eu|federal|state|all] [--state "Bayern"] [--dry-run]` – Imports representatives

Imported data stores full API payloads in `metadata` fields for future enrichment. Development snapshots saved in `letters/fixtures/parliament_seed.json` and `letters/data/db_snapshot.sqlite3`.

## Accurate Constituency Matching
Constituency matching uses a two-stage geocoding process:
1. **AddressGeocoder** converts German addresses to lat/lng coordinates via OSM Nominatim API with database caching (`GeocodeCache` model)
2. **WahlkreisLocator** performs point-in-polygon queries against GeoJSON boundaries using shapely to find federal and state constituencies

The `WahlkreisLocator.locate(latitude, longitude)` method returns matching constituencies. GeoJSON boundaries stored in `letters/data/` directory include federal Bundestag (299 districts) and state Landtag files for 9 states.

Query commands for debugging:
- `query_wahlkreis` – Find constituency by address or postal code
- `query_topics` – Find matching topics for letter text
- `query_representatives` – Find representatives by location/topics

## GeoJSON Boundary Data

Electoral district boundaries are stored as GeoJSON files in `letters/data/`:
- `wahlkreise.geojson` – Federal Bundestag constituencies (299 districts)
- `wahlkreise_{state}.geojson` – State Landtag constituencies (9 states available: BW, BY, BE, HB, NI, NW, ST, SH, TH)

The `WahlkreisLocator` service loads federal and state files on initialization. The `locate(latitude, longitude)` method returns a dict with `federal` and `state` constituency data, each containing `wkr_nr`, `wkr_name`, `land_name`, and `land_code`.

Attribution for all geodata sources is provided on the `/data-sources/` page.

## Representative Recommendation Engine
`ConstituencySuggestionService` (in `letters/services/constituency.py`) analyzes letter titles and user location to suggest relevant representatives:
1. **Topic Analysis** – Tokenizes text and maps keywords to `TopicArea` taxonomy
2. **Geographic Matching** – Resolves addresses/postal codes to constituencies using accurate geocoding
3. **Representative Scoring** – Scores candidates by constituency proximity, topic overlap (committees/issues), and election mode (direct vs. list)

Returns top candidates with explanations, suggested tags, and matched topics. HTMX partial `letters/templates/letters/partials/suggestions.html` renders live recommendations on the letter form.

## Letter Lifecycle
1. **Creation** – User drafts letter with title, content, and optional address
2. **Suggestion** – System recommends representatives based on topic + location
3. **Publication** – Letter is published (immutable after first signature)
4. **Auto-signature** – Author automatically signs on publication
5. **Signing** – Other users can add signatures
6. **Signature Breakdown** – `Letter.signature_breakdown()` computes constituent/non-constituent counts using verified identity data

Letter card component (`letters/templates/letters/partials/letter_card.html`) is shared across list views, profiles, and suggestions.

## Identity Verification (Stub)
`IdentityVerificationService` provides demo endpoints marking all attempts as `VERIFIED`. Verification records capture street/PLZ/city/state, inferred constituency/parliament, and expiration timestamps. Production implementation requires integrating third-party provider (see `docs/plans/2025-10-10-identity-verification.md`).

### Constituency Data Model

The `Constituency` model represents parliamentary electoral units:
- **Scope types**: `FEDERAL_DISTRICT`, `FEDERAL_STATE_LIST`, `FEDERAL_LIST`, `STATE_DISTRICT`, `STATE_LIST`, `STATE_REGIONAL_LIST`, `EU_AT_LARGE`
- **list_id**: Geographic identifier for geocoding (e.g., `001`-`299` for federal districts, `BY-0101` for state districts, `DE` for EU)
- **external_id**: Abgeordnetenwatch API identifier
- Electoral lists (party lists) have no `list_id` as they lack geographic boundaries

Linked to `ParliamentTerm` and stores metadata from API. The `list_id` field enables matching physical addresses to constituencies during geocoding.

## Authentication & User Management
- Double opt-in email verification for new accounts
- Password reset flow with email confirmation
- User profile showing authored letters, signed letters, and verification status
- Account deletion with confirmation step
- All auth views use custom templates in `letters/templates/registration/`

## Topic Taxonomy
- `TopicArea` model stores hierarchical topic structure (federal/state/local levels)
- `load_topic_taxonomy` command loads taxonomy from JSON/YAML
- `map_committees_to_topics` automatically maps committee names to topics
- Topics drive representative recommendations and letter categorization

## Admin Interface
Django admin (`letters/admin.py`) exposes all models with customizations:
- Parliament/representative hierarchies
- Letter/signature management
- Committee assignments
- Identity verification status
- Report moderation

## Testing Strategy
Comprehensive test suite organized in `letters/tests/`:
- **test_fixtures.py** – Shared `ParliamentFixtureMixin` for reusable test setup
- **test_auth.py** – Account registration, deletion, password reset flows
- **test_letters.py** – Letter creation, form filtering, and representative selection
- **test_identity_verification.py** – Verification linking and address forms
- **test_views.py** – Competency pages and profile address management
- **test_template_filters.py** – Markdown rendering and HTML sanitization
- **test_address_matching.py** – Address geocoding with mocked OSM Nominatim, point-in-polygon constituency matching
- **test_constituency_suggestions.py** – Topic keyword matching, representative scoring
- **test_representative_sync.py** – Data import from Abgeordnetenwatch API
- **test_i18n.py** – Internationalization configuration and language switching

Test fixtures in `letters/tests/fixtures/`:
- **wahlkreise.geojson** – Minimal GeoJSON with 3 Länder (Berlin, Hamburg, Bayern) for geocoding tests

Run tests: `uv run python manage.py test letters`

## Data Sources
- **Abgeordnetenwatch API v2** – Representatives, parliaments, committees, mandates
- **Bundeswahlleiterin GeoJSON** – Official Bundestag constituency boundaries
- **OSM Nominatim** – Address geocoding (public API, cached in database)

## Management Commands
- `sync_wahlkreise` – Sync constituencies from Abgeordnetenwatch API and validate against GeoJSON
- `sync_representatives` – Import representatives and link to constituencies
- `load_topic_taxonomy` – Load topic hierarchy from file
- `map_committees_to_topics` – Auto-map committees to topics
- `query_wahlkreis` – Interactive constituency lookup
- `query_topics` – Interactive topic matching
- `query_representatives` – Interactive representative search
- `check_translations` – Verify i18n completeness
- `db_snapshot` – Save/load database snapshots for development

## Common Development Tasks

### Setup
```bash
uv sync                                    # Install dependencies
cd website
uv run python manage.py migrate           # Run migrations
uv run python manage.py sync_wahlkreise   # Sync constituencies from API
uv run python manage.py sync_representatives --level all  # Import representatives
uv run python manage.py runserver         # Start dev server
```

### Testing
```bash
uv run python manage.py test letters      # Run all tests
uv run python manage.py test letters.tests.test_i18n  # Specific test file
```

### Translations
```bash
uv run python manage.py makemessages -l de -l en  # Extract translatable strings
# Edit locale/de/LC_MESSAGES/django.po and locale/en/LC_MESSAGES/django.po
uv run python manage.py compilemessages            # Compile translations
uv run python manage.py check_translations         # Verify completeness
```

### Data Management
```bash
uv run python manage.py db_snapshot save my_snapshot    # Save database state
uv run python manage.py db_snapshot load my_snapshot    # Restore database state
```

## Key Design Decisions
- **Single app architecture** – All domain logic in `letters` app for simplicity
- **Service layer** – Business logic in `services/` module organized by domain, separate from views
- **Accurate geocoding** – OSM Nominatim + GeoJSON for precise constituency matching
- **Immutable letters** – Letters cannot be edited after first signature
- **Auto-signature** – Authors automatically sign their own letters
- **Stub verification** – Identity verification is stubbed for MVP, ready for production integration
- **Bilingual from start** – i18n infrastructure in place for German/English
