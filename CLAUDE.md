# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Django 5.2.6 project called "writethem-eu" using Python 3.13+ and managed with `uv` for dependency management.

## Project Structure

- **Root**: Contains project metadata and a minimal `main.py` entrypoint
- **website/**: Django project root directory
  - **manage.py**: Django management command interface
  - **writethem/**: Main Django application package containing settings, URLs, ASGI/WSGI configuration

## Common Commands

### Environment Setup
```bash
# Dependencies are managed with uv
uv sync          # Install dependencies from uv.lock
```

### Django Development
```bash
# All Django commands run from website/ directory
cd website

# Run development server
python manage.py runserver

# Database migrations
python manage.py makemigrations
python manage.py migrate

# Create superuser for admin
python manage.py createsuperuser

# Django shell
python manage.py shell

# Run tests
python manage.py test

# Collect static files (production)
python manage.py collectstatic
```

## Architecture Notes

- **Django Settings**: Located at `website/writethem/settings.py`
  - Uses SQLite database (db.sqlite3)
  - DEBUG mode enabled (development)
  - Default Django apps installed (admin, auth, contenttypes, sessions, messages, staticfiles)

- **URL Configuration**: Main URL routing in `website/writethem/urls.py`
  - Currently only includes Django admin at `/admin/`

- **Python Version**: Requires Python >= 3.13 (specified in pyproject.toml and .python-version)
