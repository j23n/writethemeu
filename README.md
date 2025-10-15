# WriteThem.eu

## Getting Started
1. Install dependencies with `uv sync`.
2. Run `uv run python manage.py migrate` from `website/` to bootstrap the database.
3. (Optional) Import representatives via `uv run python manage.py sync_representatives --level all`.
4. Download constituency boundaries: `uv run python manage.py fetch_wahlkreis_data`.
5. Launch the dev server with `uv run python manage.py runserver` and visit http://localhost:8000/.

## Useful Commands
```bash
# Data import and queries
uv run python manage.py sync_representatives --level all  # Import representative data
uv run python manage.py query_wahlkreis --postal-code 10115  # Find constituency
uv run python manage.py query_topics --text "climate change"  # Match topics
uv run python manage.py query_representatives --postal-code 10115  # Find reps

# Internationalization
uv run python manage.py check_translations  # Verify translation completeness
uv run python manage.py makemessages -l de -l en  # Extract translatable strings
uv run python manage.py compilemessages  # Compile translations

# Testing and snapshots
uv run python manage.py test letters  # Run test suite
uv run python manage.py db_snapshot save my_snapshot  # Save database state
```

## Architecture
See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for comprehensive documentation.
