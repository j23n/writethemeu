# Privacy-First Wahlkreis Selection Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Refactor user profile to never store addresses, only constituency (Wahlkreis) IDs. Users can search by address to find their Wahlkreise, but addresses are never persisted.

**Architecture:** Single unified UI section with address search fields + constituency dropdowns. HTMX endpoint geocodes addresses and returns constituency data to auto-populate dropdowns. Only constituency foreign keys are saved to database. Address fields removed from IdentityVerification model.

**Tech Stack:** Django, HTMX, Tom Select (dropdown filtering), existing AddressGeocoder + WahlkreisLocator services

---

## Task 1: Create HTMX Endpoint for Wahlkreis Search

**Files:**
- Modify: `website/letters/views.py` (add new view after line 615)
- Modify: `website/letters/urls.py` (add URL route)

**Step 1: Write failing test for wahlkreis search endpoint**

Create test file: `website/letters/tests/test_wahlkreis_search.py`

```python
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse


class WahlkreisSearchTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.client.login(username='testuser', password='testpass')
        self.url = reverse('search_wahlkreis')

    def test_search_wahlkreis_requires_authentication(self):
        """Unauthenticated users cannot search"""
        self.client.logout()
        response = self.client.post(self.url, {
            'street_address': 'Platz der Republik 1',
            'postal_code': '11011',
            'city': 'Berlin'
        })
        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_search_wahlkreis_with_valid_address(self):
        """Valid address returns constituency data as JSON"""
        response = self.client.post(self.url, {
            'street_address': 'Platz der Republik 1',
            'postal_code': '11011',
            'city': 'Berlin'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('success', data)
        self.assertTrue(data['success'])
        self.assertIn('wahlkreis_nr', data)
        self.assertIn('wahlkreis_name', data)

    def test_search_wahlkreis_with_invalid_address(self):
        """Invalid address returns error message"""
        response = self.client.post(self.url, {
            'street_address': 'Nonexistent Street 999',
            'postal_code': '99999',
            'city': 'Nowhere'
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('success', data)
        self.assertFalse(data['success'])
        self.assertIn('error', data)

    def test_search_wahlkreis_missing_fields(self):
        """Missing required fields returns error"""
        response = self.client.post(self.url, {
            'street_address': 'Platz der Republik 1'
            # Missing postal_code and city
        }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('success', data)
        self.assertFalse(data['success'])
        self.assertIn('error', data)
```

**Step 2: Run test to verify it fails**

Run: `uv run python website/manage.py test letters.tests.test_wahlkreis_search -v`

Expected: FAIL with "NoReverseMatch: 'search_wahlkreis' is not a valid view function"

**Step 3: Add URL route**

In `website/letters/urls.py`, add to urlpatterns:

```python
path('api/search-wahlkreis/', views.search_wahlkreis, name='search_wahlkreis'),
```

**Step 4: Write minimal implementation**

In `website/letters/views.py`, add after line 615 (after `complete_verification`):

```python
from django.http import JsonResponse
from .services.geocoding import AddressGeocoder, WahlkreisLocator


@login_required
@require_http_methods(["POST"])
def search_wahlkreis(request):
    """
    HTMX endpoint: Search for Wahlkreis by address.
    Returns JSON with constituency data or error message.
    """
    street_address = request.POST.get('street_address', '').strip()
    postal_code = request.POST.get('postal_code', '').strip()
    city = request.POST.get('city', '').strip()

    # Validate required fields
    if not all([street_address, postal_code, city]):
        return JsonResponse({
            'success': False,
            'error': 'Please provide street address, postal code, and city.'
        })

    # Geocode address
    geocoder = AddressGeocoder()
    lat, lon, success, error_msg = geocoder.geocode(
        street=street_address,
        postal_code=postal_code,
        city=city,
        country='DE'
    )

    if not success:
        return JsonResponse({
            'success': False,
            'error': error_msg or 'Could not find address. Please check your input or select Wahlkreise manually.'
        })

    # Find Wahlkreis
    try:
        locator = WahlkreisLocator()
        result = locator.locate(lat, lon)

        if not result:
            return JsonResponse({
                'success': False,
                'error': 'Could not determine Wahlkreis for this location. Please select manually.'
            })

        wkr_nr, wkr_name, land_name = result

        return JsonResponse({
            'success': True,
            'wahlkreis_nr': wkr_nr,
            'wahlkreis_name': wkr_name,
            'land_name': land_name,
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': 'Search temporarily unavailable. Please select Wahlkreise manually.'
        })
```

**Step 5: Add import to views.py**

At top of `website/letters/views.py`, ensure import exists (should be around line 14):

```python
from django.views.decorators.http import require_http_methods
```

**Step 6: Run test to verify it passes**

Run: `uv run python website/manage.py test letters.tests.test_wahlkreis_search -v`

Expected: PASS (may show WahlkreisLocator cache warnings - that's okay)

**Step 7: Commit**

```bash
git add website/letters/views.py website/letters/urls.py website/letters/tests/test_wahlkreis_search.py
git commit -m "feat: add HTMX endpoint for wahlkreis search by address

- New /api/search-wahlkreis/ endpoint
- Uses AddressGeocoder + WahlkreisLocator
- Returns constituency data as JSON
- Validates inputs and handles errors gracefully"
```

---

## Task 2: Redesign Profile Template - Remove Verification Section

**Files:**
- Modify: `website/letters/templates/letters/profile.html:16-52`

**Step 1: Write test for profile page without verification section**

Add to `website/letters/tests/test_views.py`:

```python
def test_profile_page_does_not_show_verification_section(self):
    """Profile page should not display verification section"""
    self.client.login(username='testuser', password='testpass')
    response = self.client.get(reverse('profile'))
    self.assertEqual(response.status_code, 200)
    self.assertNotContains(response, 'Identity & Constituency')
    self.assertNotContains(response, 'Start Third-party Verification')
```

**Step 2: Run test to verify it fails**

Run: `uv run python website/manage.py test letters.tests.test_views.ProfileViewTestCase.test_profile_page_does_not_show_verification_section -v`

Expected: FAIL with "Response should not contain 'Identity & Constituency'"

**Step 3: Remove verification section from template**

In `website/letters/templates/letters/profile.html`, delete lines 15-52 (entire verification section):

```django
{# Remove from line 15: #}
    <div style="margin-top: 1rem;">
        <h3>{% trans "Identity & Constituency" %}</h3>
        ...
    </div>
{# Through line 52 #}
```

**Step 4: Run test to verify it passes**

Run: `uv run python website/manage.py test letters.tests.test_views.ProfileViewTestCase.test_profile_page_does_not_show_verification_section -v`

Expected: PASS

**Step 5: Commit**

```bash
git add website/letters/templates/letters/profile.html
git commit -m "refactor: remove unimplemented verification section from profile

The third-party verification feature is not yet implemented and was
causing user confusion. Removed entire section from profile template."
```

---

## Task 3: Redesign Profile Template - Replace Address Form with Unified Wahlkreis Section

**Files:**
- Modify: `website/letters/templates/letters/profile.html:54-110`

**Step 1: No test needed (visual change)**

This is a template redesign task. Visual changes will be validated manually.

**Step 2: Replace address and constituency sections with unified section**

In `website/letters/templates/letters/profile.html`, replace lines 54-110 with:

```django
    <div class="mt-4">
        <h3>{% trans "Your Constituencies" %}</h3>
        <p class="text-muted">
            {% trans "Select your Wahlkreise to help us recommend the right representatives. You can search by address or select manually from the dropdowns." %}
        </p>

        <form method="post" id="constituency-form" class="mt-3">
            {% csrf_token %}

            {# Address search section #}
            <div class="card mb-3" style="background-color: #f8f9fa;">
                <div class="card-body">
                    <h5 class="card-title">{% trans "Search by Address" %}</h5>
                    <p class="text-muted small">{% trans "Enter your address to automatically find your Wahlkreise. Your address will not be saved." %}</p>

                    <div class="row">
                        <div class="col-md-8 mb-2">
                            <label for="search_street" class="form-label">{% trans "Street and Number" %}</label>
                            <input type="text" id="search_street" name="search_street" class="form-control" placeholder="Platz der Republik 1">
                        </div>
                        <div class="col-md-4 mb-2">
                            <label for="search_postal_code" class="form-label">{% trans "Postal Code" %}</label>
                            <input type="text" id="search_postal_code" name="search_postal_code" class="form-control" placeholder="11011">
                        </div>
                    </div>
                    <div class="row">
                        <div class="col-md-8 mb-2">
                            <label for="search_city" class="form-label">{% trans "City" %}</label>
                            <input type="text" id="search_city" name="search_city" class="form-control" placeholder="Berlin">
                        </div>
                        <div class="col-md-4 mb-2 d-flex align-items-end">
                            <button type="button" id="search-button" class="btn btn-secondary w-100">
                                {% trans "Search" %}
                            </button>
                        </div>
                    </div>

                    {# Search result message area #}
                    <div id="search-message" class="mt-2"></div>
                </div>
            </div>

            {# Constituency selection section #}
            {% if constituency_form.non_field_errors %}
                <div class="alert alert-danger">{{ constituency_form.non_field_errors }}</div>
            {% endif %}

            {% for field in constituency_form %}
                <div class="form-group mb-3">
                    <label for="{{ field.id_for_label }}" class="form-label">{{ field.label }}</label>
                    {{ field }}
                    {% if field.errors %}
                        <div class="text-danger small">{{ field.errors|join:', ' }}</div>
                    {% endif %}
                    {% if field.help_text %}
                        <small class="form-text text-muted">{{ field.help_text }}</small>
                    {% endif %}
                </div>
            {% endfor %}

            <button type="submit" class="btn btn-primary">{% trans "Save Constituencies" %}</button>
        </form>
    </div>
```

**Step 3: Add JavaScript for HTMX interaction**

In the same file, modify the `{% block extra_js %}` section (around line 146) to add search functionality:

```django
{% block extra_js %}
<script>
document.addEventListener('DOMContentLoaded', function() {
    // Initialize Tom Select on constituency dropdowns
    const selectElements = document.querySelectorAll('.filterable-select');
    const selectInstances = {};

    selectElements.forEach(function(element) {
        selectInstances[element.id] = new TomSelect(element, {
            placeholder: element.getAttribute('data-placeholder') || 'Select...',
            allowEmptyOption: true,
            create: false,
            maxOptions: null,
            plugins: ['clear_button']
        });
    });

    // Handle address search
    const searchButton = document.getElementById('search-button');
    const searchMessage = document.getElementById('search-message');

    if (searchButton) {
        searchButton.addEventListener('click', function() {
            const street = document.getElementById('search_street').value.trim();
            const postalCode = document.getElementById('search_postal_code').value.trim();
            const city = document.getElementById('search_city').value.trim();

            if (!street || !postalCode || !city) {
                searchMessage.innerHTML = '<div class="alert alert-warning">{% trans "Please fill in all address fields." %}</div>';
                return;
            }

            // Show loading state
            searchButton.disabled = true;
            searchButton.textContent = '{% trans "Searching..." %}';
            searchMessage.innerHTML = '<div class="alert alert-info">{% trans "Searching for your Wahlkreis..." %}</div>';

            // Make HTMX request
            fetch('{% url "search_wahlkreis" %}', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': '{{ csrf_token }}',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: new URLSearchParams({
                    'street_address': street,
                    'postal_code': postalCode,
                    'city': city
                })
            })
            .then(response => response.json())
            .then(data => {
                searchButton.disabled = false;
                searchButton.textContent = '{% trans "Search" %}';

                if (data.success) {
                    searchMessage.innerHTML = '<div class="alert alert-success">{% trans "Found:" %} ' + data.wahlkreis_name + ' (' + data.land_name + ')</div>';

                    // Auto-populate dropdowns by finding matching options
                    // This is a simplified version - you may need to adjust based on actual option values
                    const federalSelect = selectInstances['id_federal_constituency'];
                    const stateSelect = selectInstances['id_state_constituency'];

                    if (federalSelect) {
                        // Search for matching federal constituency
                        const federalOptions = federalSelect.options;
                        for (let key in federalOptions) {
                            const option = federalOptions[key];
                            if (option.text && option.text.includes(data.wahlkreis_name)) {
                                federalSelect.setValue(option.value);
                                break;
                            }
                        }
                    }

                    if (stateSelect) {
                        // Search for matching state constituency
                        const stateOptions = stateSelect.options;
                        for (let key in stateOptions) {
                            const option = stateOptions[key];
                            if (option.text && option.text.includes(data.land_name)) {
                                stateSelect.setValue(option.value);
                                break;
                            }
                        }
                    }
                } else {
                    searchMessage.innerHTML = '<div class="alert alert-danger">' + data.error + '</div>';
                }
            })
            .catch(error => {
                searchButton.disabled = false;
                searchButton.textContent = '{% trans "Search" %}';
                searchMessage.innerHTML = '<div class="alert alert-danger">{% trans "An error occurred. Please try again." %}</div>';
            });
        });
    }
});
</script>
{% endblock %}
```

**Step 4: Test manually in browser**

1. Start dev server: `uv run python website/manage.py runserver`
2. Navigate to /profile
3. Enter an address and click Search
4. Verify dropdowns populate correctly
5. Verify save button persists selections

**Step 5: Commit**

```bash
git add website/letters/templates/letters/profile.html
git commit -m "refactor: redesign profile with unified wahlkreis selection

- Single section combining address search + manual selection
- Address search auto-populates dropdowns via HTMX
- Addresses are never saved to database
- Clear messaging that address is not persisted"
```

---

## Task 4: Update Profile View to Remove Address Form Logic

**Files:**
- Modify: `website/letters/views.py:314-346`

**Step 1: Write test for profile view without address form**

Add to `website/letters/tests/test_views.py`:

```python
def test_profile_post_only_accepts_constituency_form(self):
    """Profile POST should only handle constituency form, not address"""
    self.client.login(username='testuser', password='testpass')

    # Create test constituencies
    bundestag = Parliament.objects.create(
        name='Bundestag', level='FEDERAL', legislative_body='Bundestag', region='DE'
    )
    term = ParliamentTerm.objects.create(parliament=bundestag, name='20. Wahlperiode')
    federal_const = Constituency.objects.create(
        parliament_term=term, name='Berlin-Mitte', scope='FEDERAL_DISTRICT'
    )

    response = self.client.post(reverse('profile'), {
        'federal_constituency': federal_const.id,
        'state_constituency': ''
    })

    self.assertEqual(response.status_code, 302)  # Redirect after success

    # Verify constituency was saved
    verification = IdentityVerification.objects.get(user=self.user)
    self.assertEqual(verification.federal_constituency, federal_const)
```

**Step 2: Run test to verify current behavior**

Run: `uv run python website/manage.py test letters.tests.test_views.ProfileViewTestCase.test_profile_post_only_accepts_constituency_form -v`

Expected: May PASS or FAIL depending on current state - this establishes baseline

**Step 3: Simplify profile view to remove address form logic**

In `website/letters/views.py`, replace lines 314-362 with:

```python
    if request.method == 'POST':
        constituency_form = SelfDeclaredConstituencyForm(request.POST, user=user)

        if constituency_form.is_valid():
            IdentityVerificationService.self_declare(
                user=user,
                federal_constituency=constituency_form.cleaned_data['federal_constituency'],
                state_constituency=constituency_form.cleaned_data['state_constituency'],
            )
            messages.success(
                request,
                _('Your constituency information has been updated.')
            )
            return redirect('profile')
    else:
        constituency_form = SelfDeclaredConstituencyForm(user=user)

    context = {
        'user_letters': user_letters,
        'user_signatures': user_signatures,
        'verification': verification,
        'constituency_form': constituency_form,
    }

    return render(request, 'letters/profile.html', context)
```

**Step 4: Remove IdentityVerificationForm import**

In `website/letters/views.py`, remove from imports (around line 30):

```python
IdentityVerificationForm  # Remove this from the import statement
```

**Step 5: Run test to verify it passes**

Run: `uv run python website/manage.py test letters.tests.test_views.ProfileViewTestCase.test_profile_post_only_accepts_constituency_form -v`

Expected: PASS

**Step 6: Run full test suite to verify no regressions**

Run: `uv run python website/manage.py test letters -v`

Expected: All tests PASS (some may be skipped)

**Step 7: Commit**

```bash
git add website/letters/views.py
git commit -m "refactor: simplify profile view to remove address form logic

- Removed address form submission handling
- Profile now only handles constituency selection
- Removed IdentityVerificationForm import"
```

---

## Task 5: Remove Address Fields from IdentityVerification Model

**Files:**
- Modify: `website/letters/models.py:586-590`
- Create: `website/letters/migrations/000X_remove_address_fields.py`

**Step 1: Write test to ensure constituency links still work without address fields**

Add to `website/letters/tests/test_identity_verification.py`:

```python
def test_verification_works_without_address_fields(self):
    """IdentityVerification should work with only constituency foreign keys"""
    user = User.objects.create_user(username='testuser', password='testpass')

    bundestag = Parliament.objects.create(
        name='Bundestag', level='FEDERAL', legislative_body='Bundestag', region='DE'
    )
    term = ParliamentTerm.objects.create(parliament=bundestag, name='20. Wahlperiode')
    constituency = Constituency.objects.create(
        parliament_term=term, name='Berlin-Mitte', scope='FEDERAL_DISTRICT'
    )

    verification = IdentityVerification.objects.create(
        user=user,
        status='SELF_DECLARED',
        verification_type='SELF_DECLARED',
        federal_constituency=constituency
    )

    self.assertTrue(verification.is_verified)
    self.assertEqual(verification.federal_constituency, constituency)
    constituencies = verification.get_constituencies()
    self.assertEqual(len(constituencies), 1)
    self.assertEqual(constituencies[0], constituency)
```

**Step 2: Run test to verify it passes with current model**

Run: `uv run python website/manage.py test letters.tests.test_identity_verification.TestIdentityVerificationWithoutAddress -v`

Expected: PASS (test should work with or without address fields)

**Step 3: Remove address fields from model**

In `website/letters/models.py`, remove lines 586-590:

```python
# Remove these lines:
    street_address = models.CharField(max_length=255, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=32, blank=True, default='DE')
```

**Step 4: Update normalized_state property**

Since we removed the `state` field, we need to update or remove the `normalized_state` property. In `website/letters/models.py`, around line 660, replace:

```python
@property
def normalized_state(self):
    return normalize_german_state(self.state)
```

With:

```python
@property
def normalized_state(self):
    """Get normalized state from linked constituencies"""
    states = self.get_constituency_states()
    return next(iter(states)) if states else None
```

**Step 5: Create migration**

Run: `uv run python website/manage.py makemigrations letters -n remove_address_fields`

Expected: Migration file created

**Step 6: Run migration on test database**

Run: `uv run python website/manage.py migrate letters`

Expected: Migration applies successfully

**Step 7: Run full test suite**

Run: `uv run python website/manage.py test letters -v`

Expected: All tests PASS (may need to fix tests that reference removed fields)

**Step 8: Check for any remaining references to removed fields**

Run: `grep -r "street_address\|postal_code.*city" website/letters/ --include="*.py" --exclude-dir=migrations`

Expected: Only show test files or comments, no production code

**Step 9: Commit**

```bash
git add website/letters/models.py website/letters/migrations/
git commit -m "refactor: remove address fields from IdentityVerification model

Privacy improvement: addresses are never persisted to database.
Users can search by address to find constituencies, but only
constituency foreign keys are stored.

- Removed street_address, postal_code, city, state, country fields
- Updated normalized_state property to derive from constituencies
- Migration removes columns from database"
```

---

## Task 6: Remove IdentityVerificationForm

**Files:**
- Modify: `website/letters/forms.py` (remove form class)

**Step 1: Check if form is imported anywhere**

Run: `grep -r "IdentityVerificationForm" website/ --include="*.py"`

Expected: Should only show forms.py definition and possibly old imports we already removed

**Step 2: Remove form class**

In `website/letters/forms.py`, find and delete the `IdentityVerificationForm` class definition (typically ~20-40 lines).

**Step 3: Run tests to ensure no breakage**

Run: `uv run python website/manage.py test letters -v`

Expected: All tests PASS

**Step 4: Commit**

```bash
git add website/letters/forms.py
git commit -m "refactor: remove unused IdentityVerificationForm

Form is no longer needed after profile redesign. Address input
is handled via HTMX search, not form submission."
```

---

## Task 7: Update Tests that Reference Address Fields

**Files:**
- Modify: Various test files that may reference removed address fields

**Step 1: Find tests referencing address fields**

Run: `grep -r "street_address\|verification\.postal_code\|verification\.city" website/letters/tests/ --include="*.py"`

Expected: List of test files with references

**Step 2: Update or remove affected tests**

For each test file found:
- If test is checking address storage: DELETE the test (feature removed)
- If test is checking constituency logic: UPDATE to use only constituency fields
- If test is checking geocoding: KEEP but ensure it doesn't test persistence

**Step 3: Run full test suite**

Run: `uv run python website/manage.py test letters -v`

Expected: All tests PASS

**Step 4: Commit**

```bash
git add website/letters/tests/
git commit -m "test: update tests after removing address field storage

- Removed tests for address persistence (feature removed)
- Updated constituency tests to use only FK fields
- Geocoding tests unchanged (still valid)"
```

---

## Task 8: Manual Testing and Documentation

**Files:**
- Update: `docs/ARCHITECTURE.md` (if exists)
- Update: `todo.md` (mark task complete)

**Step 1: Manual testing checklist**

Test the following scenarios:

1. **Address search flow:**
   - Navigate to /profile while logged in
   - Enter valid German address
   - Click "Search"
   - Verify dropdowns auto-populate
   - Click "Save"
   - Refresh page - verify selections persisted

2. **Manual selection flow:**
   - Navigate to /profile while logged in
   - Ignore address search
   - Select constituencies from dropdowns manually
   - Click "Save"
   - Refresh page - verify selections persisted

3. **Mixed flow:**
   - Search by address to populate dropdowns
   - Manually change one dropdown selection
   - Click "Save"
   - Verify final manual selection was saved

4. **Error handling:**
   - Enter invalid address (e.g., foreign country)
   - Verify error message appears
   - Verify dropdowns remain usable
   - Verify can still save manually

5. **Verification section removed:**
   - Confirm no "Identity & Constituency" section
   - Confirm no "Start Third-party Verification" button

**Step 2: Update todo.md**

In `todo.md`, update line 15:

```markdown
~~important: we never want to save a person's address. Hence, the profile page should be changed so that a user can search for their wahlkreise by entering an address. This calls our WahlkreisLocator (with htmx?) and returns the relevant Wahlkreise. THESE are then saved to the profile~~
DONE: Profile now uses HTMX address search without persisting addresses
```

**Step 3: Update ARCHITECTURE.md (if exists)**

If `docs/ARCHITECTURE.md` exists, add section about privacy-first design:

```markdown
## Privacy-First Constituency Selection

User addresses are **never stored** in the database. Users can search by address to find their electoral constituencies (Wahlkreise), but only the constituency foreign key relationships are persisted.

**Flow:**
1. User enters address in profile
2. HTMX endpoint geocodes address (via Nominatim API)
3. WahlkreisLocator finds matching constituencies
4. JavaScript auto-populates constituency dropdowns
5. User confirms/modifies and saves
6. Only Constituency FKs are stored in IdentityVerification

**Implementation:**
- `/api/search-wahlkreis/` endpoint (views.py:617)
- AddressGeocoder service (geocoding.py:18)
- WahlkreisLocator service (geocoding.py:224)
- Profile template HTMX integration (profile.html:146)
```

**Step 4: Final commit**

```bash
git add todo.md docs/
git commit -m "docs: update documentation for privacy-first wahlkreis selection

Marked todo item complete and documented architecture decision
to never persist user addresses."
```

---

## Final Verification

**Run full test suite one more time:**

```bash
uv run python website/manage.py test letters -v
```

**Expected:** 60+ tests passing, 0 failures

**Check for any stale code:**

```bash
# Should return nothing
grep -r "street_address" website/letters/*.py --exclude-dir=migrations
grep -r "IdentityVerificationForm" website/letters/*.py
```

**Visual inspection:**

1. Start dev server
2. Register new account
3. Complete profile with address search
4. Verify data saved correctly
5. Check database directly to confirm no address data

---

## Implementation Complete

All tasks completed. The profile page now:
- ✅ Never stores user addresses
- ✅ Allows address search to find Wahlkreise
- ✅ Auto-populates dropdowns from search results
- ✅ Falls back to manual selection
- ✅ Removed unimplemented verification section
- ✅ Maintains all existing constituency logic
- ✅ Preserves privacy while improving UX
