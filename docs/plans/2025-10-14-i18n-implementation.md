# German + English Internationalization Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Implement full bilingual support (German + English) using Django's built-in i18n system.

**Architecture:** Configure Django i18n settings, wrap all UI strings in gettext translation functions, create German and English locale files (.po), add language switcher component, and configure URL patterns with language prefixes.

**Tech Stack:** Django 5.2 i18n framework, gettext, .po/.mo translation files, LocaleMiddleware

---

## Task 1: Configure Django i18n Settings

**Files:**
- Modify: `website/writethem/settings.py:104-146`

**Step 1: Write the failing test**

Create: `website/letters/tests/test_i18n.py`

```python
# ABOUTME: Tests for internationalization configuration and functionality.
# ABOUTME: Verifies language switching, URL prefixes, and translation completeness.

from django.test import TestCase
from django.conf import settings


class I18nConfigurationTests(TestCase):
    def test_i18n_enabled(self):
        """Test that USE_I18N is enabled."""
        self.assertTrue(settings.USE_I18N)

    def test_supported_languages(self):
        """Test that German and English are configured."""
        language_codes = [code for code, name in settings.LANGUAGES]
        self.assertIn('de', language_codes)
        self.assertIn('en', language_codes)

    def test_locale_paths_configured(self):
        """Test that LOCALE_PATHS is set."""
        self.assertTrue(len(settings.LOCALE_PATHS) > 0)
```

**Step 2: Run test to verify it fails**

Run: `uv run python manage.py test letters.tests.test_i18n::I18nConfigurationTests -v`
Expected: FAIL with assertion errors (USE_I18N=False, LANGUAGES not configured, LOCALE_PATHS not set)

**Step 3: Update settings.py**

In `website/writethem/settings.py`, replace lines 104-114:

```python
# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'de'
LANGUAGES = [
    ('de', 'Deutsch'),
    ('en', 'English'),
]

TIME_ZONE = 'Europe/Berlin'

USE_I18N = True
USE_L10N = True

USE_TZ = True

# Locale paths - where Django looks for .po files
LOCALE_PATHS = [
    BASE_DIR / 'locale',
]
```

**Step 4: Add LocaleMiddleware**

In `website/writethem/settings.py`, modify MIDDLEWARE list (lines 43-51):

```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # NEW - handles language detection
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]
```

**Step 5: Run test to verify it passes**

Run: `uv run python manage.py test letters.tests.test_i18n::I18nConfigurationTests -v`
Expected: PASS (3 tests)

**Step 6: Commit**

```bash
git add website/writethem/settings.py website/letters/tests/test_i18n.py
git commit -m "feat: configure Django i18n with German and English support"
```

---

## Task 2: Configure URL Patterns with Language Prefixes

**Files:**
- Modify: `website/writethem/urls.py`

**Step 1: Write the failing test**

Add to `website/letters/tests/test_i18n.py`:

```python
class I18nURLTests(TestCase):
    def test_german_url_prefix_works(self):
        """Test that German URL prefix is accessible."""
        response = self.client.get('/de/')
        self.assertEqual(response.status_code, 200)

    def test_english_url_prefix_works(self):
        """Test that English URL prefix is accessible."""
        response = self.client.get('/en/')
        self.assertEqual(response.status_code, 200)

    def test_set_language_endpoint_exists(self):
        """Test that language switcher endpoint exists."""
        from django.urls import reverse
        url = reverse('set_language')
        self.assertEqual(url, '/i18n/setlang/')
```

**Step 2: Run test to verify it fails**

Run: `uv run python manage.py test letters.tests.test_i18n::I18nURLTests -v`
Expected: FAIL (URLs not configured with language prefixes)

**Step 3: Update URLs configuration**

Replace entire contents of `website/writethem/urls.py`:

```python
"""
URL configuration for writethem project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.conf.urls.i18n import i18n_patterns
from django.views.i18n import set_language

urlpatterns = [
    # Language switcher endpoint (no prefix)
    path('i18n/setlang/', set_language, name='set_language'),
]

# All user-facing URLs get language prefix
urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    path('', include('letters.urls')),
    prefix_default_language=True,
)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

**Step 4: Run test to verify it passes**

Run: `uv run python manage.py test letters.tests.test_i18n::I18nURLTests -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add website/writethem/urls.py
git commit -m "feat: add i18n URL patterns with language prefixes"
```

---

## Task 3: Create Locale Directory Structure

**Files:**
- Create: `website/locale/` directory structure

**Step 1: Create directory structure**

Run:
```bash
cd website
mkdir -p locale/de/LC_MESSAGES
mkdir -p locale/en/LC_MESSAGES
```

**Step 2: Verify directories exist**

Run: `ls -la locale/`
Expected: Shows `de/` and `en/` directories

**Step 3: Create .gitkeep files**

Run:
```bash
touch locale/de/LC_MESSAGES/.gitkeep
touch locale/en/LC_MESSAGES/.gitkeep
```

This ensures git tracks the directory structure even before .po files are created.

**Step 4: Commit**

```bash
git add locale/
git commit -m "feat: create locale directory structure for translations"
```

---

## Task 4: Wrap Base Template Strings

**Files:**
- Modify: `website/letters/templates/letters/base.html`

**Step 1: Review current base template**

Run: `cat website/letters/templates/letters/base.html`

Identify all hardcoded strings that need translation.

**Step 2: Add i18n load tag and wrap strings**

At the top of `website/letters/templates/letters/base.html`, add after the first line:

```django
{% load i18n %}
```

Then wrap all user-facing strings with `{% trans %}` tags. For example:

- Navigation links: `{% trans "Home" %}`, `{% trans "Letters" %}`, `{% trans "Login" %}`, etc.
- Button text: `{% trans "Sign Out" %}`, `{% trans "Sign In" %}`, etc.
- Any other UI text

**Important:** The exact changes depend on the current template content. Wrap every hardcoded user-facing string.

**Step 3: Test template renders without errors**

Run: `uv run python manage.py runserver`
Visit: `http://localhost:8000/de/`
Expected: Page loads without template errors (strings still in English because .po files don't exist yet)

**Step 4: Commit**

```bash
git add website/letters/templates/letters/base.html
git commit -m "feat: wrap base template strings with i18n tags"
```

---

## Task 5: Add Language Switcher Component

**Files:**
- Modify: `website/letters/templates/letters/base.html`

**Step 1: Write the failing test**

Add to `website/letters/tests/test_i18n.py`:

```python
class LanguageSwitcherTests(TestCase):
    def test_language_switcher_present_in_page(self):
        """Test that language switcher form is present."""
        response = self.client.get('/de/')
        self.assertContains(response, 'name="language"')
        self.assertContains(response, 'Deutsch')
        self.assertContains(response, 'English')

    def test_language_switch_changes_language(self):
        """Test that submitting language form changes language."""
        response = self.client.post(
            '/i18n/setlang/',
            {'language': 'en', 'next': '/en/'},
            follow=True
        )
        self.assertEqual(response.status_code, 200)
        # Check cookie was set
        self.assertIn('django_language', response.cookies)
```

**Step 2: Run test to verify it fails**

Run: `uv run python manage.py test letters.tests.test_i18n::LanguageSwitcherTests -v`
Expected: FAIL (language switcher not present)

**Step 3: Add language switcher to base template**

In `website/letters/templates/letters/base.html`, add this component in an appropriate location (e.g., in the header/navigation area):

```django
<div class="language-switcher">
  <form action="{% url 'set_language' %}" method="post">
    {% csrf_token %}
    <input name="next" type="hidden" value="{{ request.get_full_path }}">
    <select name="language" onchange="this.form.submit()" aria-label="{% trans 'Select language' %}">
      {% get_current_language as CURRENT_LANGUAGE %}
      {% get_available_languages as AVAILABLE_LANGUAGES %}
      {% for lang_code, lang_name in AVAILABLE_LANGUAGES %}
        <option value="{{ lang_code }}" {% if lang_code == CURRENT_LANGUAGE %}selected{% endif %}>
          {{ lang_name }}
        </option>
      {% endfor %}
    </select>
  </form>
</div>
```

**Step 4: Run test to verify it passes**

Run: `uv run python manage.py test letters.tests.test_i18n::LanguageSwitcherTests -v`
Expected: PASS (2 tests)

**Step 5: Commit**

```bash
git add website/letters/templates/letters/base.html
git commit -m "feat: add language switcher component to base template"
```

---

## Task 6: Wrap Authentication Template Strings

**Files:**
- Modify: `website/letters/templates/registration/login.html`
- Modify: `website/letters/templates/registration/register.html`
- Modify: `website/letters/templates/registration/password_reset_form.html`
- Modify: `website/letters/templates/registration/password_reset_done.html`
- Modify: `website/letters/templates/registration/password_reset_confirm.html`
- Modify: `website/letters/templates/registration/password_reset_complete.html`

**Step 1: Add i18n load tag to each template**

For each template file listed above, add at the top (after `{% extends %}`):

```django
{% load i18n %}
```

**Step 2: Wrap all strings with trans tags**

For each template, wrap user-facing strings:
- Headings: `<h1>{% trans "Login" %}</h1>`
- Labels: `{% trans "Email" %}`, `{% trans "Password" %}`
- Buttons: `{% trans "Sign In" %}`, `{% trans "Register" %}`, `{% trans "Reset Password" %}`
- Messages: `{% trans "Forgot your password?" %}`, etc.

**Step 3: Test templates render**

Run: `uv run python manage.py runserver`
Visit each auth page:
- `/de/login/`
- `/de/register/`
- `/de/password-reset/`

Expected: Pages load without errors

**Step 4: Commit**

```bash
git add website/letters/templates/registration/
git commit -m "feat: wrap authentication template strings with i18n tags"
```

---

## Task 7: Wrap Letter List and Detail Template Strings

**Files:**
- Modify: `website/letters/templates/letters/letter_list.html`
- Modify: `website/letters/templates/letters/letter_detail.html`

**Step 1: Add i18n load tag**

Add to both templates after `{% extends %}`:

```django
{% load i18n %}
```

**Step 2: Wrap strings in letter_list.html**

Wrap all user-facing strings:
- Headings: `{% trans "Open Letters" %}`
- Buttons: `{% trans "Write Letter" %}`, `{% trans "Filter" %}`, `{% trans "Sort" %}`
- Labels: `{% trans "Topic" %}`, `{% trans "Signatures" %}`
- Empty states: `{% trans "No letters found" %}`

For pluralization (e.g., signature counts), use `{% blocktrans %}`:

```django
{% blocktrans count counter=letter.signatures.count %}
  {{ counter }} signature
{% plural %}
  {{ counter }} signatures
{% endblocktrans %}
```

**Step 3: Wrap strings in letter_detail.html**

Wrap all strings:
- Buttons: `{% trans "Sign Letter" %}`, `{% trans "Remove Signature" %}`, `{% trans "Share" %}`, `{% trans "Report" %}`
- Labels: `{% trans "Recipient" %}`, `{% trans "Published" %}`, `{% trans "Signatures" %}`
- Messages: `{% trans "You have signed this letter" %}`

**Step 4: Test templates render**

Run: `uv run python manage.py runserver`
Visit: `/de/letters/` and any letter detail page
Expected: Pages load without errors

**Step 5: Commit**

```bash
git add website/letters/templates/letters/letter_list.html website/letters/templates/letters/letter_detail.html
git commit -m "feat: wrap letter list and detail template strings with i18n tags"
```

---

## Task 8: Wrap Letter Creation Template Strings

**Files:**
- Modify: `website/letters/templates/letters/letter_form.html`

**Step 1: Add i18n load tag**

```django
{% load i18n %}
```

**Step 2: Wrap all strings**

Wrap:
- Headings: `{% trans "Write an Open Letter" %}`
- Form labels: `{% trans "Title" %}`, `{% trans "Content" %}`, `{% trans "Recipient" %}`
- Help text: `{% trans "Minimum 500 characters" %}`
- Warnings: `{% trans "Once published, letters cannot be edited" %}`
- Buttons: `{% trans "Publish Letter" %}`, `{% trans "Preview" %}`, `{% trans "Cancel" %}`

**Step 3: Update form class with verbose_name**

Modify: `website/letters/forms.py`

Add at the top:
```python
from django.utils.translation import gettext_lazy as _
```

For each form field, add `label` parameter:
```python
title = forms.CharField(
    label=_("Title"),
    max_length=200,
    help_text=_("A clear, concise title for your letter")
)
```

**Step 4: Test template renders**

Visit: `/de/letters/new/`
Expected: Page loads without errors

**Step 5: Commit**

```bash
git add website/letters/templates/letters/letter_form.html website/letters/forms.py
git commit -m "feat: wrap letter creation template and form strings with i18n"
```

---

## Task 9: Wrap Profile and Account Template Strings

**Files:**
- Modify: `website/letters/templates/letters/profile.html`
- Modify: `website/letters/templates/letters/account_delete.html`
- Modify: Any other account-related templates

**Step 1: Add i18n load tag to each template**

```django
{% load i18n %}
```

**Step 2: Wrap all strings**

Profile page:
- Headings: `{% trans "Your Profile" %}`, `{% trans "Authored Letters" %}`, `{% trans "Signed Letters" %}`
- Buttons: `{% trans "Edit Profile" %}`, `{% trans "Delete Account" %}`
- Labels: `{% trans "Email" %}`, `{% trans "Verified" %}`, `{% trans "Unverified" %}`

Account deletion:
- Warnings: `{% trans "This action cannot be undone" %}`
- Buttons: `{% trans "Confirm Deletion" %}`, `{% trans "Cancel" %}`

**Step 3: Test templates render**

Visit profile and account pages
Expected: Pages load without errors

**Step 4: Commit**

```bash
git add website/letters/templates/letters/profile.html website/letters/templates/letters/account_delete.html
git commit -m "feat: wrap profile and account template strings with i18n tags"
```

---

## Task 10: Extract Translation Strings to .po Files

**Files:**
- Create: `website/locale/de/LC_MESSAGES/django.po`
- Create: `website/locale/en/LC_MESSAGES/django.po`

**Step 1: Run makemessages for German**

Run:
```bash
cd website
uv run python manage.py makemessages -l de
```

Expected: Creates/updates `locale/de/LC_MESSAGES/django.po` with all translatable strings

**Step 2: Run makemessages for English**

Run:
```bash
uv run python manage.py makemessages -l en
```

Expected: Creates/updates `locale/en/LC_MESSAGES/django.po`

**Step 3: Verify .po files created**

Run:
```bash
ls -la locale/de/LC_MESSAGES/
ls -la locale/en/LC_MESSAGES/
```

Expected: Both show `django.po` files

**Step 4: Check .po file contents**

Run:
```bash
head -n 30 locale/de/LC_MESSAGES/django.po
```

Expected: Shows header and first few msgid/msgstr pairs

**Step 5: Commit**

```bash
git add locale/
git commit -m "feat: extract translatable strings to .po files"
```

---

## Task 11: Translate German Strings in .po File

**Files:**
- Modify: `website/locale/de/LC_MESSAGES/django.po`

**Step 1: Open German .po file**

Open `website/locale/de/LC_MESSAGES/django.po` for editing

**Step 2: Translate strings systematically**

Go through each `msgid` and add German translation to `msgstr`:

```po
#: letters/templates/letters/base.html:10
msgid "Home"
msgstr "Startseite"

#: letters/templates/letters/base.html:11
msgid "Letters"
msgstr "Briefe"

#: letters/templates/letters/base.html:12
msgid "Sign In"
msgstr "Anmelden"

#: letters/templates/letters/base.html:13
msgid "Sign Out"
msgstr "Abmelden"

#: letters/templates/letters/letter_list.html:5
msgid "Open Letters"
msgstr "Offene Briefe"

#: letters/templates/letters/letter_list.html:8
msgid "Write Letter"
msgstr "Brief Schreiben"

#: letters/templates/letters/letter_detail.html:15
msgid "Sign Letter"
msgstr "Brief Unterschreiben"

#: letters/templates/letters/letter_detail.html:18
msgid "Remove Signature"
msgstr "Unterschrift Entfernen"

#: letters/templates/letters/letter_detail.html:21
msgid "Share"
msgstr "Teilen"

#: letters/templates/letters/letter_form.html:5
msgid "Write an Open Letter"
msgstr "Einen Offenen Brief Schreiben"

#: letters/templates/letters/letter_form.html:10
msgid "Title"
msgstr "Titel"

#: letters/templates/letters/letter_form.html:11
msgid "Content"
msgstr "Inhalt"

#: letters/templates/letters/letter_form.html:12
msgid "Minimum 500 characters"
msgstr "Mindestens 500 Zeichen"

#: letters/templates/letters/letter_form.html:15
msgid "Once published, letters cannot be edited"
msgstr "Nach Veröffentlichung können Briefe nicht mehr bearbeitet werden"

#: letters/templates/letters/letter_form.html:20
msgid "Publish Letter"
msgstr "Brief Veröffentlichen"

#: letters/templates/registration/login.html:5
msgid "Login"
msgstr "Anmeldung"

#: letters/templates/registration/login.html:10
msgid "Email"
msgstr "E-Mail"

#: letters/templates/registration/login.html:11
msgid "Password"
msgstr "Passwort"

#: letters/templates/registration/login.html:15
msgid "Forgot your password?"
msgstr "Passwort vergessen?"

#: letters/templates/registration/register.html:5
msgid "Register"
msgstr "Registrieren"
```

**Note:** The exact strings will depend on what was extracted in Task 10. Translate ALL msgid entries systematically.

**Step 3: Save the file**

Ensure all translations are complete (no empty `msgstr ""` entries)

**Step 4: Commit**

```bash
git add locale/de/LC_MESSAGES/django.po
git commit -m "feat: add German translations to .po file"
```

---

## Task 12: Populate English .po File

**Files:**
- Modify: `website/locale/en/LC_MESSAGES/django.po`

**Step 1: Open English .po file**

Open `website/locale/en/LC_MESSAGES/django.po` for editing

**Step 2: Add identity translations**

For English, most translations are identity (msgstr = msgid):

```po
#: letters/templates/letters/base.html:10
msgid "Home"
msgstr "Home"

#: letters/templates/letters/base.html:11
msgid "Letters"
msgstr "Letters"
```

Go through all entries and copy msgid to msgstr (they should be identical for English).

**Step 3: Save the file**

**Step 4: Commit**

```bash
git add locale/en/LC_MESSAGES/django.po
git commit -m "feat: add English identity translations to .po file"
```

---

## Task 13: Compile Translation Files

**Files:**
- Create: `website/locale/de/LC_MESSAGES/django.mo`
- Create: `website/locale/en/LC_MESSAGES/django.mo`

**Step 1: Run compilemessages**

Run:
```bash
cd website
uv run python manage.py compilemessages
```

Expected: Creates `django.mo` files for both German and English

**Step 2: Verify .mo files created**

Run:
```bash
ls -la locale/de/LC_MESSAGES/
ls -la locale/en/LC_MESSAGES/
```

Expected: Both show `django.mo` files (binary format)

**Step 3: Test translations work**

Run: `uv run python manage.py runserver`

Visit `/de/` - should show German interface
Visit `/en/` - should show English interface

Use language switcher to toggle between languages.

**Step 4: Add .mo files to .gitignore**

Modify `.gitignore` in repository root, add:
```
# Compiled translation files (generated from .po)
*.mo
```

**Note:** .mo files are generated artifacts and don't need to be tracked in git.

**Step 5: Commit**

```bash
git add .gitignore
git commit -m "chore: add compiled translation files to .gitignore"
```

---

## Task 14: Create Translation Completeness Check Command

**Files:**
- Create: `website/letters/management/commands/check_translations.py`

**Step 1: Write the failing test**

Add to `website/letters/tests/test_i18n.py`:

```python
from django.core.management import call_command
from io import StringIO


class TranslationCompletenessTests(TestCase):
    def test_check_translations_command_exists(self):
        """Test that check_translations command can be called."""
        out = StringIO()
        call_command('check_translations', stdout=out)
        output = out.getvalue()
        self.assertIn('Deutsch', output)
        self.assertIn('English', output)
```

**Step 2: Run test to verify it fails**

Run: `uv run python manage.py test letters.tests.test_i18n::TranslationCompletenessTests -v`
Expected: FAIL (command doesn't exist)

**Step 3: Create management command**

Create: `website/letters/management/commands/check_translations.py`

```python
# ABOUTME: Management command to check translation completeness and report coverage.
# ABOUTME: Analyzes .po files to find untranslated strings and calculate coverage percentage.

from django.core.management.base import BaseCommand
from django.conf import settings
import pathlib


class Command(BaseCommand):
    help = "Check translation completeness for all configured languages"

    def add_arguments(self, parser):
        parser.add_argument(
            '--language',
            type=str,
            help='Check specific language (e.g., "de" or "en")',
        )

    def handle(self, *args, **options):
        locale_paths = settings.LOCALE_PATHS
        languages = settings.LANGUAGES

        target_language = options.get('language')

        if target_language:
            languages_to_check = [(target_language, None)]
        else:
            languages_to_check = languages

        for lang_code, lang_name in languages_to_check:
            self.check_language(locale_paths[0], lang_code, lang_name)

    def check_language(self, locale_path, lang_code, lang_name):
        """Check translation completeness for a single language."""
        po_file = pathlib.Path(locale_path) / lang_code / 'LC_MESSAGES' / 'django.po'

        if not po_file.exists():
            self.stdout.write(self.style.ERROR(
                f"\n{lang_code}: No .po file found at {po_file}"
            ))
            return

        total = 0
        translated = 0
        untranslated = []

        with open(po_file, 'r', encoding='utf-8') as f:
            current_msgid = None
            for line in f:
                line = line.strip()
                if line.startswith('msgid "') and not line.startswith('msgid ""'):
                    current_msgid = line[7:-1]  # Extract string between quotes
                    total += 1
                elif line.startswith('msgstr "'):
                    msgstr = line[8:-1]
                    if msgstr:  # Non-empty translation
                        translated += 1
                    elif current_msgid:
                        untranslated.append(current_msgid)
                    current_msgid = None

        if total == 0:
            self.stdout.write(self.style.WARNING(
                f"\n{lang_code}: No translatable strings found"
            ))
            return

        coverage = (translated / total) * 100
        display_name = lang_name if lang_name else lang_code

        self.stdout.write(self.style.SUCCESS(
            f"\n{display_name} ({lang_code}):"
        ))
        self.stdout.write(f"   Total strings: {total}")
        self.stdout.write(f"   Translated: {translated}")
        self.stdout.write(f"   Untranslated: {len(untranslated)}")
        self.stdout.write(f"   Coverage: {coverage:.1f}%")

        if untranslated:
            self.stdout.write(self.style.WARNING(
                f"\nMissing translations ({len(untranslated)}):"
            ))
            for msgid in untranslated[:10]:  # Show first 10
                self.stdout.write(f"   - {msgid}")
            if len(untranslated) > 10:
                self.stdout.write(f"   ... and {len(untranslated) - 10} more")
        else:
            self.stdout.write(self.style.SUCCESS(
                "\nAll strings translated!"
            ))
```

**Step 4: Run test to verify it passes**

Run: `uv run python manage.py test letters.tests.test_i18n::TranslationCompletenessTests -v`
Expected: PASS

**Step 5: Test command manually**

Run:
```bash
uv run python manage.py check_translations
```

Expected: Shows coverage report for both German and English

**Step 6: Commit**

```bash
git add website/letters/management/commands/check_translations.py
git commit -m "feat: add check_translations management command"
```

---

## Task 15: Update Documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/matching-algorithm.md` (add i18n section)

**Step 1: Update README with i18n information**

Add a new section to `README.md`:

```markdown
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
```

**Step 2: Add i18n section to matching-algorithm.md**

Add at the end of `docs/matching-algorithm.md`:

```markdown
## Internationalization

The constituency matching system works identically in both German and English:

- Addresses can be entered in German format (standard use case)
- UI language (German/English) does not affect geocoding or matching logic
- Representative names, constituency names, and geographic data remain in original German
- All user-facing labels and messages are translated
```

**Step 3: Commit**

```bash
git add README.md docs/matching-algorithm.md
git commit -m "docs: add internationalization documentation"
```

---

## Task 16: Run Full Test Suite and Verify

**Step 1: Run all tests**

Run:
```bash
cd website
uv run python manage.py test letters.tests.test_i18n letters.tests.test_address_matching letters.tests.test_topic_mapping letters.tests.test_constituency_suggestions
```

Expected: All tests pass (check total count)

**Step 2: Check translation completeness**

Run:
```bash
uv run python manage.py check_translations
```

Expected: 100% coverage for both languages (or report any missing translations)

**Step 3: Manual verification checklist**

Run: `uv run python manage.py runserver`

Test each page in both languages:

**German (`/de/`):**
- [ ] Homepage loads in German
- [ ] Login page in German
- [ ] Register page in German
- [ ] Letter list in German
- [ ] Letter detail in German
- [ ] Letter creation form in German
- [ ] Profile page in German
- [ ] Language switcher works (toggles to English)

**English (`/en/`):**
- [ ] Homepage loads in English
- [ ] Login page in English
- [ ] Register page in English
- [ ] Letter list in English
- [ ] Letter detail in English
- [ ] Letter creation form in English
- [ ] Profile page in English
- [ ] Language switcher works (toggles to German)

**Step 4: Check for untranslated strings**

While testing, look for any English text appearing on German pages (or vice versa). These indicate missed translations.

If found, add them to .po files, compile, and test again.

**Step 5: Create summary commit**

```bash
git add .
git commit -m "test: verify i18n implementation with full test suite"
```

---

## Verification Checklist

Before merging this feature:

- [ ] USE_I18N=True in settings
- [ ] LANGUAGES configured with German and English
- [ ] LOCALE_PATHS configured
- [ ] LocaleMiddleware added to MIDDLEWARE
- [ ] URL patterns use i18n_patterns()
- [ ] Language switcher present in base template
- [ ] All templates have `{% load i18n %}`
- [ ] All UI strings wrapped with `{% trans %}` or `{% blocktrans %}`
- [ ] German .po file fully translated (100% coverage)
- [ ] English .po file complete (identity translations)
- [ ] .mo files compile without errors
- [ ] check_translations command works
- [ ] All automated tests pass
- [ ] Manual testing in both languages successful
- [ ] Documentation updated
- [ ] No untranslated strings visible in UI

---

## Notes for Implementation

**Language policy:**
- All code (variables, functions, classes): English
- All comments and docstrings: English
- All translation keys (msgid in .po): English
- .po files contain actual translations

**Testing strategy:**
- TDD throughout: write test → verify fail → implement → verify pass → commit
- Run `uv run python manage.py test` frequently
- Use `uv run python manage.py runserver` for manual verification
- Use `check_translations` command to catch missing translations

**Common pitfalls:**
- Forgetting `{% load i18n %}` at top of templates
- Not using `gettext_lazy` in models/forms (use lazy version for class-level strings)
- Mixing `{% trans %}` and `{% blocktrans %}` incorrectly (use blocktrans for variables)
- Not recompiling after editing .po files (run compilemessages)

**Skills to reference:**
- @skills/testing/test-driven-development for TDD workflow
- @skills/debugging/systematic-debugging if tests fail unexpectedly
- @skills/collaboration/finishing-a-development-branch when merging back to feat/matching
