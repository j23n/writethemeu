# WriteThem.eu Localization Action Plan

## Overview
This document outlines the strategy for implementing comprehensive localization support for WriteThem.eu, with German as the primary target language while maintaining English for development and enabling future language support.

## Goals
1. **User-facing content in German**: All UI text, messages, emails
2. **Development in English**: Code, comments, documentation, technical terms
3. **Multi-language data handling**: Support API data in German, user content in German/English
4. **Future extensibility**: Framework supports adding French, Spanish, Italian, etc.

---

## Phase 1: Django i18n Infrastructure Setup

### 1.1 Settings Configuration
**File**: `website/writethem/settings.py`

```python
# Internationalization
LANGUAGE_CODE = 'de'  # Default to German
TIME_ZONE = 'Europe/Berlin'  # German timezone

USE_I18N = True  # Enable internationalization
USE_L10N = True  # Enable localized formatting (dates, numbers)
USE_TZ = True

# Supported languages
LANGUAGES = [
    ('de', 'Deutsch'),
    ('en', 'English'),
]

# Path for translation files
LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# Middleware for language detection
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # ADD THIS
    'django.middleware.common.CommonMiddleware',
    # ... rest of middleware
]
```

### 1.2 URL Configuration
**File**: `website/writethem/urls.py`

```python
from django.conf.urls.i18n import i18n_patterns
from django.urls import path, include

urlpatterns = [
    path('i18n/', include('django.conf.urls.i18n')),  # Language switcher
]

urlpatterns += i18n_patterns(
    path('admin/', admin.site.urls),
    path('', include('letters.urls')),
    prefix_default_language=True,  # URLs like /de/ or /en/
)
```

### 1.3 Template Context Processor
Ensure `django.template.context_processors.i18n` is in context processors (already enabled by USE_I18N).

---

## Phase 2: Code Localization

### 2.1 Template Strings
**Approach**: Use `{% trans %}` and `{% blocktrans %}` tags

**Example transformation** (`letters/templates/letters/base.html`):
```django
<!-- BEFORE -->
<h1>WriteThem.eu</h1>
<a href="{% url 'letter_list' %}">Letters</a>

<!-- AFTER -->
{% load i18n %}
<h1>WriteThem.eu</h1>
<a href="{% url 'letter_list' %}">{% trans "Letters" %}</a>
```

**Templates to localize** (priority order):
1. `base.html` - Navigation, footer, common elements
2. `letter_list.html` - Browse page, search form
3. `letter_detail.html` - Letter view, signature section
4. `letter_form.html` - Letter creation, suggestions
5. `representative_detail.html` - Representative profiles
6. `profile.html` - User profile
7. `register.html`, `login.html` - Authentication
8. `partials/suggestions.html` - HTMX suggestion panel

### 2.2 Python Code Strings
**Approach**: Use `gettext_lazy` for strings, `gettext` for runtime

**Example transformation** (`letters/models.py`):
```python
from django.utils.translation import gettext_lazy as _

class Letter(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', _('Draft')),
        ('PUBLISHED', _('Published')),
        ('FLAGGED', _('Flagged for Review')),
        ('REMOVED', _('Removed')),
    ]
```

**Files to localize**:
1. `models.py` - Model field labels, choices, help_text
2. `forms.py` - Form labels, help texts, validation messages
3. `views.py` - Flash messages (`messages.success()`, etc.)
4. `services.py` - User-facing explanation strings
5. `admin.py` - Admin interface labels

### 2.3 JavaScript Strings
**Approach**: Use Django's `javascript_catalog` view

**File**: `letters/urls.py`
```python
from django.views.i18n import JavaScriptCatalog

urlpatterns = [
    path('jsi18n/', JavaScriptCatalog.as_view(), name='javascript-catalog'),
]
```

**In templates**:
```django
<script src="{% url 'javascript-catalog' %}"></script>
<script>
  const message = gettext("Select");
  console.log(message);  // "Auswählen" in German
</script>
```

---

## Phase 3: Data Model Localization

### 3.1 Database Content Strategy
**Challenge**: API data (committees, representatives) is in German; topic taxonomy is in English

**Solutions**:

#### A. Translatable Model Fields (django-modeltranslation)
**Install**: `uv add django-modeltranslation`

**Use for**: TopicArea, Committee descriptions where we control content

```python
# letters/translation.py
from modeltranslation.translator import register, TranslationOptions
from .models import TopicArea

@register(TopicArea)
class TopicAreaTranslationOptions(TranslationOptions):
    fields = ('name', 'description', 'keywords')
```

This creates `name_de`, `name_en`, `description_de`, etc. fields.

#### B. Keep API Data in Original Language
**For**: Representative names, committee names from API (already German)

**Approach**: Store as-is, no translation needed. These are proper nouns.

#### C. Topic Taxonomy Multi-Language
**File**: `letters/management/commands/load_topic_taxonomy.py`

Update to create both German and English versions:
```python
TopicArea.objects.create(
    slug='federal-transportation',
    name_en='Federal Transportation',
    name_de='Bundesverkehr',
    description_en='Deutsche Bahn, intercity trains, federal highways',
    description_de='Deutsche Bahn, Fernverkehr, Bundesstraßen',
    keywords_en='train, railway, Deutsche Bahn, ICE, highway',
    keywords_de='Zug, Bahn, Deutsche Bahn, ICE, Autobahn',
    # ...
)
```

### 3.2 User-Generated Content
**Letters and signatures**: Store in original language (German or English)

**Approach**:
- Add `language` field to Letter model: `language = models.CharField(max_length=5, default='de')`
- Detect language during creation (optional: use `langdetect` library)
- Display language badge on letters
- Allow filtering by language

---

## Phase 4: Translation File Creation

### 4.1 Generate Message Files
```bash
cd website
django-admin makemessages -l de
django-admin makemessages -l en
```

This creates:
- `locale/de/LC_MESSAGES/django.po`
- `locale/en/LC_MESSAGES/django.po`

### 4.2 Translation Workflow
**Tools**:
1. **Poedit** - GUI tool for translators
2. **Weblate** (future) - Web-based collaborative translation
3. **DeepL API** - Initial machine translation, human review

**Process**:
1. Developer runs `makemessages` after adding/changing strings
2. Translator edits `.po` files (manually or via Poedit)
3. Run `compilemessages` to generate `.mo` binary files
4. Restart server to load new translations

### 4.3 Example `.po` File
```po
# locale/de/LC_MESSAGES/django.po
msgid "Letters"
msgstr "Briefe"

msgid "Write a Letter"
msgstr "Brief schreiben"

msgid "Sign this letter"
msgstr "Brief unterzeichnen"

#: letters/models.py:45
msgid "Published"
msgstr "Veröffentlicht"
```

---

## Phase 5: Special Considerations

### 5.1 API Response Handling
**Challenge**: Abgeordnetenwatch API returns German text

**Approach**: **Keep as-is** - it's already in the target language
- Committee names: "Ausschuss für Verkehr" → Store directly
- Representative names: "Luise Amtsberg" → Store directly
- Party names: "BÜNDNIS 90/DIE GRÜNEN" → Store directly

**Exception**: If we add non-German parliament support (e.g., EU Parliament with MEPs from France):
- Store original language data
- Add `language` field to Committee, Representative if needed

### 5.2 Search and Matching
**Challenge**: Keyword matching in `ConstituencySuggestionService`

**Solution**: Match in **both languages**
```python
# Match against both German and English keywords
for topic in TopicArea.objects.all():
    keywords_de = topic.keywords_de.split(',') if topic.keywords_de else []
    keywords_en = topic.keywords_en.split(',') if topic.keywords_en else []
    all_keywords = keywords_de + keywords_en

    score = sum(1 for keyword in all_keywords if keyword.lower() in concern_lower)
```

### 5.3 Email Localization
**File**: Create `letters/emails.py`

```python
from django.core.mail import send_mail
from django.utils.translation import gettext as _
from django.template.loader import render_to_string

def send_verification_email(user, language='de'):
    with translation.override(language):
        subject = _('Verify your email address')
        message = render_to_string('emails/verification.html', {'user': user})
        send_mail(subject, message, 'noreply@writethem.eu', [user.email])
```

### 5.4 Date and Number Formatting
**Already handled** by `USE_L10N = True`

In templates:
```django
{{ letter.published_at|date:"SHORT_DATE_FORMAT" }}
<!-- German: "04.10.2025" -->
<!-- English: "10/04/2025" -->

{{ letter.signature_count|intcomma }}
<!-- German: "1.234" -->
<!-- English: "1,234" -->
```

---

## Phase 6: Language Switcher UI

### 6.1 Add Language Selector to Base Template
```django
<!-- base.html -->
{% load i18n %}
<form action="{% url 'set_language' %}" method="post">
  {% csrf_token %}
  <input name="next" type="hidden" value="{{ redirect_to }}">
  <select name="language" onchange="this.form.submit()">
    {% get_current_language as LANGUAGE_CODE %}
    {% get_available_languages as LANGUAGES %}
    {% for lang_code, lang_name in LANGUAGES %}
      <option value="{{ lang_code }}"{% if lang_code == LANGUAGE_CODE %} selected{% endif %}>
        {{ lang_name }}
      </option>
    {% endfor %}
  </select>
</form>
```

### 6.2 Language Detection Priority
Django checks in this order:
1. User selection (session/cookie)
2. `Accept-Language` HTTP header (browser preference)
3. `LANGUAGE_CODE` setting (default: 'de')

---

## Phase 7: Testing Strategy

### 7.1 Automated Tests
```python
# letters/tests/test_i18n.py
from django.test import TestCase
from django.utils.translation import activate

class LocalizationTestCase(TestCase):
    def test_german_interface(self):
        activate('de')
        response = self.client.get('/')
        self.assertContains(response, 'Briefe')  # Not "Letters"

    def test_english_interface(self):
        activate('en')
        response = self.client.get('/')
        self.assertContains(response, 'Letters')  # Not "Briefe"
```

### 7.2 Translation Coverage
**Tool**: `django-rosetta` - Web UI to check missing translations

```bash
uv add django-rosetta

# settings.py
INSTALLED_APPS += ['rosetta']

# urls.py
urlpatterns += [path('rosetta/', include('rosetta.urls'))]
```

Visit `/rosetta/` to see translation completeness.

---

## Implementation Checklist

### Immediate (Phase 1-2):
- [ ] Update `settings.py` with i18n configuration
- [ ] Add `LocaleMiddleware`
- [ ] Wrap template strings in `{% trans %}` (start with `base.html`)
- [ ] Wrap Python strings in `gettext_lazy`
- [ ] Run `makemessages -l de`
- [ ] Translate high-priority strings (navigation, buttons)
- [ ] Run `compilemessages`

### Short-term (Phase 3-4):
- [ ] Add `django-modeltranslation` for TopicArea
- [ ] Update `load_topic_taxonomy` command with German translations
- [ ] Add `language` field to Letter model
- [ ] Create translation workflow documentation
- [ ] Set up translation tools (Poedit)

### Medium-term (Phase 5-6):
- [ ] Localize all email templates
- [ ] Add language switcher to UI
- [ ] Update search/matching to use both languages
- [ ] Localize admin interface
- [ ] Add JavaScript i18n for HTMX components

### Long-term (Phase 7):
- [ ] Set up Weblate or similar for community translations
- [ ] Add automated translation coverage tests
- [ ] Document translation contribution guide
- [ ] Consider adding French/Italian/Spanish support

---

## File Structure After Implementation

```
website/
├── locale/
│   ├── de/
│   │   └── LC_MESSAGES/
│   │       ├── django.po     # German translations
│   │       └── django.mo     # Compiled German
│   └── en/
│       └── LC_MESSAGES/
│           ├── django.po     # English translations
│           └── django.mo     # Compiled English
├── letters/
│   ├── translation.py        # modeltranslation config
│   ├── templates/
│   │   └── emails/          # Localized email templates
│   └── locale/              # App-specific translations (optional)
└── writethem/
    └── settings.py          # i18n configuration
```

---

## Best Practices

1. **Always use lazy translation** in models, forms, class-level variables
2. **Use regular gettext** in views (runtime evaluation)
3. **Mark strings at definition**, not at usage
4. **Avoid string concatenation** - use format strings or `blocktrans`:
   ```django
   {# BAD #}
   {% trans "You have" %} {{ count }} {% trans "signatures" %}

   {# GOOD #}
   {% blocktrans count counter=count %}
     You have {{ counter }} signature
   {% plural %}
     You have {{ counter }} signatures
   {% endblocktrans %}
   ```
5. **Context for ambiguous words**:
   ```python
   # "Post" can mean "letter" or "submit"
   pgettext("noun", "Post")  # Brief
   pgettext("verb", "Post")  # Absenden
   ```
6. **Keep code in English** - only translate user-facing strings
7. **Test with `USE_I18N = False`** to ensure fallbacks work

---

## Resources

- [Django Internationalization Docs](https://docs.djangoproject.com/en/5.2/topics/i18n/)
- [django-modeltranslation](https://django-modeltranslation.readthedocs.io/)
- [Poedit](https://poedit.net/) - Translation editor
- [Weblate](https://weblate.org/) - Collaborative translation platform
- [DeepL API](https://www.deepl.com/pro-api) - Machine translation for first pass

---

## Expected Outcomes

1. **German as default**: All UI in German for German users
2. **English available**: Full English translation for international users/developers
3. **Mixed content handling**: API data (German) + UI (localized) works seamlessly
4. **Future-proof**: Easy to add French, Italian, Spanish, Dutch, etc.
5. **Maintainable**: Translation workflow integrated into development process
6. **Professional**: Proper pluralization, date formats, number formats per locale
