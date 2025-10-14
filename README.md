# WriteThem.eu

## Getting Started
1. Install dependencies with `uv sync`.
2. Run `uv run python manage.py migrate` from `website/` to bootstrap the database.
3. (Optional) Import representatives via `uv run python manage.py sync_representatives --level all`.
4. Download constituency boundaries: `uv run python manage.py fetch_wahlkreis_data` (required for accurate address-based matching).
5. Launch the dev server with `uv run python manage.py runserver` and visit http://localhost:8000/.

## Internationalization

WriteThem.eu supports German (default) and English.

### Using the Site

- Visit `/de/` for German interface
- Visit `/en/` for English interface
- Use the language switcher in the header to toggle languages
- Language preference is saved in a cookie

### For Developers

**Translation workflow:**

1. Wrap new UI strings with translation functions:
   - Templates: `{% trans "Text" %}` or `{% blocktrans %}`
   - Python: `gettext()` or `gettext_lazy()`

2. Extract strings to .po files:
   ```bash
   cd website
   uv run python manage.py makemessages -l de -l en
   ```

3. Translate strings in `.po` files:
   - Edit `locale/de/LC_MESSAGES/django.po` (German translations)
   - Edit `locale/en/LC_MESSAGES/django.po` (English, mostly identity translations)

4. Compile translations:
   ```bash
   uv run python manage.py compilemessages
   ```

5. Check translation completeness:
   ```bash
   uv run python manage.py check_translations
   ```

**Important:** All code, comments, and translation keys should be in English. Only .po files contain actual translations.

## Architecture
- **Frameworks**: Django 5.2 / Python 3.13 managed with `uv`. The project root holds dependency metadata; all Django code lives in `website/` (settings in `writethem/`, app logic in `letters/`).
- **Domain models**: `letters/models.py` defines parliaments, terms, constituencies, representatives, committees, letters, signatures, identity verification, and moderation reports. Relationships reflect multi-level mandates (EU/Federal/State) and committee membership.
- **Sync pipeline**: `RepresentativeSyncService` (in `letters/services.py`) calls the Abgeordnetenwatch v2 API to create/update parliaments, terms, electoral districts, constituencies, representatives, and committee memberships. Management command `sync_representatives` orchestrates the import.
- **Constituency matching**: `AddressGeocoder` converts full addresses to coordinates via OSM Nominatim (cached in `GeocodeCache`). `WahlkreisLocator` performs point-in-polygon lookups against official Bundestag GeoJSON boundaries. `ConstituencyLocator` integrates both with PLZ fallback. See `docs/matching-algorithm.md` for details.
- **Suggestion engine**: `ConstituencySuggestionService` analyses letter titles + addresses to recommend representatives, tags, and similar letters. The HTMX partial `letters/partials/suggestions.html` renders the live preview used on the letter form.
- **Identity & signatures**: `IdentityVerificationService` (stub) attaches address information to users; signature counts and verification badges are derived from the associated verification records.
- **Presentation**: Class-based views in `letters/views.py` back the main pages (letter list/detail, creation, representative detail, user profile). Templates under `letters/templates/` share layout via partials (e.g., `letter_card.html`).
- **Utilities**: Management commands in `letters/management/commands/` cover representative sync, taxonomy tests, and helper scripts. Tests in `letters/tests.py` exercise model behaviour, letter flows, and the suggestion service.
