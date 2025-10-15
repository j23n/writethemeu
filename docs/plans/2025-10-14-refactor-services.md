# Services Refactoring Implementation Plan

> **For Claude:** Use `${SUPERPOWERS_SKILLS_ROOT}/skills/collaboration/executing-plans/SKILL.md` to implement this plan task-by-task.

**Goal:** Split monolithic `services.py` (2616 lines) into a clean `services/` package structure and fix the Saarland representative sync bug.

**Architecture:** Extract 7 classes into separate modules organized by responsibility. Fix the `mandate_won` filter bug that excludes 44 of 51 Saarland representatives. Add comprehensive tests for `RepresentativeSyncService`. Maintain backward compatibility via re-exports.

**Tech Stack:** Django, Python 3.13, pytest/Django test framework, AbgeordnetenwatchAPI

---

## Task 1: Create services package structure

**Files:**
- Create: `website/letters/services/__init__.py`
- Create: `website/letters/services/abgeordnetenwatch_api_client.py`

**Step 1: Create services directory**

```bash
mkdir -p website/letters/services
```

**Step 2: Extract AbgeordnetenwatchAPI to new module**

Create `website/letters/services/abgeordnetenwatch_api_client.py`:

```python
# ABOUTME: API client for fetching parliament and representative data from Abgeordnetenwatch.
# ABOUTME: Handles pagination and HTTP communication with the public Abgeordnetenwatch v2 API.

from typing import Any, Dict, List, Optional
import requests


class AbgeordnetenwatchAPI:
    """Thin client for the public Abgeordnetenwatch v2 API."""

    BASE_URL = "https://www.abgeordnetenwatch.de/api/v2"
    DEFAULT_PAGE_SIZE = 100

    @classmethod
    def _request(cls, endpoint: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        url = f"{cls.BASE_URL}/{endpoint}"
        print(f"GET {url} params={params}")
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    @classmethod
    def fetch_paginated(cls, endpoint: str, params: Optional[Dict] = None) -> List[Dict]:
        params = params or {}
        params.setdefault('page', 0)
        params.setdefault('pager_limit', cls.DEFAULT_PAGE_SIZE)

        results: List[Dict] = []
        while True:
            payload = cls._request(endpoint, params)
            data = payload.get('data', [])
            if not data:
                break
            results.extend(data)

            meta = payload.get('meta', {}).get('result', {})
            total = meta.get('total', len(results))
            if len(results) >= total:
                break
            params['page'] += 1
        return results

    @classmethod
    def get_parliaments(cls) -> List[Dict]:
        return cls.fetch_paginated('parliaments')

    @classmethod
    def get_parliament_periods(cls, parliament_id: int) -> List[Dict]:
        return cls.fetch_paginated('parliament-periods', {'parliament': parliament_id})

    @classmethod
    def get_candidacies_mandates(cls, parliament_period_id: int) -> List[Dict]:
        return cls.fetch_paginated('candidacies-mandates', {'parliament_period': parliament_period_id})

    @classmethod
    def get_electoral_list(cls, list_id: int) -> Dict:
        return cls._request(f'electoral-lists/{list_id}')['data']

    @classmethod
    def get_politician(cls, politician_id: int) -> Dict:
        return cls._request(f'politicians/{politician_id}')['data']

    @classmethod
    def get_committees(cls, parliament_period_id: Optional[int] = None) -> List[Dict]:
        """Fetch committees, optionally filtered by parliament period."""
        params = {}
        if parliament_period_id:
            params['field_legislature'] = parliament_period_id
        return cls.fetch_paginated('committees', params)

    @classmethod
    def get_committee_memberships(cls, parliament_period_id: Optional[int] = None) -> List[Dict]:
        """Fetch committee memberships, optionally filtered by parliament period."""
        params = {}
        if parliament_period_id:
            # Need to fetch committees first to filter memberships
            # For now, fetch all and filter in Python
            pass
        return cls.fetch_paginated('committee-memberships', params)
```

**Step 3: Create initial __init__.py with re-export**

Create `website/letters/services/__init__.py`:

```python
# ABOUTME: Service layer for the letters application.
# ABOUTME: Re-exports all service classes for backward compatibility with existing imports.

from .abgeordnetenwatch_api_client import AbgeordnetenwatchAPI

__all__ = [
    'AbgeordnetenwatchAPI',
]
```

**Step 4: Run existing tests to verify no breakage**

```bash
uv run python website/manage.py test letters.tests
```

Expected: All 19 tests pass (4 skipped)

**Step 5: Commit**

```bash
git add website/letters/services/
git commit -m "refactor: extract AbgeordnetenwatchAPI to services package"
```

---

## Task 2: Extract geocoding services

**Files:**
- Create: `website/letters/services/geocoding.py`
- Modify: `website/letters/services/__init__.py`

**Step 1: Extract geocoding classes**

Read lines 135-422 from `website/letters/services.py` to extract:
- `AddressGeocoder`
- `WahlkreisLocator`

Create `website/letters/services/geocoding.py` with these classes and their imports.

```bash
# Read the source to get exact implementation
head -422 website/letters/services.py | tail -288
```

**Step 2: Create geocoding.py**

Create `website/letters/services/geocoding.py`:

```python
# ABOUTME: Geocoding services for converting addresses to coordinates and Wahlkreise.
# ABOUTME: Uses OSM Nominatim for geocoding and GeoJSON boundary data for constituency mapping.

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.conf import settings
from shapely.geometry import Point, shape


class AddressGeocoder:
    """Geocodes German addresses using OSM Nominatim."""

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
    USER_AGENT = "WriteThemEU/1.0 (contact@writethemeu.org)"

    @classmethod
    def geocode(cls, address: str) -> Optional[Tuple[float, float]]:
        """
        Returns (latitude, longitude) for the given address, or None if not found.
        Respects Nominatim usage policy with 1-second delay.
        """
        params = {
            'q': address,
            'format': 'json',
            'limit': 1,
            'countrycodes': 'de',
            'addressdetails': 1,
        }
        headers = {'User-Agent': cls.USER_AGENT}

        time.sleep(1)

        try:
            response = requests.get(cls.NOMINATIM_URL, params=params, headers=headers, timeout=10)
            response.raise_for_status()
        except requests.RequestException:
            return None

        data = response.json()
        if not data:
            return None

        result = data[0]
        try:
            lat = float(result['lat'])
            lon = float(result['lon'])
            return (lat, lon)
        except (KeyError, ValueError):
            return None


class WahlkreisLocator:
    """Locates German Bundestag constituencies (Wahlkreise) from coordinates."""

    def __init__(self):
        geojson_path = Path(settings.BASE_DIR) / 'letters' / 'data' / 'wahlkreise.geojson'
        with open(geojson_path, 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)
        self.features = geojson_data.get('features', [])

    def locate(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """
        Returns Wahlkreis information for coordinates, or None if not found.

        Returns dict with keys:
            - wahlkreis_nummer: str (e.g., "001")
            - wahlkreis_name: str (e.g., "Flensburg – Schleswig")
            - land_name: str (e.g., "Schleswig-Holstein")
        """
        point = Point(lon, lat)

        for feature in self.features:
            polygon = shape(feature['geometry'])
            if polygon.contains(point):
                props = feature.get('properties', {})
                return {
                    'wahlkreis_nummer': props.get('WKR_NR'),
                    'wahlkreis_name': props.get('WKR_NAME'),
                    'land_name': props.get('LAND_NAME'),
                }
        return None
```

**Step 3: Update __init__.py**

Edit `website/letters/services/__init__.py`:

```python
# ABOUTME: Service layer for the letters application.
# ABOUTME: Re-exports all service classes for backward compatibility with existing imports.

from .abgeordnetenwatch_api_client import AbgeordnetenwatchAPI
from .geocoding import AddressGeocoder, WahlkreisLocator

__all__ = [
    'AbgeordnetenwatchAPI',
    'AddressGeocoder',
    'WahlkreisLocator',
]
```

**Step 4: Run tests**

```bash
uv run python website/manage.py test letters.tests
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add website/letters/services/
git commit -m "refactor: extract geocoding services to separate module"
```

---

## Task 3: Extract constituency services

**Files:**
- Create: `website/letters/services/constituency.py`
- Modify: `website/letters/services/__init__.py`

**Step 1: Read constituency-related code**

Read lines 424-734 from `website/letters/services.py`:
- `LocatedConstituencies` dataclass
- `LocationContext` dataclass
- `ConstituencyLocator`
- `ConstituencySuggestionService`

**Step 2: Create constituency.py**

Create `website/letters/services/constituency.py`:

```python
# ABOUTME: Services for locating constituencies and suggesting representatives based on addresses.
# ABOUTME: Combines geocoding, Wahlkreis mapping, and PLZ fallback for robust constituency resolution.

import logging
from dataclasses import dataclass
from typing import List, Optional

from django.db.models import Q

from ..models import Constituency, Representative
from .geocoding import AddressGeocoder, WahlkreisLocator

logger = logging.getLogger(__name__)


@dataclass
class LocatedConstituencies:
    """Result of constituency location with optional federal and state matches."""
    federal: Optional[Constituency] = None
    state: Optional[Constituency] = None


@dataclass
class LocationContext:
    """Context information from address geocoding and Wahlkreis lookup."""
    coordinates: Optional[tuple[float, float]] = None
    wahlkreis_nummer: Optional[str] = None
    wahlkreis_name: Optional[str] = None
    land_name: Optional[str] = None


class ConstituencyLocator:
    """Locates federal and state constituencies from addresses or postal codes."""

    def __init__(self):
        try:
            self.wahlkreis_locator = WahlkreisLocator()
        except FileNotFoundError as e:
            logger.warning("Failed to warm WahlkreisLocator cache: %s", e)
            self.wahlkreis_locator = None

    def locate_by_address(self, street: str, postal_code: str, city: str) -> tuple[LocatedConstituencies, LocationContext]:
        """
        Locate constituencies using full address geocoding.

        Returns:
            (LocatedConstituencies, LocationContext) tuple
        """
        address = f"{street}, {postal_code} {city}"
        context = LocationContext()

        if not self.wahlkreis_locator:
            logger.info("No wahlkreis data, falling back to PLZ")
            return self._fallback_by_plz(postal_code), context

        coordinates = AddressGeocoder.geocode(address)
        if not coordinates:
            logger.info("Geocoding failed for '%s', falling back to PLZ", address)
            return self._fallback_by_plz(postal_code), context

        context.coordinates = coordinates
        lat, lon = coordinates
        wahlkreis = self.wahlkreis_locator.locate(lat, lon)

        if not wahlkreis:
            logger.info("Coordinates (%.4f, %.4f) not in any Wahlkreis, falling back to PLZ", lat, lon)
            return self._fallback_by_plz(postal_code), context

        context.wahlkreis_nummer = wahlkreis.get('wahlkreis_nummer')
        context.wahlkreis_name = wahlkreis.get('wahlkreis_name')
        context.land_name = wahlkreis.get('land_name')

        located = LocatedConstituencies()
        located.federal = self._find_federal_constituency(context.wahlkreis_nummer)
        located.state = self._find_state_constituency(postal_code, context.land_name)

        return located, context

    def locate_by_plz(self, postal_code: str) -> tuple[LocatedConstituencies, LocationContext]:
        """
        Locate constituencies using only postal code (coarse resolution).

        Returns:
            (LocatedConstituencies, LocationContext) tuple
        """
        return self._fallback_by_plz(postal_code), LocationContext()

    def _fallback_by_plz(self, postal_code: str) -> LocatedConstituencies:
        """Fallback lookup using postal code prefix matching."""
        if not postal_code or len(postal_code) < 2:
            return LocatedConstituencies()

        located = LocatedConstituencies()

        # Try federal
        located.federal = Constituency.objects.filter(
            postal_codes__contains=[postal_code[:2]],
            parliament__level='FEDERAL'
        ).first()

        # Try state
        located.state = Constituency.objects.filter(
            postal_codes__contains=[postal_code[:2]],
            parliament__level='STATE'
        ).first()

        return located

    def _find_federal_constituency(self, wahlkreis_nummer: Optional[str]) -> Optional[Constituency]:
        """Find federal constituency by Wahlkreis number."""
        if not wahlkreis_nummer:
            return None
        return Constituency.objects.filter(
            electoral_district=wahlkreis_nummer,
            parliament__level='FEDERAL'
        ).first()

    def _find_state_constituency(self, postal_code: str, land_name: Optional[str]) -> Optional[Constituency]:
        """Find state constituency by postal code and state name."""
        if not postal_code or not land_name:
            return None
        return Constituency.objects.filter(
            postal_codes__contains=[postal_code[:2]],
            parliament__level='STATE',
            parliament__region__iexact=land_name
        ).first()


class ConstituencySuggestionService:
    """Suggests constituencies and representatives based on user address."""

    @staticmethod
    def suggest_constituencies(street: str, postal_code: str, city: str) -> dict:
        """
        Returns suggestions for federal and state representatives.

        Returns dict with keys:
            - federal_constituency: Constituency or None
            - state_constituency: Constituency or None
            - federal_representatives: QuerySet[Representative]
            - state_representatives: QuerySet[Representative]
            - used_fallback: bool
            - debug_info: dict
        """
        locator = ConstituencyLocator()

        try:
            located, context = locator.locate_by_address(street, postal_code, city)
        except Exception as e:
            logger.error("Error during address-based lookup for %s, %s %s: %s",
                        street, postal_code, city, e, exc_info=True)
            located, context = locator.locate_by_plz(postal_code), LocationContext()

        federal_reps = Representative.objects.none()
        state_reps = Representative.objects.none()

        used_fallback = context.wahlkreis_nummer is None

        if located.federal:
            federal_reps = Representative.objects.filter(
                terms__constituencies=located.federal,
                terms__parliament__level='FEDERAL'
            ).distinct()
            if not federal_reps.exists():
                logger.info("No representatives found for WK %s, falling back to PLZ",
                           context.wahlkreis_nummer or '??')
                located_plz, _ = locator.locate_by_plz(postal_code)
                if located_plz.federal:
                    located.federal = located_plz.federal
                    federal_reps = Representative.objects.filter(
                        terms__constituencies=located_plz.federal,
                        terms__parliament__level='FEDERAL'
                    ).distinct()
                    used_fallback = True

        if located.state:
            state_reps = Representative.objects.filter(
                terms__constituencies=located.state,
                terms__parliament__level='STATE'
            ).distinct()

        return {
            'federal_constituency': located.federal,
            'state_constituency': located.state,
            'federal_representatives': federal_reps,
            'state_representatives': state_reps,
            'used_fallback': used_fallback,
            'debug_info': {
                'coordinates': context.coordinates,
                'wahlkreis_nummer': context.wahlkreis_nummer,
                'wahlkreis_name': context.wahlkreis_name,
                'land_name': context.land_name,
            }
        }
```

**Step 3: Update __init__.py**

```python
# ABOUTME: Service layer for the letters application.
# ABOUTME: Re-exports all service classes for backward compatibility with existing imports.

from .abgeordnetenwatch_api_client import AbgeordnetenwatchAPI
from .geocoding import AddressGeocoder, WahlkreisLocator
from .constituency import (
    ConstituencyLocator,
    ConstituencySuggestionService,
    LocatedConstituencies,
    LocationContext,
)

__all__ = [
    'AbgeordnetenwatchAPI',
    'AddressGeocoder',
    'WahlkreisLocator',
    'ConstituencyLocator',
    'ConstituencySuggestionService',
    'LocatedConstituencies',
    'LocationContext',
]
```

**Step 4: Run tests**

```bash
uv run python website/manage.py test letters.tests
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add website/letters/services/
git commit -m "refactor: extract constituency services to separate module"
```

---

## Task 4: Extract identity and topic services

**Files:**
- Create: `website/letters/services/identity.py`
- Create: `website/letters/services/topics.py`
- Modify: `website/letters/services/__init__.py`

**Step 1: Create identity.py**

Create `website/letters/services/identity.py`:

```python
# ABOUTME: Identity verification service for validating user identity before sending letters.
# ABOUTME: Currently a stub implementation to be replaced with actual verification workflow.

from typing import Optional


class IdentityVerificationService:
    """Stub for future identity verification workflow."""

    @staticmethod
    def initiate_verification(user_id: int, method: str = 'email') -> dict:
        """
        Initiate identity verification for a user.

        Args:
            user_id: User ID to verify
            method: Verification method ('email', 'phone', 'postal')

        Returns:
            dict with verification_id and status
        """
        return {
            'verification_id': f'stub-{user_id}',
            'status': 'pending',
            'method': method,
        }

    @staticmethod
    def check_verification_status(verification_id: str) -> dict:
        """
        Check status of a verification request.

        Returns:
            dict with status ('pending', 'verified', 'failed')
        """
        return {
            'verification_id': verification_id,
            'status': 'pending',
        }
```

**Step 2: Read topic services code**

Read lines 2496-2616 from `website/letters/services.py` to extract:
- `TopicSuggestionService`
- `CommitteeTopicMappingService`

**Step 3: Create topics.py**

Create `website/letters/services/topics.py`:

```python
# ABOUTME: Services for mapping user input to political topics and committee classifications.
# ABOUTME: Provides lightweight suggestion helpers for topic tagging and committee-topic associations.

import logging
from typing import List, Optional

from django.db.models import Q

from ..models import Tag, TopicArea, Committee

logger = logging.getLogger(__name__)


class TopicSuggestionService:
    """Maps user input to topic tags and suggests relevant topics."""

    @staticmethod
    def suggest_topics(text: str, limit: int = 5) -> List[Tag]:
        """
        Suggest topic tags based on text input.

        Args:
            text: User input text
            limit: Maximum number of suggestions

        Returns:
            List of Tag objects
        """
        if not text or len(text) < 3:
            return []

        # Simple keyword matching - could be enhanced with NLP
        words = text.lower().split()
        tags = Tag.objects.filter(
            Q(name__icontains=text) |
            Q(name__in=words)
        ).distinct()[:limit]

        return list(tags)

    @staticmethod
    def get_popular_topics(limit: int = 10) -> List[Tag]:
        """Get most commonly used topic tags."""
        # TODO: Track usage counts
        return list(Tag.objects.all()[:limit])


class CommitteeTopicMappingService:
    """Links parliamentary committees to topic areas."""

    @staticmethod
    def get_committees_for_topic(topic_area: TopicArea) -> List[Committee]:
        """
        Find committees relevant to a topic area.

        Returns:
            List of Committee objects
        """
        # Simple name-based matching
        keywords = topic_area.name.lower().split()
        committees = Committee.objects.filter(
            Q(name__icontains=topic_area.name)
        ).distinct()

        return list(committees)

    @staticmethod
    def get_topics_for_committee(committee: Committee) -> List[TopicArea]:
        """
        Find topic areas relevant to a committee.

        Returns:
            List of TopicArea objects
        """
        # Extract keywords from committee name
        keywords = committee.name.lower().split()
        topics = TopicArea.objects.filter(
            Q(name__in=keywords)
        ).distinct()

        return list(topics)
```

**Step 4: Update __init__.py**

```python
# ABOUTME: Service layer for the letters application.
# ABOUTME: Re-exports all service classes for backward compatibility with existing imports.

from .abgeordnetenwatch_api_client import AbgeordnetenwatchAPI
from .geocoding import AddressGeocoder, WahlkreisLocator
from .constituency import (
    ConstituencyLocator,
    ConstituencySuggestionService,
    LocatedConstituencies,
    LocationContext,
)
from .identity import IdentityVerificationService
from .topics import TopicSuggestionService, CommitteeTopicMappingService

__all__ = [
    'AbgeordnetenwatchAPI',
    'AddressGeocoder',
    'WahlkreisLocator',
    'ConstituencyLocator',
    'ConstituencySuggestionService',
    'LocatedConstituencies',
    'LocationContext',
    'IdentityVerificationService',
    'TopicSuggestionService',
    'CommitteeTopicMappingService',
]
```

**Step 5: Run tests**

```bash
uv run python website/manage.py test letters.tests
```

Expected: All tests pass

**Step 6: Commit**

```bash
git add website/letters/services/
git commit -m "refactor: extract identity and topic services to separate modules"
```

---

## Task 5: Extract RepresentativeSyncService with bug fix

**Files:**
- Create: `website/letters/services/representative_sync.py`
- Modify: `website/letters/services/__init__.py`

**Step 1: Read RepresentativeSyncService code**

Read lines 736-1645 from `website/letters/services.py` - this is the full `RepresentativeSyncService` class.

**Step 2: Create representative_sync.py with bug fix**

Create `website/letters/services/representative_sync.py` by copying the class from services.py, making these changes:

1. Update imports at the top
2. **BUG FIX**: In `_fetch_active_mandates` method, change the filter from:
   ```python
   if m.get('type') == 'mandate' and m.get('electoral_data', {}).get('mandate_won')
   ```
   to:
   ```python
   if m.get('type') == 'mandate'
   ```

Copy the entire class (lines 736-1645) with the bug fix applied.

**Step 3: Update __init__.py**

```python
# ABOUTME: Service layer for the letters application.
# ABOUTME: Re-exports all service classes for backward compatibility with existing imports.

from .abgeordnetenwatch_api_client import AbgeordnetenwatchAPI
from .geocoding import AddressGeocoder, WahlkreisLocator
from .constituency import (
    ConstituencyLocator,
    ConstituencySuggestionService,
    LocatedConstituencies,
    LocationContext,
)
from .identity import IdentityVerificationService
from .topics import TopicSuggestionService, CommitteeTopicMappingService
from .representative_sync import RepresentativeSyncService

__all__ = [
    'AbgeordnetenwatchAPI',
    'AddressGeocoder',
    'WahlkreisLocator',
    'ConstituencyLocator',
    'ConstituencySuggestionService',
    'LocatedConstituencies',
    'LocationContext',
    'IdentityVerificationService',
    'TopicSuggestionService',
    'CommitteeTopicMappingService',
    'RepresentativeSyncService',
]
```

**Step 4: Run existing tests**

```bash
uv run python website/manage.py test letters.tests
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add website/letters/services/
git commit -m "refactor: extract RepresentativeSyncService and fix Saarland mandate filter bug"
```

---

## Task 6: Write comprehensive tests for RepresentativeSyncService

**Files:**
- Create: `website/letters/tests/test_representative_sync.py`

**Step 1: Write failing test for Saarland bug**

Create `website/letters/tests/test_representative_sync.py`:

```python
# ABOUTME: Tests for RepresentativeSyncService including mandate filtering and API pagination.
# ABOUTME: Includes regression test for Saarland bug (mandate_won=None filtering).

from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.utils import timezone

from letters.services import RepresentativeSyncService
from letters.models import Parliament, ParliamentTerm, Representative


class RepresentativeSyncMandateFilteringTests(TestCase):
    """Tests for mandate filtering logic."""

    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI')
    def test_saarland_bug_mandate_won_none_should_be_included(self, mock_api):
        """
        Regression test for Saarland bug.

        Mandates with mandate_won=None should be imported.
        In Saarland, 44 of 51 mandates have mandate_won=None (directly elected).
        """
        # Mock parliament data
        mock_api.get_parliaments.return_value = [{
            'id': 1,
            'label': 'Landtag des Saarlandes',
        }]

        # Mock parliament period
        mock_api.get_parliament_periods.return_value = [{
            'id': 137,
            'label': 'Saarland 2022 - 2027',
            'start_date_period': '2022-01-01',
            'end_date_period': '2027-12-31',
        }]

        # Mock candidacies with different mandate_won values
        mock_api.get_candidacies_mandates.return_value = [
            # mandate_won=None (directly elected) - was incorrectly filtered out
            {
                'id': 1,
                'type': 'mandate',
                'politician': {'id': 101, 'label': 'Directly Elected'},
                'electoral_data': {'mandate_won': None},
            },
            # mandate_won='list' - was correctly included
            {
                'id': 2,
                'type': 'mandate',
                'politician': {'id': 102, 'label': 'List Elected'},
                'electoral_data': {'mandate_won': 'list'},
            },
            # mandate_won='moved_up' - was correctly included
            {
                'id': 3,
                'type': 'mandate',
                'politician': {'id': 103, 'label': 'Moved Up'},
                'electoral_data': {'mandate_won': 'moved_up'},
            },
            # type='candidacy' - should be filtered out
            {
                'id': 4,
                'type': 'candidacy',
                'politician': {'id': 104, 'label': 'Candidate Only'},
                'electoral_data': {'mandate_won': True},
            },
        ]

        # Mock politician details
        def mock_get_politician(politician_id):
            return {
                'id': politician_id,
                'label': f'Politician {politician_id}',
                'first_name': 'Test',
                'last_name': f'Person {politician_id}',
                'party': {'label': 'Test Party'},
            }

        mock_api.get_politician.side_effect = mock_get_politician
        mock_api.get_committees.return_value = []
        mock_api.get_committee_memberships.return_value = []

        # Run sync
        service = RepresentativeSyncService(dry_run=True)
        service._sync(level='state', state='Saarland')

        # Verify all 3 mandates were processed (mandate_won=None, list, moved_up)
        # Candidacy should be excluded
        self.assertEqual(service.stats['representatives_created'], 3)

    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI')
    def test_mandate_filtering_excludes_candidacies(self, mock_api):
        """Only type='mandate' should be imported, not type='candidacy'."""
        mock_api.get_parliaments.return_value = [{
            'id': 1,
            'label': 'Bundestag',
        }]

        mock_api.get_parliament_periods.return_value = [{
            'id': 111,
            'label': 'Bundestag 2021 - 2025',
            'start_date_period': '2021-10-26',
            'end_date_period': '2025-10-25',
        }]

        mock_api.get_candidacies_mandates.return_value = [
            {
                'id': 1,
                'type': 'mandate',
                'politician': {'id': 101, 'label': 'Elected'},
                'electoral_data': {'mandate_won': 'constituency'},
            },
            {
                'id': 2,
                'type': 'candidacy',
                'politician': {'id': 102, 'label': 'Not Elected'},
                'electoral_data': {'mandate_won': False},
            },
        ]

        mock_api.get_politician.return_value = {
            'id': 101,
            'label': 'Elected',
            'first_name': 'Elected',
            'last_name': 'Person',
            'party': {'label': 'Party'},
        }

        mock_api.get_committees.return_value = []
        mock_api.get_committee_memberships.return_value = []

        service = RepresentativeSyncService(dry_run=True)
        service._sync(level='federal')

        # Only the mandate should be imported
        self.assertEqual(service.stats['representatives_created'], 1)

    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI')
    def test_different_mandate_won_values_all_imported(self, mock_api):
        """Test that all mandate_won values are handled correctly."""
        mock_api.get_parliaments.return_value = [{
            'id': 1,
            'label': 'Bundestag',
        }]

        mock_api.get_parliament_periods.return_value = [{
            'id': 111,
            'label': 'Bundestag 2021 - 2025',
        }]

        # Test all known mandate_won values from the API
        mock_api.get_candidacies_mandates.return_value = [
            {'id': 1, 'type': 'mandate', 'politician': {'id': 101},
             'electoral_data': {'mandate_won': 'constituency'}},
            {'id': 2, 'type': 'mandate', 'politician': {'id': 102},
             'electoral_data': {'mandate_won': 'list'}},
            {'id': 3, 'type': 'mandate', 'politician': {'id': 103},
             'electoral_data': {'mandate_won': 'moved_up'}},
            {'id': 4, 'type': 'mandate', 'politician': {'id': 104},
             'electoral_data': {'mandate_won': None}},
            {'id': 5, 'type': 'mandate', 'politician': {'id': 105},
             'electoral_data': {}},  # No mandate_won key
        ]

        mock_api.get_politician.return_value = {
            'id': 100,
            'label': 'Test',
            'first_name': 'Test',
            'last_name': 'Person',
            'party': {'label': 'Party'},
        }

        mock_api.get_committees.return_value = []
        mock_api.get_committee_memberships.return_value = []

        service = RepresentativeSyncService(dry_run=True)
        service._sync(level='federal')

        # All 5 mandates should be imported
        self.assertEqual(service.stats['representatives_created'], 5)
```

**Step 2: Run test to verify it passes (bug is fixed)**

```bash
uv run python website/manage.py test letters.tests.test_representative_sync::RepresentativeSyncMandateFilteringTests
```

Expected: All tests PASS (the bug was fixed in Task 5)

**Step 3: Add pagination test**

Add to `test_representative_sync.py`:

```python
class RepresentativeSyncPaginationTests(TestCase):
    """Tests for API pagination logic."""

    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI')
    def test_pagination_fetches_all_pages(self, mock_api):
        """Verify that pagination correctly fetches multiple pages."""
        # This is more of an integration test to ensure the API client
        # pagination works correctly

        # Mock returning multiple pages
        page1 = [{'id': i, 'label': f'Parliament {i}'} for i in range(100)]
        page2 = [{'id': i, 'label': f'Parliament {i}'} for i in range(100, 150)]

        call_count = [0]
        def mock_fetch(endpoint, params=None):
            results = page1 if call_count[0] == 0 else page2
            call_count[0] += 1
            return {
                'data': results,
                'meta': {
                    'result': {
                        'total': 150,
                        'count': len(results),
                        'page': call_count[0] - 1,
                    }
                }
            }

        from letters.services.abgeordnetenwatch_api_client import AbgeordnetenwatchAPI
        original_request = AbgeordnetenwatchAPI._request

        with patch.object(AbgeordnetenwatchAPI, '_request', side_effect=mock_fetch):
            results = AbgeordnetenwatchAPI.fetch_paginated('test-endpoint')

        # Should fetch all 150 items across 2 pages
        self.assertEqual(len(results), 150)
```

**Step 4: Run pagination test**

```bash
uv run python website/manage.py test letters.tests.test_representative_sync::RepresentativeSyncPaginationTests
```

Expected: PASS

**Step 5: Add dry-run test**

Add to `test_representative_sync.py`:

```python
class RepresentativeSyncDryRunTests(TestCase):
    """Tests for dry-run mode."""

    @patch('letters.services.representative_sync.AbgeordnetenwatchAPI')
    def test_dry_run_does_not_persist(self, mock_api):
        """Verify dry-run mode rolls back changes."""
        mock_api.get_parliaments.return_value = [{
            'id': 999,
            'label': 'Test Parliament',
        }]

        mock_api.get_parliament_periods.return_value = [{
            'id': 9999,
            'label': 'Test Period',
        }]

        mock_api.get_candidacies_mandates.return_value = []
        mock_api.get_committees.return_value = []

        # Run in dry-run mode
        stats = RepresentativeSyncService.sync(level='federal', dry_run=True)

        # Stats should show creation
        self.assertEqual(stats['parliaments_created'], 1)

        # But database should be empty
        self.assertEqual(Parliament.objects.filter(name='Test Parliament').count(), 0)
```

**Step 6: Run dry-run test**

```bash
uv run python website/manage.py test letters.tests.test_representative_sync::RepresentativeSyncDryRunTests
```

Expected: PASS

**Step 7: Run all representative sync tests**

```bash
uv run python website/manage.py test letters.tests.test_representative_sync
```

Expected: All tests PASS

**Step 8: Commit**

```bash
git add website/letters/tests/test_representative_sync.py
git commit -m "test: add comprehensive tests for RepresentativeSyncService"
```

---

## Task 7: Delete old services.py and services_old.py

**Files:**
- Delete: `website/letters/services.py`
- Delete: `website/letters/services_old.py`

**Step 1: Verify all tests still pass**

```bash
uv run python website/manage.py test letters.tests
```

Expected: All tests pass (19 + new tests from Task 6)

**Step 2: Check for any remaining imports of services.py**

```bash
grep -r "from.*services import" website/letters/ --include="*.py" | grep -v "services/"
grep -r "import.*services" website/letters/ --include="*.py" | grep -v "services/"
```

Expected: Only imports from `services/` package, not `services.py`

**Step 3: Delete old files**

```bash
rm website/letters/services.py
rm website/letters/services_old.py
```

**Step 4: Run all tests again**

```bash
uv run python website/manage.py test letters.tests
```

Expected: All tests pass

**Step 5: Commit**

```bash
git add -A
git commit -m "refactor: remove old monolithic services.py and services_old.py"
```

---

## Task 8: Verify sync command works with bug fix

**Files:**
- Test: Management command `sync_representatives`

**Step 1: Check that sync command still works**

```bash
uv run python website/manage.py sync_representatives --help
```

Expected: Help output shows

**Step 2: Run dry-run sync for Saarland to verify bug fix**

```bash
uv run python website/manage.py sync_representatives --level STATE --state Saarland --dry-run
```

Expected: Should report fetching 51 representatives (not 7)

**Step 3: Document the fix**

Add entry to `docs/CHANGELOG.md` or similar:

```markdown
## [Unreleased]

### Fixed
- Fixed Saarland representative sync bug where only 7 of 51 representatives were imported. The filter incorrectly excluded mandates with `mandate_won=None` (directly elected representatives).

### Changed
- Refactored `services.py` (2616 lines) into modular `services/` package:
  - `abgeordnetenwatch_api_client.py` - API client
  - `geocoding.py` - Address geocoding and Wahlkreis lookup
  - `constituency.py` - Constituency location services
  - `representative_sync.py` - Parliament/representative import
  - `identity.py` - Identity verification (stub)
  - `topics.py` - Topic suggestion services
- Removed `services_old.py`
```

**Step 4: Run full test suite**

```bash
uv run python website/manage.py test
```

Expected: All tests pass

**Step 5: Final commit**

```bash
git add docs/
git commit -m "docs: document Saarland bug fix and services refactoring"
```

---

## Summary

This plan refactors the monolithic `services.py` into a clean package structure while fixing the critical Saarland representative sync bug. Each module has a single clear responsibility, comprehensive tests ensure the refactoring doesn't break existing functionality, and the bug fix is validated with specific regression tests.

The key bug fix changes the mandate filter from checking `mandate_won` truthiness to simply checking `type == 'mandate'`, which correctly imports all 51 Saarland representatives instead of just 7.
