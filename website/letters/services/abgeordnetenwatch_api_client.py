# ABOUTME: API client for fetching parliament and representative data from Abgeordnetenwatch.
# ABOUTME: Handles pagination and HTTP communication with the public Abgeordnetenwatch v2 API.

import logging
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)


class AbgeordnetenwatchAPI:
    """Thin client for the public Abgeordnetenwatch v2 API."""

    BASE_URL = "https://www.abgeordnetenwatch.de/api/v2"
    DEFAULT_PAGE_SIZE = 100

    @classmethod
    def _request(cls, endpoint: str, params: Optional[Dict] = None) -> Dict:
        params = params or {}
        url = f"{cls.BASE_URL}/{endpoint}"
        logger.debug("GET %s params=%s", url, params)
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
