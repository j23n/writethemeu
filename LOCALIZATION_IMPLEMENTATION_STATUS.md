# Localization Implementation Status

## ✅ Completed

### 1. Django Settings Configuration
- ✅ Added `LocaleMiddleware` to middleware stack
- ✅ Set `LANGUAGE_CODE = 'de'` (German default)
- ✅ Set `TIME_ZONE = 'Europe/Berlin'`
- ✅ Enabled `USE_I18N`, `USE_L10N`, `USE_TZ`
- ✅ Configured `LANGUAGES = [('de', 'Deutsch'), ('en', 'English')]`
- ✅ Set `LOCALE_PATHS = [BASE_DIR / 'locale']`

### 2. URL Configuration
- ✅ Added `i18n_patterns()` to `writethem/urls.py`
- ✅ Added language switcher endpoint `/i18n/`
- ✅ URLs now support `/de/` and `/en/` prefixes

### 3. Base Template Localization
- ✅ Added `{% load i18n %}` to `base.html`
- ✅ Localized navigation menu (Letters, Write Letter, Profile, Login, etc.)
- ✅ Localized footer text
- ✅ Added language switcher dropdown in footer
- ✅ Set HTML lang attribute to `{{ LANGUAGE_CODE }}`

### 4. Letter List Template
- ✅ Loaded i18n template tag
- ✅ Localized page title, headings
- ✅ Localized "About This" section
- ✅ Localized search form
- ✅ Localized "Popular tags"
- ✅ Localized "By", "To" labels
- ✅ Used `SHORT_DATE_FORMAT` for dates

### 5. Models Localization
- ✅ Added `from django.utils.translation import gettext_lazy as _`
- ✅ Localized `Constituency.LEVEL_CHOICES`
- ✅ Localized `Letter.STATUS_CHOICES`

### 6. Views Localization
- ✅ Added translation imports
- ✅ Localized flash messages:
  - "Your letter has been published..."
  - "You have already signed this letter."
  - "Your signature has been added!"
  - "Thank you for your report..."
  - "Welcome, %(username)s! Your account has been created."

### 7. Translation Files
- ✅ Created `locale/de/LC_MESSAGES/django.po` with ~50 translated strings
- ✅ All navigation, common UI elements translated
- ✅ All flash messages translated
- ✅ Model choices translated
- ✅ Proper plural forms configured

---

## 🚧 To Complete (requires gettext tools)

### Install GNU gettext
**On Ubuntu/Debian:**
```bash
sudo apt-get install gettext
```

**On macOS:**
```bash
brew install gettext
brew link gettext --force
```

**Verify installation:**
```bash
msgfmt --version
```

### Generate Complete Translation Files
Once gettext is installed:

```bash
cd /mnt/shared/dmp/website

# Generate message files (scans all code for translatable strings)
python manage.py makemessages -l de --ignore=venv
python manage.py makemessages -l en --ignore=venv

# This will update locale/de/LC_MESSAGES/django.po with ALL strings
# and create locale/en/LC_MESSAGES/django.po
```

### Translate Remaining Strings
Edit `locale/de/LC_MESSAGES/django.po` and translate any new strings found.

### Compile Translations
```bash
python manage.py compilemessages

# This creates django.mo binary files that Django uses
```

### Restart Server
```bash
python manage.py runserver
```

---

## 📝 Remaining Templates to Localize

### High Priority:
1. **`letter_detail.html`** - Letter view, signature section
   - Add `{% load i18n %}`
   - Wrap: "Signatures", "Sign this letter", "You have signed this letter", "Login to sign", "Report this letter"

2. **`letter_form.html`** - Letter creation
   - Add `{% load i18n %}`
   - Wrap: "Write an Open Letter", "Title:", "To Representative:", "Letter Body:", "Tags:", "Publish Letter", "Cancel"
   - Wrap: "Smart Suggestions", "Type your letter title..."

3. **`partials/suggestions.html`** - HTMX suggestions
   - Add `{% load i18n %}`
   - Wrap: "Our Interpretation", "Topic:", "Suggested Representatives", "Select", "View profile", "Related Keywords", "Similar Letters"

4. **`representative_detail.html`** - Representative profile
   - Add `{% load i18n %}`
   - Wrap: "Party:", "Constituency:", "Legislative Body:", "Term:", "Status:", "Committee Memberships", "Policy Competences", "Open Letters", "External Resources", "Write a Letter", "Quick Stats"

5. **`profile.html`** - User profile
6. **`login.html`** - Login page
7. **`register.html`** - Registration page

### Medium Priority:
8. **`report_letter.html`** - Report form
9. **Email templates** (when created)

---

## 🔧 Forms to Localize

Add to **`letters/forms.py`**:
```python
from django.utils.translation import gettext_lazy as _

class LetterForm(forms.ModelForm):
    class Meta:
        model = Letter
        fields = ['title', 'representative', 'body', 'tags']
        labels = {
            'title': _('Title'),
            'representative': _('To Representative'),
            'body': _('Letter Body'),
            'tags': _('Tags (optional)'),
        }
        help_texts = {
            'title': _('Describe your concern briefly'),
            'body': _('Write your letter here'),
        }
```

Similar updates for:
- `SignatureForm`
- `ReportForm`
- `LetterSearchForm`
- `UserRegisterForm`

---

## 📊 Model Help Text to Localize

Add `help_text=_("...")` to model fields in `letters/models.py`:

```python
# Example for Letter model
title = models.CharField(
    max_length=255,
    verbose_name=_("Title"),
    help_text=_("Brief description of your concern")
)

body = models.TextField(
    verbose_name=_("Letter body"),
    help_text=_("The content of your letter to the representative")
)
```

Do this for all user-facing models: Letter, Signature, Representative, etc.

---

## 🎨 JavaScript Localization (Future)

For JavaScript strings in `suggestions.html`:

1. Add to `letters/urls.py`:
```python
from django.views.i18n import JavaScriptCatalog

urlpatterns += [
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
]
```

2. In template:
```html
<script src="{% url 'javascript-catalog' %}"></script>
<script>
  const selectText = gettext("Select");  // Will be "Auswählen" in German
</script>
```

---

## 🌐 Services Localization

The `ConstituencySuggestionService` generates explanation text. Update in `letters/services.py`:

```python
from django.utils.translation import gettext as _

# In suggest_from_concern():
explanation_parts = [
    _('Your concern relates to %(topic)s (%(type)s).') % {
        'topic': primary_topic.name,
        'type': primary_topic.get_competency_type_display()
    }
]

if primary_topic.legal_basis:
    explanation_parts.append(_('Legal basis: %(basis)s') % {'basis': primary_topic.legal_basis})
```

---

## 📖 Admin Interface Localization

Django admin is already partially localized, but customize in `letters/admin.py`:

```python
from django.utils.translation import gettext_lazy as _

class LetterAdmin(admin.ModelAdmin):
    list_display = ['title', 'author', 'status', 'published_at']
    list_filter = ['status', 'published_at']
    search_fields = ['title', 'body']

    fieldsets = (
        (_('Content'), {
            'fields': ('title', 'body', 'representative')
        }),
        (_('Metadata'), {
            'fields': ('author', 'status', 'tags')
        }),
    )
```

---

## ✅ Testing Localization

### 1. Test German (Default)
Visit: `http://localhost:9090/de/`
- All navigation should be in German
- Flash messages should be in German
- Date format: DD.MM.YYYY

### 2. Test English
Visit: `http://localhost:9090/en/`
OR use the language switcher in footer
- All navigation should be in English
- Flash messages should be in English
- Date format: MM/DD/YYYY

### 3. Test Language Switcher
- Change language in footer dropdown
- Should redirect to same page in new language
- Language preference stored in session

### 4. Test Untranslated Strings
- Look for English text appearing when German is selected
- These indicate missing translations in `.po` file

---

## 📚 Translation Workflow (Ongoing)

1. **Developer adds new UI feature**
   ```python
   # In code:
   messages.success(request, _('New feature added!'))

   # In template:
   <h2>{% trans "New Feature" %}</h2>
   ```

2. **Extract new strings**
   ```bash
   python manage.py makemessages -l de --ignore=venv
   ```

3. **Translator edits .po file**
   Open `locale/de/LC_MESSAGES/django.po` in Poedit or text editor:
   ```po
   msgid "New feature added!"
   msgstr "Neue Funktion hinzugefügt!"
   ```

4. **Compile translations**
   ```bash
   python manage.py compilemessages
   ```

5. **Restart server**
   ```bash
   python manage.py runserver
   ```

---

## 🛠️ Recommended Tools

### Poedit (Translation Editor)
- Download: https://poedit.net/
- GUI for editing `.po` files
- Shows translation progress
- Validates formatting

### django-rosetta (Web-based Translation)
```bash
uv add django-rosetta

# settings.py
INSTALLED_APPS += ['rosetta']

# urls.py
urlpatterns += [path('rosetta/', include('rosetta.urls'))]
```
Visit `/rosetta/` to translate in web interface.

---

## 🎯 Current Translation Coverage

**Estimated coverage: ~40%**

- ✅ Navigation: 100%
- ✅ Base template: 100%
- ✅ Flash messages: 100%
- ✅ Model choices: 80%
- ✅ Letter list: 80%
- ⚠️ Letter detail: 0%
- ⚠️ Letter form: 0%
- ⚠️ Representative detail: 0%
- ⚠️ Forms: 0%
- ⚠️ Admin: 20% (Django's default)
- ⚠️ Services/explanations: 0%

---

## 📋 Next Steps

1. **Install gettext** (required for `makemessages`)
2. **Run `makemessages -l de --ignore=venv`**
3. **Translate any new strings** in the generated `.po` file
4. **Run `compilemessages`**
5. **Test both languages** (`/de/` and `/en/`)
6. **Localize remaining templates** (letter_detail, letter_form, representative_detail)
7. **Localize forms** (add labels, help_texts)
8. **Localize services** (explanation strings)
9. **Set up continuous translation workflow**

---

## 📞 Support

For translation questions:
- Django i18n docs: https://docs.djangoproject.com/en/5.2/topics/i18n/
- Translation format (gettext): https://www.gnu.org/software/gettext/manual/

For gettext installation:
- Linux: `apt-get install gettext`
- macOS: `brew install gettext && brew link gettext --force`
- Windows: https://mlocati.github.io/articles/gettext-iconv-windows.html
