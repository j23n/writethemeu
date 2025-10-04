# Repository Guide for Coding Agents

## Project Overview
WriteThem.eu is a Django 5.2 project (Python 3.13, dependency-managed with `uv`) that lets citizens draft open letters to political representatives at EU, federal, and state level. The single Django app `letters` owns all domain logic: data imports, recommendation services, identity stubs, and presentation.

## Directory Layout
- **pyproject.toml / uv.lock** – dependency metadata (install via `uv sync`).
- **main.py** – thin CLI entrypoint (mostly unused during normal development).
- **vision/** – forward-looking design notes (e.g. `vision/matching.md`).
- **TODO.md** – active follow-up items (e.g. integrate Wahlkreis GeoJSON).
- **website/** – Django project root.
  - **manage.py** – run Django management commands (always execute from `website/`).
  - **writethem/** – Django settings, URL routing, ASGI/WSGI configs.
  - **letters/** – core app: models, services, views, forms, templates, tests, management commands, constants, geo helpers, fixtures.

## Key Workflows
### Representative Sync
- `letters/services.py::RepresentativeSyncService` calls the Abgeordnetenwatch v2 API to import:
  - **Parliaments** (EU / Bundestag / Landtage) + terms
  - **Electoral districts & constituencies** (direct vs list scope)
  - **Representatives** with contact metadata, election mode, term dates
  - **Committees & memberships**
- Management command: `uv run python manage.py sync_representatives --level [eu|federal|state|all] [--state "Bayern"] [--dry-run]`
- Imported representatives store API payloads under `Representative.metadata` (`mandate`, `politician_id`, links, etc.).
- After imports we snapshot data for development in `letters/fixtures/` and `letters/data/db_snapshot.sqlite3`.

### Suggestion Engine
- `ConstituencySuggestionService` (in `letters/services.py`) analyses letter titles + optional PLZ:
  1. Tokenises the text, maps keywords to `TopicArea` taxonomy.
  2. Resolves postal codes to state/federal constituencies (currently via prefix heuristics; TODO: GeoJSON boundaries).
  3. Scores representatives by constituency proximity, topic overlap (committees/issues), and returns the top candidates plus suggested tags/keywords.
- HTMX partial `letters/templates/letters/partials/suggestions.html` renders live recommendations on the letter form.
- Regression tests in `letters/tests.py::SuggestionServiceTests` ensure PLZ- and keyword-driven picks behave as expected.

### Letters & Signatures
- `Letter` model links to a single representative; `Signature` records user participation.
- `Letter.signature_breakdown()` computes constituent/non-constituent counts using verified identity data.
- Letter author auto-signs on creation (`LetterCreateView`), and `letters/templates/letters/partials/letter_card.html` is the shared card view for lists, profiles, and suggestions.

### Identity Verification (Stub)
- `IdentityVerificationService` provides demo endpoints: `initiate_verification()` and `complete_verification()` (currently mark every attempt `VERIFIED`).
- Verification records capture street/PLZ/city/state, inferred constituency/parliament, and expiration timestamps.
- In production, swap the stubbed methods with a real provider (eID, POSTIDENT, etc.) then re-use the same storage and constituency linking.

### Admin, Fixtures, Tests
- Admin customisations live in `letters/admin.py`, exposing parliaments, representatives, committees, signatures, verification status, etc.
- Tests (`letters/tests.py`) cover letter flows, identity behaviour, and suggestion scoring. Run with `uv run python manage.py test letters`.
- Large representative datasets are stored as JSON fixture `letters/fixtures/parliament_seed.json`; keep it updated after major syncs if test data relies on it.

## Data Sources & Integrations
- **Abgeordnetenwatch API** – canonical source for parliaments, mandates, committees, response stats.
- **Bundestag vita JSON** (planned) – to enrich biographies/focus areas (see `vision/matching.md`).
- **Bundeswahlleiter Wahlkreis GeoJSON** (planned) – replace PLZ-prefix routing with true spatial lookups (`TODO.md`).
- Additional Landtag/EU feeds can slot into the planned `RepresentativeProfile` architecture.

## Commands Cheat Sheet
```bash
# Install dependencies
uv sync

# Apply migrations / run dev server
cd website
uv run python manage.py migrate
uv run python manage.py runserver

# Sync data
uv run python manage.py sync_representatives --level all

# Run tests
uv run python manage.py test letters
```

## Core Files to Know
- `letters/models.py` – domain schema (parliaments → representatives → letters/signatures/verification).
- `letters/services.py` – API clients, sync logic, suggestion engine, identity stubs.
- `letters/views.py` – list/detail/create views for letters, representative detail, profile.
- `letters/templates/letters/` – HTML templates; partials share UI across pages.
- `letters/forms.py` – letter creation form (with PLZ filtering), signature and report forms.
- `letters/management/commands/` – representative sync, topic/constituency testers, wahlkreis fetcher.
- `vision/matching.md` – long-term roadmap for accurate recipient matching and profile enrichment.

## Known Gaps / TODOs
- Integrate Wahlkreis GeoJSON to replace prefix-based constituency mapping (`TODO.md`).
- Build `RepresentativeProfile` importers (Abgeordnetenwatch detailed topics, Bundestag biographies, Landtag feeds) per `vision/matching.md`.
- Improve localization coverage (templates/forms still contain untranslated strings; see `letters/templates`).
- Replace identity stub with real provider when ready.

Keep this document up to date when you add cross-cutting features or change major workflows—it’s the quickest way for future agents to gain context.
