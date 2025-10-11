# WriteThem.eu

## Getting Started
1. Install dependencies with `uv sync`.
2. Run `uv run python manage.py migrate` from `website/` to bootstrap the database.
3. (Optional) Import representatives via `uv run python manage.py sync_representatives --level all`.
4. Download constituency boundaries: `uv run python manage.py fetch_wahlkreis_data` (required for accurate address-based matching).
5. Launch the dev server with `uv run python manage.py runserver` and visit http://localhost:8000/.

## Architecture
- **Frameworks**: Django 5.2 / Python 3.13 managed with `uv`. The project root holds dependency metadata; all Django code lives in `website/` (settings in `writethem/`, app logic in `letters/`).
- **Domain models**: `letters/models.py` defines parliaments, terms, constituencies, representatives, committees, letters, signatures, identity verification, and moderation reports. Relationships reflect multi-level mandates (EU/Federal/State) and committee membership.
- **Sync pipeline**: `RepresentativeSyncService` (in `letters/services.py`) calls the Abgeordnetenwatch v2 API to create/update parliaments, terms, electoral districts, constituencies, representatives, and committee memberships. Management command `sync_representatives` orchestrates the import.
- **Constituency matching**: `AddressGeocoder` converts full addresses to coordinates via OSM Nominatim (cached in `GeocodeCache`). `WahlkreisLocator` performs point-in-polygon lookups against official Bundestag GeoJSON boundaries. `ConstituencyLocator` integrates both with PLZ fallback. See `docs/matching-algorithm.md` for details.
- **Suggestion engine**: `ConstituencySuggestionService` analyses letter titles + addresses to recommend representatives, tags, and similar letters. The HTMX partial `letters/partials/suggestions.html` renders the live preview used on the letter form.
- **Identity & signatures**: `IdentityVerificationService` (stub) attaches address information to users; signature counts and verification badges are derived from the associated verification records.
- **Presentation**: Class-based views in `letters/views.py` back the main pages (letter list/detail, creation, representative detail, user profile). Templates under `letters/templates/` share layout via partials (e.g., `letter_card.html`).
- **Utilities**: Management commands in `letters/management/commands/` cover representative sync, taxonomy tests, and helper scripts. Tests in `letters/tests.py` exercise model behaviour, letter flows, and the suggestion service.
