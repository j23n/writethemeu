# Repository Guidelines

## Project Structure & Module Organization
- Root holds `pyproject.toml`, `uv.lock`, and entrypoint `main.py`; full Django code lives in `website/`.
- `website/manage.py` drives tasks, `website/writethem/` stores settings/URLs, and `website/letters/` contains app models, forms, views, templates, and URLs.
- Business integrations (geocoding, API sync, verification) reside in `website/letters/services.py` with companion commands under `website/letters/management/commands/`.

## Build, Test, and Development Commands
- `uv sync` installs dependencies; rerun when `pyproject.toml` changes.
- `uv run python manage.py migrate` applies SQLite migrations; commit generated migration files.
- `uv run python manage.py runserver` starts http://localhost:8000/ for local development.
- `uv run python manage.py test` (optionally `letters.tests`) runs the Django suite; use `sync_representatives --dry-run` to smoke-test API integrations without database writes.

## Coding Style & Naming Conventions
- Follow PEP 8 with four-space indents and type hints for new service methods, matching patterns in `letters/services.py`.
- Use PascalCase for models and class-based views, snake_case for functions, and keep imports grouped stdlib/third-party/local.
- Keep templates modular via `{% block %}` fragments inside `templates/letters/` rather than embedding logic in views.

## Testing Guidelines
- Extend `django.test.TestCase` in `website/letters/tests.py` or split into a `tests/` package; name methods `test_<behavior>`.
- Mock outbound requests (e.g., Abgeordnetenwatch, Nominatim) so tests stay deterministic and offline.
- Add regression coverage whenever services or management commands change; no hard coverage target, but every feature should land with at least one test.

## Commit & Pull Request Guidelines
- Write imperative, present-tense commit subjects; Conventional Commit prefixes (`feat:`, `fix:`, `chore:`) help highlight scope.
- Document issue links and manual test commands in commit or PR descriptions; attach screenshots for UI updates.
- Ensure PRs call out migrations, new environment variables, or cron-like command usage so reviewers can deploy safely.

## Security & Configuration Tips
- Move secrets such as `SECRET_KEY` and API tokens into environment variables before production; never commit live credentials.
- Clean `db.sqlite3` and other generated artifacts from branches unless intentionally updating fixtures, and respect API rate limits when scheduling sync jobs.
